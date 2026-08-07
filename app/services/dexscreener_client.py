from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class TokenMarketQuote:
    price_usd: float
    pair_url: str | None


class DexScreenerClient:
    """Fetch a best-liquidity USD quote from the free Dexscreener API."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client

    async def get_token_quote(self, token_address: str) -> TokenMarketQuote | None:
        url = f"https://api.dexscreener.com/tokens/v1/solana/{token_address}"
        if self._client is not None:
            response = await self._client.get(url)
        else:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(url)
        response.raise_for_status()
        payload = response.json()
        pairs = payload if isinstance(payload, list) else []

        best: tuple[float, TokenMarketQuote] | None = None
        for item in pairs:
            if not isinstance(item, dict):
                continue
            base_token = item.get("baseToken")
            if (
                not isinstance(base_token, dict)
                or base_token.get("address") != token_address
            ):
                continue
            price_usd = self._positive_float(item.get("priceUsd"))
            if price_usd is None:
                continue
            liquidity = item.get("liquidity")
            liquidity_usd = (
                self._positive_float(liquidity.get("usd"))
                if isinstance(liquidity, dict)
                else None
            ) or 0.0
            pair_url = item.get("url")
            quote = TokenMarketQuote(
                price_usd=price_usd,
                pair_url=pair_url if isinstance(pair_url, str) else None,
            )
            if best is None or liquidity_usd > best[0]:
                best = (liquidity_usd, quote)
        return best[1] if best is not None else None

    @staticmethod
    def _positive_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
