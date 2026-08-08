import json

import httpx
import pytest

from app.services.dexscreener_client import DexScreenerClient


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
