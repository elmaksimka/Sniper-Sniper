from __future__ import annotations

from typing import Any

import pytest

from app.listeners.helius_websocket import HeliusTransactionSubscriber


async def noop(transaction: dict[str, Any], addresses: tuple[str, ...]) -> None:
    return None


def subscriber() -> HeliusTransactionSubscriber:
    return HeliusTransactionSubscriber(
        "wss://example.invalid",
        ("wallet-b", "wallet-a"),
        noop,
    )


def test_subscription_uses_one_account_include_filter() -> None:
    request = subscriber().subscription_request()

    assert request["method"] == "transactionSubscribe"
    assert request["params"][0]["accountInclude"] == ["wallet-b", "wallet-a"]
    assert request["params"][1]["transactionDetails"] == "full"


def test_log_subscription_uses_one_wallet_mention() -> None:
    request = subscriber().log_subscription_request("request-one", "wallet-a")

    assert request["method"] == "logsSubscribe"
    assert request["params"] == [
        {"mentions": ["wallet-a"]},
        {"commitment": "confirmed"},
    ]


def test_notification_extracts_full_transaction_and_matching_wallets() -> None:
    stream = subscriber()
    parsed = stream.parse_notification(
        {
            "method": "transactionNotification",
            "params": {
                "result": {
                    "signature": "signature-one",
                    "slot": 123,
                    "blockTime": 1_700_000_000,
                    "transaction": {
                        "transaction": {
                            "signatures": ["signature-one"],
                            "message": {
                                "accountKeys": [
                                    {"pubkey": "wallet-a", "signer": True},
                                    {"pubkey": "program", "signer": False},
                                ]
                            },
                        },
                        "meta": {"loadedAddresses": {"writable": ["wallet-b"]}},
                    },
                }
            },
        }
    )

    assert parsed is not None
    transaction, addresses, signature = parsed
    assert signature == "signature-one"
    assert addresses == ("wallet-a", "wallet-b")
    assert transaction["blockTime"] == 1_700_000_000
    assert transaction["slot"] == 123


def test_non_transaction_messages_are_ignored() -> None:
    assert subscriber().parse_notification({"result": 123}) is None


async def fetch_transaction(signature: str) -> dict[str, Any] | None:
    return {
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": [{"pubkey": "wallet-a"}]},
        },
        "meta": {},
    }


@pytest.mark.asyncio
async def test_log_notification_fetches_full_transaction() -> None:
    stream = HeliusTransactionSubscriber(
        "wss://example.invalid",
        ("wallet-a",),
        noop,
        transaction_fetcher=fetch_transaction,
    )

    parsed = await stream.parse_log_notification(
        {
            "method": "logsNotification",
            "params": {
                "subscription": 42,
                "result": {"value": {"signature": "signature-two"}},
            },
        },
        {42: "wallet-a"},
    )

    assert parsed is not None
    transaction, addresses, signature = parsed
    assert signature == "signature-two"
    assert addresses == ("wallet-a",)
    assert transaction["signature"] == "signature-two"
