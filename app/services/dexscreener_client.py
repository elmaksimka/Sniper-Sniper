from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class TokenMarketQuote:
    price_usd: float
    pair_url: str | None
    liquidity_usd: float = 0.0
    volume_5m_usd: float = 0.0
    buys_5m: int = 0
    sells_5m: int = 0
    pair_created_at_ms: int | None = None

    @property
    def transactions_5m(self) -> int:
        return self.buys_5m + self.sells_5m


@dataclass(frozen=True, slots=True)
class TokenTrendingMetrics:
    pair_created_at_ms: int | None
    liquidity_usd: float
    volume_6h_usd: float
    buys_6h: int
    sells_6h: int
    price_change_6h: float

    @property
    def trend_score(self) -> float:
        transactions = self.buys_6h + self.sells_6h
        return (
            self.volume_6h_usd
            + self.liquidity_usd * 0.25
            + transactions * 100
            + max(self.price_change_6h, 0) * 100
        )


@dataclass(frozen=True, slots=True)
class TrendingToken:
    pair_address: str
    token_address: str


class DexScreenerClient:
    """Fetch a best-liquidity USD quote from the free Dexscreener API."""

    SOLANA_TRENDING_H24_URL = (
        "https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc"
    )
    _PAIR_PATTERN = re.compile(
        r'"pairAddress":"([^"\\]+)","baseToken":\{[^{}]*?'
        r'"address":"([^"\\]+)"'
    )

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        renderer_url: str = "",
        renderer_timeout_seconds: float = 75,
    ) -> None:
        self._client = http_client
        self._renderer_url = renderer_url
        self._renderer_timeout_seconds = renderer_timeout_seconds

    async def get_solana_trending_h24(self) -> list[TrendingToken]:
        if not self._renderer_url:
            raise RuntimeError("DEXSCREENER_RENDERER_URL is not configured")
        payload = await self._post_json(
            self._renderer_url,
            {
                "cmd": "request.get",
                "url": self.SOLANA_TRENDING_H24_URL,
                "maxTimeout": int(self._renderer_timeout_seconds * 1000),
            },
        )
        if not isinstance(payload, dict):
            raise RuntimeError("DexScreener renderer returned invalid JSON")
        solution = payload.get("solution")
        html = solution.get("response") if isinstance(solution, dict) else None
        if payload.get("status") != "ok" or not isinstance(html, str):
            raise RuntimeError("DexScreener renderer returned no page")

        tokens: list[TrendingToken] = []
        seen_pairs: set[str] = set()
        seen_tokens: set[str] = set()
        for pair_address, token_address in self._PAIR_PATTERN.findall(html):
            if pair_address in seen_pairs or token_address in seen_tokens:
                continue
            seen_pairs.add(pair_address)
            seen_tokens.add(token_address)
            tokens.append(TrendingToken(pair_address, token_address))
        if not tokens:
            raise RuntimeError("DexScreener H24 page contained no Solana pairs")
        return tokens

    async def get_latest_solana_profiles(self) -> list[str]:
        payload = await self._get_json(
            "https://api.dexscreener.com/token-profiles/latest/v1"
        )
        if not isinstance(payload, list):
            return []
        return list(
            dict.fromkeys(
                item["tokenAddress"]
                for item in payload
                if isinstance(item, dict)
                and item.get("chainId") == "solana"
                and isinstance(item.get("tokenAddress"), str)
            )
        )

    async def get_token_trending_metrics(
        self,
        token_address: str,
    ) -> TokenTrendingMetrics | None:
        payload = await self._get_json(
            f"https://api.dexscreener.com/tokens/v1/solana/{token_address}"
        )
        pairs = payload if isinstance(payload, list) else []
        best: tuple[float, TokenTrendingMetrics] | None = None
        for item in pairs:
            if not isinstance(item, dict):
                continue
            base = item.get("baseToken")
            if not isinstance(base, dict) or base.get("address") != token_address:
                continue
            liquidity = item.get("liquidity")
            liquidity_usd = (
                self._nonnegative_float(liquidity.get("usd"))
                if isinstance(liquidity, dict)
                else None
            ) or 0.0
            volume = item.get("volume")
            txns = item.get("txns")
            h6_txns = txns.get("h6") if isinstance(txns, dict) else None
            price_change = item.get("priceChange")
            metrics = TokenTrendingMetrics(
                pair_created_at_ms=self._positive_int(item.get("pairCreatedAt")),
                liquidity_usd=liquidity_usd,
                volume_6h_usd=(
                    self._nonnegative_float(volume.get("h6"))
                    if isinstance(volume, dict)
                    else None
                )
                or 0.0,
                buys_6h=self._nonnegative_int(
                    h6_txns.get("buys") if isinstance(h6_txns, dict) else None
                ),
                sells_6h=self._nonnegative_int(
                    h6_txns.get("sells") if isinstance(h6_txns, dict) else None
                ),
                price_change_6h=(
                    self._float(price_change.get("h6"))
                    if isinstance(price_change, dict)
                    else 0.0
                ),
            )
            if best is None or liquidity_usd > best[0]:
                best = (liquidity_usd, metrics)
        return best[1] if best is not None else None

    async def get_token_quote(self, token_address: str) -> TokenMarketQuote | None:
        url = f"https://api.dexscreener.com/tokens/v1/solana/{token_address}"
        payload = await self._get_json(url)
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
            volume = item.get("volume")
            volume_5m_usd = (
                self._nonnegative_float(volume.get("m5"))
                if isinstance(volume, dict)
                else None
            ) or 0.0
            transactions = item.get("txns")
            transactions_5m = (
                transactions.get("m5") if isinstance(transactions, dict) else None
            )
            buys_5m = self._nonnegative_int(
                transactions_5m.get("buys")
                if isinstance(transactions_5m, dict)
                else None
            )
            sells_5m = self._nonnegative_int(
                transactions_5m.get("sells")
                if isinstance(transactions_5m, dict)
                else None
            )
            pair_url = item.get("url")
            quote = TokenMarketQuote(
                price_usd=price_usd,
                pair_url=pair_url if isinstance(pair_url, str) else None,
                liquidity_usd=liquidity_usd,
                volume_5m_usd=volume_5m_usd,
                buys_5m=buys_5m,
                sells_5m=sells_5m,
                pair_created_at_ms=self._positive_int(item.get("pairCreatedAt")),
            )
            if best is None or liquidity_usd > best[0]:
                best = (liquidity_usd, quote)
        return best[1] if best is not None else None

    async def _get_json(self, url: str) -> Any:
        if self._client is not None:
            response = await self._client.get(url)
        else:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
        response.raise_for_status()
        return response.json()

    async def _post_json(self, url: str, payload: dict[str, Any]) -> Any:
        if self._client is not None:
            response = await self._client.post(url, json=payload)
        else:
            async with httpx.AsyncClient(
                timeout=self._renderer_timeout_seconds + 5
            ) as client:
                response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _positive_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _nonnegative_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return 0
        return max(parsed, 0)

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None
