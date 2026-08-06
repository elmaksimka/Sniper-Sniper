from __future__ import annotations

from app.listeners.helius_client import HeliusClient


class TokenDiscovery:
    """
    Discovers token metadata from Solana.
    """

    def __init__(
        self,
        client: HeliusClient,
    ):
        self.client = client

    async def discover(
        self,
        address: str,
    ) -> dict | None:
        """
        Fetch token metadata.
        """

        response = await self.client.get_asset(
            address,
        )

        if "error" in response:
            print(
                "Helius asset error:",
                response["error"],
            )
            return None

        asset = response.get(
            "result",
            {},
        )

        metadata = (
            asset
            .get("content", {})
            .get("metadata", {})
        )

        return {
            "address": address,
            "symbol": metadata.get("symbol"),
            "name": metadata.get("name"),
        }