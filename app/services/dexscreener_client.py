from __future__ import annotations

import re
import struct
from dataclasses import dataclass
from io import BytesIO
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
    symbol: str = ""


@dataclass(frozen=True, slots=True)
class DexScreenerTopTrader:
    wallet: str
    buy_volume_usd: float
    sell_volume_usd: float
    buys: int
    sells: int
    label: str | None = None

    @property
    def realized_pnl_usd(self) -> float:
        return self.sell_volume_usd - self.buy_volume_usd

    @property
    def realized_roi(self) -> float:
        if self.buy_volume_usd <= 0:
            return 0.0
        return self.realized_pnl_usd / self.buy_volume_usd


class DexScreenerClient:
    """Fetch a best-liquidity USD quote from the free Dexscreener API."""

    SOLANA_TRENDING_H24_URL = (
        "https://dexscreener.com/solana?rankBy=trendingScoreH24&order=desc"
    )
    _PAIR_PATTERN = re.compile(
        r'"pairAddress":"([^"\\]+)","baseToken":\{[^{}]*?'
        r'"address":"([^"\\]+)"[^{}]*?"symbol":"([^"\\]*)"'
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
        solution = await self._render_page(self.SOLANA_TRENDING_H24_URL)
        html = solution["response"]

        tokens: list[TrendingToken] = []
        seen_pairs: set[str] = set()
        seen_tokens: set[str] = set()
        for pair_address, token_address, symbol in self._PAIR_PATTERN.findall(html):
            if pair_address in seen_pairs or token_address in seen_tokens:
                continue
            seen_pairs.add(pair_address)
            seen_tokens.add(token_address)
            tokens.append(TrendingToken(pair_address, token_address, symbol))
        if not tokens:
            raise RuntimeError("DexScreener H24 page contained no Solana pairs")
        return tokens

    async def get_pair_top_traders(
        self,
        pair_address: str,
        *,
        limit: int = 10,
    ) -> list[DexScreenerTopTrader]:
        pair_url = f"https://dexscreener.com/solana/{pair_address}"
        solution = await self._render_page(pair_url)
        adapter, quote_token = self._pair_feed_metadata(
            solution["response"],
            pair_address,
        )
        feed_url = (
            "https://io.dexscreener.com/dex/log/amm/v5/"
            f"{adapter}/top/solana/{pair_address}"
        )
        cookies = {
            str(item["name"]): str(item["value"])
            for item in solution.get("cookies", [])
            if isinstance(item, dict)
            and isinstance(item.get("name"), str)
            and isinstance(item.get("value"), str)
        }
        user_agent = solution.get("userAgent")
        headers = {
            "Origin": "https://dexscreener.com",
            "Referer": pair_url,
            "Accept": "*/*",
        }
        if isinstance(user_agent, str):
            headers["User-Agent"] = user_agent
        payload = await self._get_bytes(
            feed_url,
            params={"q": quote_token, "s": "pnl", "sd": "desc"},
            headers=headers,
            cookies=cookies,
        )
        return self._decode_top_traders(payload)[: max(1, limit)]

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

    async def _render_page(self, url: str) -> dict[str, Any]:
        if not self._renderer_url:
            raise RuntimeError("DEXSCREENER_RENDERER_URL is not configured")
        payload = await self._post_json(
            self._renderer_url,
            {
                "cmd": "request.get",
                "url": url,
                "maxTimeout": int(self._renderer_timeout_seconds * 1000),
            },
        )
        if not isinstance(payload, dict):
            raise TypeError("DexScreener renderer returned invalid JSON")
        solution = payload.get("solution")
        if not isinstance(solution, dict):
            raise TypeError("DexScreener renderer returned no solution")
        html = solution.get("response")
        if payload.get("status") != "ok" or not isinstance(html, str):
            raise RuntimeError("DexScreener renderer returned no page")
        return solution

    async def _get_bytes(
        self,
        url: str,
        *,
        params: dict[str, str],
        headers: dict[str, str],
        cookies: dict[str, str],
    ) -> bytes:
        if self._client is not None:
            response = await self._client.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies,
            )
        else:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers=headers,
                    cookies=cookies,
                )
        response.raise_for_status()
        return response.content

    @staticmethod
    def _pair_feed_metadata(html: str, pair_address: str) -> tuple[str, str]:
        marker = f'"pairAddress":"{pair_address}"'
        marker_index = html.find(marker)
        if marker_index < 0:
            raise RuntimeError("DexScreener pair metadata was not found")
        adapter_marker = '"a":"'
        adapter_index = html.rfind(
            adapter_marker,
            max(0, marker_index - 2_000),
            marker_index,
        )
        if adapter_index < 0:
            adapter_index = html.find(
                adapter_marker,
                marker_index,
                marker_index + 2_000,
            )
        quote_token_index = html.find(
            '"quoteToken":',
            marker_index,
            marker_index + 5_000,
        )
        quote_marker = '"address":"'
        quote_index = html.find(
            quote_marker,
            quote_token_index,
            quote_token_index + 1_000,
        )
        if adapter_index < 0 or quote_token_index < 0 or quote_index < 0:
            raise RuntimeError("DexScreener pair feed metadata was incomplete")
        adapter_start = adapter_index + len(adapter_marker)
        adapter_end = html.find('"', adapter_start)
        quote_start = quote_index + len(quote_marker)
        quote_end = html.find('"', quote_start)
        if adapter_end < 0 or quote_end < 0:
            raise RuntimeError("DexScreener pair feed metadata was incomplete")
        return html[adapter_start:adapter_end], html[quote_start:quote_end]

    @staticmethod
    def _decode_top_traders(payload: bytes) -> list[DexScreenerTopTrader]:
        decoder = _AvroDecoder(payload)
        count = decoder.read_long()
        if count < 0:
            count = -count
            decoder.read_long()
        traders: list[DexScreenerTopTrader] = []
        try:
            for _ in range(count):
                wallet = decoder.read_string()
                label = decoder.read_optional_string()
                decoder.read_optional_string()  # profile URL
                buys = decoder.read_double()
                sells = decoder.read_double()
                buy_volume_usd = decoder.read_double()
                sell_volume_usd = decoder.read_double()
                decoder.read_string()  # token amount bought
                decoder.read_string()  # token amount sold
                decoder.read_optional_string()  # current token balance
                decoder.read_optional_double()  # current balance percentage
                decoder.read_double()  # first swap timestamp
                decoder.read_double()  # last swap timestamp
                traders.append(
                    DexScreenerTopTrader(
                        wallet=wallet,
                        buy_volume_usd=buy_volume_usd,
                        sell_volume_usd=sell_volume_usd,
                        buys=max(0, int(buys)),
                        sells=max(0, int(sells)),
                        label=label,
                    )
                )
        except (EOFError, UnicodeDecodeError, struct.error) as error:
            raise RuntimeError("Invalid DexScreener top traders payload") from error
        return traders

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


class _AvroDecoder:
    def __init__(self, payload: bytes) -> None:
        self._stream = BytesIO(payload)

    def read_long(self) -> int:
        value = 0
        shift = 0
        while True:
            raw = self._stream.read(1)
            if not raw:
                raise EOFError
            byte = raw[0]
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return (value >> 1) ^ -(value & 1)
            shift += 7
            if shift > 70:
                raise RuntimeError("Invalid Avro long")

    def read_string(self) -> str:
        length = self.read_long()
        if length < 0:
            raise RuntimeError("Invalid Avro string length")
        raw = self._stream.read(length)
        if len(raw) != length:
            raise EOFError
        return raw.decode()

    def read_double(self) -> float:
        raw = self._stream.read(8)
        if len(raw) != 8:
            raise EOFError
        return struct.unpack("<d", raw)[0]

    def read_optional_string(self) -> str | None:
        branch = self.read_long()
        if branch == 0:
            return None
        if branch != 1:
            raise RuntimeError("Invalid Avro union")
        return self.read_string()

    def read_optional_double(self) -> float | None:
        branch = self.read_long()
        if branch == 0:
            return None
        if branch != 1:
            raise RuntimeError("Invalid Avro union")
        return self.read_double()
