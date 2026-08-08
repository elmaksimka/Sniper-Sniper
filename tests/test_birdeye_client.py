import httpx
import pytest
from unittest.mock import AsyncMock

import app.services.birdeye_client as birdeye_module
from app.services.birdeye_client import BirdeyeClient


@pytest.mark.asyncio
async def test_top_traders_are_parsed_and_sorted_by_realized_pnl() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-API-KEY"] == "secret"
        assert request.headers["x-chain"] == "solana"
        assert request.url.params["sort_by"] == "realized_pnl"
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "items": [
                        {
                            "owner": "wallet",
                            "realizedPnl": 52_645.93,
                            "totalPnl": 52_645.93,
                            "volumeBuyUSD": 3_788.83,
                            "volumeSellUSD": 70_402.02,
                            "tags": ["dev", "bundler"],
                        }
                    ]
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        traders = await BirdeyeClient("secret", http).get_top_traders("mint")

    assert len(traders) == 1
    assert traders[0].wallet == "wallet"
    assert traders[0].realized_pnl_usd == 52_645.93
    assert traders[0].realized_roi > 13
    assert traders[0].tags == ("dev", "bundler")


@pytest.mark.asyncio
async def test_top_traders_retries_rate_limit(monkeypatch) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, request=request)
        return httpx.Response(
            200,
            json={"success": True, "data": {"items": []}},
            request=request,
        )

    sleep = AsyncMock()
    monkeypatch.setattr(birdeye_module.asyncio, "sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        traders = await BirdeyeClient("secret", http).get_top_traders("mint")

    assert traders == []
    assert calls == 2
    sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_top_traders_pages_when_more_than_ten_are_requested() -> None:
    offsets: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        offsets.append(request.url.params["offset"])
        count = int(request.url.params["limit"])
        start = int(request.url.params["offset"])
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "items": [
                        {"owner": f"wallet-{index}", "realizedPnl": 100 - index}
                        for index in range(start, start + count)
                    ]
                },
            },
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        traders = await BirdeyeClient("secret", http).get_top_traders(
            "mint",
            limit=15,
        )

    assert offsets == ["0", "10"]
    assert len(traders) == 15
