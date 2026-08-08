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
        await notifier.send_worker_started(
            monitor_interval_seconds=30,
            rpc_discovery_interval_seconds=120,
            candidate_refresh_interval_seconds=21_600,
            candidate_token_limit=5,
            traders_per_token=10,
            history_page_size=75,
            maximum_history_transactions=1_000,
            external_discovery_enabled=True,
        )
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
                "candidate_history_transactions_total": 95,
                "candidate_audit_state": "in_progress",
                "candidate_wallets_promoted": 1,
                "candidate_last_wallet": "candidate-wallet",
                "candidate_last_score_before": 39.4,
                "candidate_last_score_after": 42.1,
                "candidate_history_limit": 20,
                "candidate_source_window_hours": 24,
                "candidate_source_tokens": 25,
                "candidate_source_candidates": 80,
                "top_wallets": [
                    {
                        "address": "Gb2HfReRRLpp8w5zkKhu1SSTpkpWbTMdjwduvLiiDivC",
                        "score": 88.35,
                        "grade": "A",
                    },
                    {
                        "address": "BUs3UHJgT3sfUmddBJyMJ5pLSKaxWKLMqjoXx5TqgCuB",
                        "score": 78.28,
                        "grade": "B",
                    },
                    {
                        "address": "2PfoPwHGD33wB8tjMuV7F7G1wkxMSBGULzy6UKWFW12X",
                        "score": 64.84,
                        "grade": "C",
                    },
                ],
            }
        )
        await notifier.send_discovery_degraded(1, 240)
        await notifier.send_discovery_recovered()
        await notifier.send_worker_stopped()

    assert len(messages) == 5
    assert "Alpha Engine запущено" in messages[0]
    assert "Джерело кандидатів: DexScreener → Birdeye" in messages[0]
    assert "Черга: 5 монет × топ-10 трейдерів" in messages[0]
    assert "сторінками 75, до 1000 транзакцій" in messages[0]
    assert "усі трейдери монети → наступна монета" in messages[0]
    assert "Моніторинг A/B: кожні 30 с" in messages[0]
    assert "Оновлення монет: кожні 6 год" in messages[0]
    assert "Фоновий RPC discovery: кожні 120 с" in messages[0]
    assert "Alpha Engine працює" in messages[1]
    assert "125 транзакцій / 48 торгових токенів" in messages[1]
    assert "17 транзакцій / 9 активних токенів" in messages[1]
    assert "7 транзакцій" in messages[1]
    assert "Кандидатів оброблено: 1" in messages[1]
    assert "Воронка 24 год: 25 winner-токенів / 80 ранніх трейдерів" in messages[1]
    assert "Останній кандидат: candidate-wallet (39.40 → 42.10)" in messages[1]
    assert (
        "Історія кандидата: 95 транзакцій загалом; "
        "остання сторінка 20 транзакцій; стан in_progress"
    ) in messages[1]
    assert "Нових топ-гаманців: 1" in messages[1]
    assert "Активні топ-гаманці A/B (2):" in messages[1]
    assert "Gb2HfReRRLpp8w5zkKhu1SSTpkpWbTMdjwduvLiiDivC — 88.35 (A)" in messages[1]
    assert "BUs3UHJgT3sfUmddBJyMJ5pLSKaxWKLMqjoXx5TqgCuB — 78.28 (B)" in messages[1]
    assert "2PfoPwHGD33wB8tjMuV7F7G1wkxMSBGULzy6UKWFW12X" not in messages[1]
    assert "RPC перевантажений" in messages[2]
    assert "discovery відновлено" in messages[3]
    assert "Alpha Engine зупинено" in messages[4]
