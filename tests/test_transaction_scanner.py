from typing import Any

import pytest

from app.analyzer import TokenAnalyzer, TokenTrade
from app.listeners.helius_client import HeliusTransactionPage
from app.listeners.transaction_scanner import TransactionScanner
from app.services.token_parser import TokenParser


def raw_transaction(signature: str, block_time: int = 1_700_000_000) -> dict:
    return {
        "slot": 100,
        "blockTime": block_time,
        "transaction": {
            "signatures": [signature],
            "message": {"accountKeys": ["wallet"]},
        },
        "meta": {
            "fee": 0,
            "preBalances": [1_000_000_000],
            "postBalances": [900_000_000],
            "preTokenBalances": [],
            "postTokenBalances": [
                {
                    "mint": "mint",
                    "owner": "wallet",
                    "uiTokenAmount": {"uiAmount": 10},
                }
            ],
        },
    }


class FakeHeliusClient:
    async def get_transactions_for_address(
        self,
        wallet: str,
        limit: int,
        pagination_token: str | None,
        sort_order: str,
    ) -> HeliusTransactionPage:
        assert wallet == "wallet"
        assert limit == 3
        assert pagination_token is None
        assert sort_order == "desc"
        return HeliusTransactionPage([raw_transaction("signature")], None)


@pytest.mark.asyncio
async def test_scanner_returns_tokens_and_normalized_raw_trades() -> None:
    helius: Any = FakeHeliusClient()
    scanner = TransactionScanner(
        helius=helius,
        parser=TokenParser(),
        analyzer=TokenAnalyzer(),
    )

    result = await scanner.scan_address("wallet", limit=3)

    assert result == [
        {
            "signature": "signature",
            "timestamp": 1_700_000_000,
            "tokens": ["mint"],
            "trades": [
                TokenTrade(
                    mint="mint",
                    wallet="wallet",
                    sol_change=-0.1,
                    token_change=10.0,
                )
            ],
        }
    ]


class PaginatedHeliusClient:
    def __init__(self) -> None:
        self.tokens: list[str | None] = []

    async def get_transactions_for_address(
        self,
        wallet: str,
        limit: int,
        pagination_token: str | None,
        sort_order: str,
    ) -> HeliusTransactionPage:
        self.tokens.append(pagination_token)
        if pagination_token is None:
            return HeliusTransactionPage(
                [raw_transaction("sig-1"), raw_transaction("sig-2")],
                "next-page",
            )
        return HeliusTransactionPage(
            [raw_transaction("sig-2"), raw_transaction("sig-3")],
            None,
        )


@pytest.mark.asyncio
async def test_scanner_paginates_and_deduplicates_signatures() -> None:
    helius = PaginatedHeliusClient()
    helius_dependency: Any = helius
    scanner = TransactionScanner(
        helius=helius_dependency,
        parser=TokenParser(),
        analyzer=TokenAnalyzer(),
    )

    result = await scanner.scan_address("wallet", limit=3)

    assert [item["signature"] for item in result] == ["sig-1", "sig-2", "sig-3"]
    assert helius.tokens == [None, "next-page"]


class RepeatingTokenClient:
    async def get_transactions_for_address(
        self,
        **_: Any,
    ) -> HeliusTransactionPage:
        return HeliusTransactionPage([], "repeated-token")


@pytest.mark.asyncio
async def test_scanner_stops_when_pagination_token_repeats() -> None:
    helius: Any = RepeatingTokenClient()
    scanner = TransactionScanner(helius, TokenParser(), TokenAnalyzer())

    result = await scanner.scan_address("wallet", limit=10)

    assert result == []
