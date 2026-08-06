from __future__ import annotations

from typing import Any

from app.listeners.helius_client import HeliusClient


class MetadataService:
    """Extract token metadata from Helius DAS responses."""

    def __init__(self, client: HeliusClient) -> None:
        self.client = client

    async def get_metadata(self, mint: str) -> dict[str, Any]:
        response = await self.client.get_asset(mint)
        asset = response.get("result")

        if not isinstance(asset, dict):
            return self.empty()

        metadata = asset.get("content", {}).get("metadata", {})
        token_info = asset.get("token_info", {})
        ownership = asset.get("ownership", {})

        return {
            "name": metadata.get("name") or "Unknown",
            "symbol": metadata.get("symbol") or "UNKNOWN",
            "creator": ownership.get("owner"),
            "decimals": self._optional_int(token_info.get("decimals")),
            "supply": self._optional_int(token_info.get("supply")),
        }

    @staticmethod
    def empty() -> dict[str, Any]:
        return {
            "name": "Unknown",
            "symbol": "UNKNOWN",
            "creator": None,
            "decimals": None,
            "supply": None,
        }

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None
