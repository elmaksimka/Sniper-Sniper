from typing import Any

import pytest

from app.analyzer import TokenAnalyzer, TokenTrade
from app.listeners.transaction_scanner import TransactionScanner
from app.services.token_parser import TokenParser


class FakeHeliusClient:
    async def get_transactions(
        self,
        wallet: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        assert wallet == "wallet"
        assert limit == 3
        return [
            {
                "signature": "signature",
                "tokenTransfers": [
                    {
                        "mint": "mint",
                        "fromUserAccount": "sender",
                        "toUserAccount": "wallet",
                    }
                ],
                "accountData": [
                    {
                        "account": "wallet",
                        "nativeBalanceChange": -100_000_000,
                        "tokenBalanceChanges": [
                            {
                                "mint": "mint",
                                "userAccount": "wallet",
                                "rawTokenAmount": {
                                    "tokenAmount": "10",
                                    "decimals": 0,
                                },
                            }
                        ],
                    }
                ],
            }
        ]


@pytest.mark.asyncio
async def test_scanner_returns_tokens_and_normalized_trades() -> None:
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
            "timestamp": None,
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
