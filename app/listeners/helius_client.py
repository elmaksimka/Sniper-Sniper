from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class HeliusTransactionPage:
    transactions: list[dict[str, Any]]
    pagination_token: str | None


class HeliusRPCError(RuntimeError):
    """Raised when Helius returns a JSON-RPC error response."""


class HeliusClient:
    """Async client for the Helius RPC and Enhanced Transactions APIs."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self.api_key = settings.helius_api_key
        self.transaction_history_mode = settings.transaction_history_mode
        helius_url = settings.helius_rpc_url or (
            f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
            if self.api_key
            else ""
        )
        self.rpc_url = (
            settings.solana_rpc_url or helius_url
            if self.transaction_history_mode == "standard"
            else helius_url or settings.solana_rpc_url
        )
        self.max_retries = settings.helius_max_retries
        self.retry_base_seconds = settings.helius_retry_base_seconds
        self.retry_max_seconds = settings.helius_retry_max_seconds
        self._timeout = settings.helius_timeout_seconds
        self.request_delay = settings.helius_request_delay_seconds
        self.standard_transaction_delay = (
            settings.standard_rpc_transaction_delay_seconds
        )
        self._semaphore = asyncio.Semaphore(settings.helius_max_concurrency)
        self._client = http_client
        self._owns_client = http_client is None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _retry_delay(
        self,
        attempt: int,
        response: httpx.Response | None = None,
    ) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), self.retry_max_seconds)
                except ValueError:
                    pass
        return min(
            self.retry_base_seconds * (2**attempt),
            self.retry_max_seconds,
        )

    @staticmethod
    def _is_retryable_rpc_error(error: object) -> bool:
        if not isinstance(error, dict):
            return False
        code = error.get("code")
        message = str(error.get("message", "")).lower()
        return code in {-32005, -32004, -32603} or any(
            marker in message
            for marker in ("rate limit", "temporarily", "unavailable", "timeout")
        )

    async def _request(
        self,
        method: str,
        params: list[Any] | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.rpc_url:
            return {"error": {"message": "Helius RPC is not configured"}}

        payload = {
            "jsonrpc": "2.0",
            "id": "alpha-engine",
            "method": method,
            "params": params or [],
        }
        client = self._get_client()

        for attempt in range(self.max_retries + 1):
            response: httpx.Response | None = None
            try:
                async with self._semaphore:
                    response = await client.post(self.rpc_url, json=payload)
                    if self.request_delay > 0:
                        await asyncio.sleep(self.request_delay)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise HeliusRPCError("Helius returned a non-object response")

                error = data.get("error")
                if error is None:
                    return data
                if not self._is_retryable_rpc_error(error):
                    raise HeliusRPCError(f"Helius RPC error: {error}")
                if attempt >= self.max_retries:
                    raise HeliusRPCError(f"Helius RPC error: {error}")
            except httpx.HTTPStatusError as exc:
                if (
                    exc.response.status_code not in {408, 429, 500, 502, 503, 504}
                    or attempt >= self.max_retries
                ):
                    raise HeliusRPCError(
                        f"Helius HTTP {exc.response.status_code}"
                    ) from None
                response = exc.response
            except httpx.RequestError:
                if attempt >= self.max_retries:
                    raise

            await asyncio.sleep(self._retry_delay(attempt, response))

        raise RuntimeError("unreachable")

    async def get_health(self) -> dict[str, Any]:
        return await self._request("getHealth")

    async def get_asset(self, address: str) -> dict[str, Any]:
        if self.transaction_history_mode == "standard":
            return {"result": None}
        return await self._request("getAsset", {"id": address})

    async def get_signatures(
        self,
        address: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        return await self.get_signature_page(address, limit)

    async def get_signature_page(
        self,
        address: str,
        limit: int = 10,
        before: str | None = None,
    ) -> dict[str, Any]:
        config: dict[str, Any] = {
            "limit": min(max(limit, 1), 1000),
            "commitment": "finalized",
        }
        if before:
            config["before"] = before
        return await self._request(
            "getSignaturesForAddress",
            [address, config],
        )

    async def get_transaction(self, signature: str) -> dict[str, Any]:
        return await self._request(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "finalized",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )

    async def get_transactions_for_address(
        self,
        wallet: str,
        limit: int = 100,
        pagination_token: str | None = None,
        sort_order: Literal["asc", "desc"] = "desc",
    ) -> HeliusTransactionPage:
        if self.transaction_history_mode == "standard":
            return await self._get_standard_transactions_for_address(
                wallet,
                limit,
                pagination_token,
            )

        return await self._get_enhanced_transactions_for_address(
            wallet,
            limit,
            pagination_token,
            sort_order,
        )

    async def count_transactions_for_address(self, wallet: str) -> int:
        """Count the complete finalized signature history for a wallet."""
        total = 0
        before: str | None = None
        seen_cursors: set[str] = set()
        while True:
            config: dict[str, Any] = {
                "limit": 1_000,
                "commitment": "finalized",
            }
            if before:
                config["before"] = before
            response = await self._request(
                "getSignaturesForAddress",
                [wallet, config],
            )
            result = response.get("result")
            signatures = (
                [item for item in result if isinstance(item, dict)]
                if isinstance(result, list)
                else []
            )
            total += len(signatures)
            if len(signatures) < 1_000:
                return total
            cursor = signatures[-1].get("signature")
            if not isinstance(cursor, str) or not cursor or cursor in seen_cursors:
                return total
            seen_cursors.add(cursor)
            before = cursor

    async def _get_enhanced_transactions_for_address(
        self,
        wallet: str,
        limit: int,
        pagination_token: str | None,
        sort_order: Literal["asc", "desc"],
    ) -> HeliusTransactionPage:
        config: dict[str, Any] = {
            "transactionDetails": "full",
            "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": 0,
            "sortOrder": sort_order,
            "limit": min(max(limit, 1), 100),
            "commitment": "finalized",
        }
        if pagination_token:
            config["paginationToken"] = pagination_token

        response = await self._request(
            "getTransactionsForAddress",
            [wallet, config],
        )
        result = response.get("result")
        if not isinstance(result, dict):
            return HeliusTransactionPage([], None)

        data = result.get("data")
        transactions = (
            [item for item in data if isinstance(item, dict)]
            if isinstance(data, list)
            else []
        )
        next_token = result.get("paginationToken")
        return HeliusTransactionPage(
            transactions=transactions,
            pagination_token=(
                next_token if isinstance(next_token, str) and next_token else None
            ),
        )

    async def _get_standard_transactions_for_address(
        self,
        wallet: str,
        limit: int,
        before: str | None,
    ) -> HeliusTransactionPage:
        page_limit = min(max(limit, 1), 100)
        config: dict[str, Any] = {
            "limit": page_limit,
            "commitment": "finalized",
        }
        if before:
            config["before"] = before

        response = await self._request(
            "getSignaturesForAddress",
            [wallet, config],
        )
        result = response.get("result")
        rows = (
            [row for row in result if isinstance(row, dict)]
            if isinstance(result, list)
            else []
        )
        signatures = [
            signature
            for row in rows
            if row.get("err") is None
            and isinstance((signature := row.get("signature")), str)
            and signature
        ]
        # Public Solana RPC endpoints apply strict per-method burst limits.
        # Fetch details sequentially so one history page does not launch a
        # synchronized wave of requests and retries after a 429 response.
        responses = []
        for index, signature in enumerate(signatures):
            responses.append(await self.get_transaction(signature))
            if (
                self.standard_transaction_delay > 0
                and index < len(signatures) - 1
            ):
                await asyncio.sleep(self.standard_transaction_delay)
        transactions = [
            transaction
            for item in responses
            if isinstance((transaction := item.get("result")), dict)
        ]

        last_signature = rows[-1].get("signature") if rows else None
        next_token = (
            last_signature
            if len(rows) == page_limit
            and isinstance(last_signature, str)
            and last_signature
            else None
        )
        return HeliusTransactionPage(transactions, next_token)
