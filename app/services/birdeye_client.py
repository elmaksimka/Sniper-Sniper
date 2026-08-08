from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class TokenTopTrader:
    wallet: str
    token_address: str
    realized_pnl_usd: float
    total_pnl_usd: float
    buy_volume_usd: float
    sell_volume_usd: float
    tags: tuple[str, ...]

    @property
    def realized_roi(self) -> float:
        if self.buy_volume_usd <= 0:
            return 0.0
        return self.realized_pnl_usd / self.buy_volume_usd


class BirdeyeClient:
    """Read ranked token traders from Birdeye's public Data Services API."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key
        self._client = http_client

    async def get_top_traders(
        self,
        token_address: str,
        *,
        limit: int = 10,
    ) -> list[TokenTopTrader]:
        if not self.api_key:
            return []
        url = "https://public-api.birdeye.so/defi/v2/tokens/top_traders"
        params: dict[str, str | int] = {
            "address": token_address,
            "time_frame": "all_time",
            "sort_by": "realized_pnl",
            "sort_type": "desc",
            "offset": 0,
            "limit": max(1, min(limit, 10)),
        }
        headers = {"X-API-KEY": self.api_key, "x-chain": "solana"}
        response: httpx.Response | None = None
        for attempt in range(3):
            if self._client is not None:
                response = await self._client.get(
                    url,
                    params=params,
                    headers=headers,
                )
            else:
                async with httpx.AsyncClient(timeout=15) as client:
                    response = await client.get(
                        url,
                        params=params,
                        headers=headers,
                    )
            if response.status_code != 429 or attempt == 2:
                break
            retry_after = self._float(response.headers.get("Retry-After"))
            await asyncio.sleep(max(retry_after, 1.1 * (attempt + 1)))
        assert response is not None
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else None
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            return []

        traders: list[TokenTopTrader] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            wallet = item.get("owner")
            if not isinstance(wallet, str) or not wallet:
                continue
            tags = item.get("tags")
            traders.append(
                TokenTopTrader(
                    wallet=wallet,
                    token_address=token_address,
                    realized_pnl_usd=self._float(item.get("realizedPnl")),
                    total_pnl_usd=self._float(item.get("totalPnl")),
                    buy_volume_usd=self._float(item.get("volumeBuyUSD")),
                    sell_volume_usd=self._float(item.get("volumeSellUSD")),
                    tags=tuple(
                        str(tag).lower()
                        for tag in tags
                        if isinstance(tag, str)
                    )
                    if isinstance(tags, list)
                    else (),
                )
            )
        return traders

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
