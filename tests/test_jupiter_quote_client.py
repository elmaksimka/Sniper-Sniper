from __future__ import annotations

import httpx
import pytest

from app.services.jupiter_quote_client import JupiterQuoteClient, USDC_MINT


@pytest.mark.asyncio
async def test_buy_quote_uses_route_output_after_fees() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["inputMint"] == USDC_MINT
        assert request.url.params["outputMint"] == "token"
        assert request.url.params["amount"] == "1000000"
        assert request.headers["x-api-key"] == "jupiter-key"
        return httpx.Response(
            200,
            json={
                "inAmount": "1000000",
                "outAmount": "250000000",
                "priceImpactPct": "0.004",
                "feeBps": 50,
                "router": "metis",
                "routePlan": [
                    {"swapInfo": {"label": "Raydium"}},
                    {"swapInfo": {"label": "Meteora"}},
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        quote = await JupiterQuoteClient(
            http,
            api_key="jupiter-key",
        ).get_buy_quote("token", 1, 6)

    assert quote is not None
    assert quote.input_amount == 1
    assert quote.output_amount == 250
    assert quote.price_impact_pct == pytest.approx(0.4)
    assert quote.fee_bps == 50
    assert quote.route == "Raydium -> Meteora"


@pytest.mark.asyncio
async def test_sell_quote_supports_keyless_and_direct_price_impact() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "x-api-key" not in request.headers
        assert request.url.params["amount"] == "123456789"
        return httpx.Response(
            200,
            json={
                "inAmount": "123456789",
                "outAmount": "765432",
                "priceImpact": 0.75,
                "feeBps": 10,
                "router": "dflow",
                "routePlan": [],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        quote = await JupiterQuoteClient(http).get_sell_quote(
            "token",
            123.456789,
            6,
        )

    assert quote is not None
    assert quote.input_amount == pytest.approx(123.456789)
    assert quote.output_amount == pytest.approx(0.765432)
    assert quote.price_impact_pct == pytest.approx(0.75)
