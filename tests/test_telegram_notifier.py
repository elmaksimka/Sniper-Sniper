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
