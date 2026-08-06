from __future__ import annotations

import httpx

from app.core.config import get_settings


class HeliusClient:
    """
    Client for interacting with Helius API.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def get_health(self) -> dict:
        """
        Check Helius RPC connection.
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
                    "id": 1,
                    "method": "getHealth",
                },
                timeout=10,
            )

            response.raise_for_status()

            return response.json()

    async def get_asset(
        self,
        address: str,
    ) -> dict:
        """
        Get Solana token metadata using Helius DAS API.
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
                    "method": "getAsset",
                    "params": {
                        "id": address,
                    },
                },
                timeout=10,
            )

            response.raise_for_status()

            return response.json()