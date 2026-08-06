from __future__ import annotations

import httpx

from app.core.config import get_settings


class HeliusClient:
    """
    Client for Helius API.

    Responsible only for communication
    with external Helius services.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    async def get_health(self) -> dict:
        """
        Temporary health check.

        Later will be replaced with:
        - getAsset
        - getTransactions
        - WebSocket subscriptions
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