from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings


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
        self.base_url = "https://api.helius.xyz"

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

    async def get_transactions(
        self,
        wallet: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if not self.api_key:
            return []

        url = f"{self.base_url}/v0/addresses/{wallet}/transactions"

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                url,
                params={"api-key": self.api_key, "limit": limit},
            )
            response.raise_for_status()
            data = response.json()

        return data if isinstance(data, list) else []
