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


@pytest.mark.asyncio
async def test_quote_returns_none_when_token_is_not_indexed() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        quote = await DexScreenerClient(http).get_token_quote("mint")

    assert quote is None
