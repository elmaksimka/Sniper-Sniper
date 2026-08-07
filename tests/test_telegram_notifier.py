import json
from typing import Any

import httpx
import pytest

from app.core.events import AlphaSignalGenerated
from app.notifications.telegram import TelegramNotifier


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
        )
        await notifier.handle_alpha_signal(alpha_signal())

    assert [payload["chat_id"] for payload in payloads] == ["100", "200"]
    assert all("TOP TRADER BUY" in payload["text"] for payload in payloads)
    assert all("2.750000 SOL" in payload["text"] for payload in payloads)
    assert all("5 trades / 3 wallets" in payload["text"] for payload in payloads)
    assert all("solscan.io/tx/transaction-signature" in payload["text"] for payload in payloads)


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
            }
        )
        await notifier.send_discovery_degraded(1, 240)
        await notifier.send_discovery_recovered()
        await notifier.send_worker_stopped()

    assert len(messages) == 5
    assert "Alpha Engine запущено" in messages[0]
    assert "кожні 30 с" in messages[0]
    assert "Alpha Engine працює" in messages[1]
    assert "125 транзакцій / 48 токенів" in messages[1]
    assert "17 транзакцій / 9 активних токенів" in messages[1]
    assert "7 транзакцій" in messages[1]
    assert "RPC перевантажений" in messages[2]
    assert "discovery відновлено" in messages[3]
    assert "Alpha Engine зупинено" in messages[4]
