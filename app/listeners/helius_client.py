from __future__ import annotations

import httpx

from app.core.config import get_settings


class HeliusClient:
    """
    Client for interacting with Helius API.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def _request(
        self,
        method: str,
        params: list | None = None,
    ) -> dict:
        """
        Generic JSON RPC request.
        """

        if not self.settings.helius_rpc_url:
            return {
                "status": "not_configured",
            }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.settings.helius_rpc_url,
                json={
                    "jsonrpc": "2.0",
                    "id": "alpha-engine",
                    "method": method,
                    "params": params or [],
                },
                timeout=10,
            )

            response.raise_for_status()

            return response.json()

    async def get_health(self) -> dict:
        """
        Check Helius RPC connection.
        """

        return await self._request(
            "getHealth",
        )

    async def get_asset(
        self,
        address: str,
    ) -> dict:
        """
        Get Solana token metadata using Helius DAS API.
        """

        return await self._request(
            "getAsset",
            [
                address,
            ],
        )

    async def get_signatures(
        self,
        address: str,
        limit: int = 10,
    ) -> dict:
        """
        Get recent transaction signatures.
        """

        return await self._request(
            "getSignaturesForAddress",
            [
                address,
                {
                    "limit": limit,
                },
            ],
        )

    async def get_transaction(
        self,
        signature: str,
    ) -> dict:
        """
        Get parsed Solana transaction.
        """

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