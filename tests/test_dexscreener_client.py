import json
import struct

import httpx
import pytest

from app.services.dexscreener_client import DexScreenerClient


def _avro_long(value: int) -> bytes:
    encoded = (value << 1) ^ (value >> 63)
    output = bytearray()
    while encoded & ~0x7F:
        output.append((encoded & 0x7F) | 0x80)
        encoded >>= 7
    output.append(encoded)
    return bytes(output)


def _avro_string(value: str) -> bytes:
    raw = value.encode()
    return _avro_long(len(raw)) + raw


def _avro_optional_string(value: str | None) -> bytes:
    if value is None:
        return _avro_long(0)
    return _avro_long(1) + _avro_string(value)


def _avro_optional_double(value: float | None) -> bytes:
    if value is None:
        return _avro_long(0)
    return _avro_long(1) + struct.pack("<d", value)


def _top_trader_record(
    wallet: str,
    *,
    buy_volume: float,
    sell_volume: float,
    label: str | None = None,
) -> bytes:
    return b"".join(
        [
            _avro_string(wallet),
            _avro_optional_string(label),
            _avro_optional_string(None),
            struct.pack("<d", 2),
            struct.pack("<d", 1),
            struct.pack("<d", buy_volume),
            struct.pack("<d", sell_volume),
            _avro_string("100"),
            _avro_string("80"),
            _avro_optional_string("20"),
            _avro_optional_double(20),
            struct.pack("<d", 1_700_000_000),
            struct.pack("<d", 1_700_001_000),
        ]
    )


@pytest.mark.asyncio
async def test_quote_uses_highest_liquidity_pair_for_requested_base_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {
                    "baseToken": {"address": "mint"},
                    "priceUsd": "0.01",
                    "liquidity": {"usd": 100},
                    "url": "https://dexscreener.com/solana/low",
                },
                {
                    "baseToken": {"address": "mint"},
                    "priceUsd": "0.02",
                    "liquidity": {"usd": 500},
                    "volume": {"m5": 7500},
                    "txns": {"m5": {"buys": 8, "sells": 4}},
                    "pairCreatedAt": 1_700_000_000_000,
                    "url": "https://dexscreener.com/solana/best",
                },
                {
                    "baseToken": {"address": "another-token"},
                    "priceUsd": "999",
                    "liquidity": {"usd": 1000},
                },
            ],
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        quote = await DexScreenerClient(http).get_token_quote("mint")

    assert quote is not None
    assert quote.price_usd == 0.02
    assert quote.pair_url == "https://dexscreener.com/solana/best"
    assert quote.liquidity_usd == 500
    assert quote.volume_5m_usd == 7500
    assert quote.buys_5m == 8
    assert quote.sells_5m == 4
    assert quote.transactions_5m == 12
    assert quote.pair_created_at_ms == 1_700_000_000_000


@pytest.mark.asyncio
async def test_quote_returns_none_when_token_is_not_indexed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        quote = await DexScreenerClient(http).get_token_quote("mint")

    assert quote is None


@pytest.mark.asyncio
async def test_latest_profiles_only_returns_solana_addresses() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"chainId": "solana", "tokenAddress": "mint"},
                {"chainId": "ethereum", "tokenAddress": "other"},
            ],
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        profiles = await DexScreenerClient(http).get_latest_solana_profiles()

    assert profiles == ["mint"]


@pytest.mark.asyncio
async def test_h24_trending_preserves_page_order_and_deduplicates_tokens() -> None:
    html = "".join(
        [
            '"pairAddress":"pair-1","baseToken":{"$typeName":"Token",'
            '"address":"mint-1","symbol":"ONE"}',
            '"pairAddress":"pair-2","baseToken":{"$typeName":"Token",'
            '"address":"mint-2","symbol":"TWO"}',
            '"pairAddress":"pair-3","baseToken":{"$typeName":"Token",'
            '"address":"mint-1","symbol":"ONE"}',
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "http://renderer:8191/v1"
        request_payload = json.loads(request.content)
        assert request_payload["url"].endswith(
            "rankBy=trendingScoreH24&order=desc"
        )
        return httpx.Response(
            200,
            json={"status": "ok", "solution": {"response": html}},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        tokens = await DexScreenerClient(
            http,
            renderer_url="http://renderer:8191/v1",
        ).get_solana_trending_h24()

    assert [(item.pair_address, item.token_address) for item in tokens] == [
        ("pair-1", "mint-1"),
        ("pair-2", "mint-2"),
    ]


@pytest.mark.asyncio
async def test_pair_top_traders_uses_dex_pnl_order_and_decodes_feed() -> None:
    pair = "Nx9dcwNs3iJxM5YAxshMHE4aYJHdDyyGMhVcmaSgfu8"
    quote = "So11111111111111111111111111111111111111112"
    html = (
        '"a":"pumpfundex","pairAddress":"'
        f'{pair}","quoteToken":{{"address":"{quote}"}}'
    )
    feed = b"".join(
        [
            _avro_long(2),
            _top_trader_record(
                "CAPn1yH4oSywsxGU456jfgTrSSUidf9jgeAnHceNUJdw",
                buy_volume=4_500,
                sell_volume=70_400,
                label="himothy",
            ),
            _top_trader_record(
                "second-wallet",
                buy_volume=2_000,
                sell_volume=5_000,
            ),
        ]
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "renderer":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "solution": {
                        "response": html,
                        "userAgent": "test-agent",
                        "cookies": [{"name": "cf_clearance", "value": "ok"}],
                    },
                },
                request=request,
            )
        assert request.url.host == "io.dexscreener.com"
        assert dict(request.url.params) == {
            "q": quote,
            "s": "pnl",
            "sd": "desc",
        }
        assert request.headers["user-agent"] == "test-agent"
        assert request.headers["cookie"] == "cf_clearance=ok"
        return httpx.Response(200, content=feed, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        traders = await DexScreenerClient(
            http,
            renderer_url="http://renderer:8191/v1",
        ).get_pair_top_traders(pair, limit=10)

    assert [trader.wallet for trader in traders] == [
        "CAPn1yH4oSywsxGU456jfgTrSSUidf9jgeAnHceNUJdw",
        "second-wallet",
    ]
    assert traders[0].label == "himothy"
    assert traders[0].realized_pnl_usd == 65_900
    assert traders[0].realized_roi == pytest.approx(14.6444, rel=1e-4)
