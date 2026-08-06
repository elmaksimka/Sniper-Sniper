from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import get_settings


@dataclass(frozen=True, slots=True)
class HeliusTransactionPage:
    transactions: list[dict[str, Any]]
    pagination_token: str | None


class HeliusClient:
    """Async client for the Helius RPC and Enhanced Transactions APIs."""

    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.helius_api_key
        self.rpc_url = settings.helius_rpc_url or (
            f"https://mainnet.helius-rpc.com/?api-key={self.api_key}"
            if self.api_key
            else ""
        )

    async def _request(
        self,
        method: str,
        params: list[Any] | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.rpc_url:
            return {"error": {"message": "Helius RPC is not configured"}}

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                self.rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "alpha-engine",
                    "method": method,
                    "params": params or [],
                },
            )
            response.raise_for_status()
            return response.json()

    async def get_health(self) -> dict[str, Any]:
        return await self._request("getHealth")

    async def get_asset(self, address: str) -> dict[str, Any]:
        return await self._request("getAsset", {"id": address})

    async def get_signatures(
        self,
        address: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        return await self._request(
            "getSignaturesForAddress",
            [address, {"limit": limit}],
        )

    async def get_transaction(self, signature: str) -> dict[str, Any]:
        return await self._request(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
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
        config: dict[str, Any] = {
            "transactionDetails": "full",
            "encoding": "jsonParsed",
            "maxSupportedTransactionVersion": 0,
            "sortOrder": sort_order,
            "limit": min(max(limit, 1), 100),
            "commitment": "finalized",
            "filters": {
                "status": "succeeded",
                "tokenAccounts": "balanceChanged",
            },
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
