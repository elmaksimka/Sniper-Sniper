import json
from typing import Any

import httpx
import pytest

from app.core.events import AlphaSignalGenerated
from app.notifications.telegram import TelegramNotifier
from app.services.dexscreener_client import TokenMarketQuote


def alpha_signal() -> AlphaSignalGenerated:
    return AlphaSignalGenerated(
        wallet="wallet-address",
        token_address="token-address",
        wallet_score=82.5,
        wallet_grade="A",
        token_score=71.25,
        token_grade="B",
        token_score_methodology="early-token-v1",
        observed_trade_count=5,
        observed_wallet_count=3,
        token_amount=1234.5,
        sol_amount=2.75,
        signature="transaction-signature",
        severity="high",
        message="alpha",
        observed_top_trader_count=2,
        trader_long_hold_positions=2,
        trader_max_trades_60s=3,
        trader_rapid_round_trips=0,
    )


class FakeMarketData:
    async def get_token_quote(self, token_address: str) -> TokenMarketQuote:
        return TokenMarketQuote(
            price_usd=0.01,
            pair_url="https://dexscreener.com/solana/pair-address",
            liquidity_usd=20_000,
            volume_5m_usd=7_500,
            buys_5m=8,
            sells_5m=4,
        )


@pytest.mark.asyncio
async def test_alpha_signal_is_sent_to_each_unique_recipient() -> None:
    payloads: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(200, json={"ok": True}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        notifier = TelegramNotifier(
            "secret-token",
            ["100", "200", "100"],
            http_client=http,
            market_data_client=FakeMarketData(),  # type: ignore[arg-type]
        )
        await notifier.handle_alpha_signal(alpha_signal())

    assert [payload["chat_id"] for payload in payloads] == ["100", "200"]
    assert all("STRONG CONSENSUS" in payload["text"] for payload in payloads)
    assert all("2.750000 SOL" in payload["text"] for payload in payloads)
    assert all("~$12.35 (current DEX price)" in payload["text"] for payload in payloads)
    assert all("5 trades / 3 wallets" in payload["text"] for payload in payloads)
    assert all("$20,000 liquidity / $7,500 5m volume" in payload["text"] for payload in payloads)
    assert all("8 buys / 4 sells" in payload["text"] for payload in payloads)
    assert all("Top traders in token: 2" in payload["text"] for payload in payloads)
    assert all("2 proven 30m+ holds" in payload["text"] for payload in payloads)
    assert all("solscan.io/tx/transaction-signature" in payload["text"] for payload in payloads)
    assert all(
        "dexscreener.com/solana/pair-address" in payload["text"]
        for payload in payloads
    )


@pytest.mark.asyncio
async def test_disabled_notifier_makes_no_request() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"ok": True}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        notifier = TelegramNotifier("", ["100"], http_client=http)
        await notifier.handle_alpha_signal(alpha_signal())

    assert calls == 0


@pytest.mark.asyncio
async def test_worker_status_notifications_are_delivered() -> None:
    messages: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        messages.append(str(json.loads(request.content)["text"]))
        return httpx.Response(200, json={"ok": True}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        notifier = TelegramNotifier("secret-token", ["100"], http_client=http)
        await notifier.send_worker_started(30, 120, 20, 2)
        await notifier.send_worker_status(
            {
                "discovery_failures": 0,
                "discovered_transactions": 7,
                "processed_transactions": 3,
                "total_transactions": 125,
                "total_tokens": 48,
                "recent_transactions": 17,
                "recent_tokens": 9,
                "status_window_minutes": 30,
                "candidate_wallets_enriched": 1,
                "candidate_history_transactions": 20,
                "candidate_wallets_promoted": 1,
            }
        )
        await notifier.send_discovery_degraded(1, 240)
        await notifier.send_discovery_recovered()
        await notifier.send_worker_stopped()

    assert len(messages) == 5
    assert "Alpha Engine запущено" in messages[0]
    assert "кожні 30 с" in messages[0]
    assert "Alpha Engine працює" in messages[1]
    assert "125 транзакцій / 48 торгових токенів" in messages[1]
    assert "17 транзакцій / 9 активних токенів" in messages[1]
    assert "7 транзакцій" in messages[1]
    assert "Кандидатів оброблено: 1" in messages[1]
    assert "Історичних транзакцій: 20" in messages[1]
    assert "Нових топ-гаманців: 1" in messages[1]
    assert "RPC перевантажений" in messages[2]
    assert "discovery відновлено" in messages[3]
    assert "Alpha Engine зупинено" in messages[4]
