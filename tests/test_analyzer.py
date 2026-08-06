import pytest

from app.analyzer import TokenAnalyzer, TokenTrade


def test_analyze_enhanced_transaction_buy() -> None:
    transaction = {
        "accountData": [
            {
                "account": "wallet",
                "nativeBalanceChange": -500_000_000,
                "tokenBalanceChanges": [
                    {
                        "mint": "mint",
                        "userAccount": "wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "2500000",
                            "decimals": 6,
                        },
                    },
                    {
                        "mint": "other-mint",
                        "userAccount": "other-wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "10",
                            "decimals": 0,
                        },
                    },
                ],
            }
        ]
    }

    trades = TokenAnalyzer().analyze_transaction(transaction, "wallet")

    assert trades == [
        TokenTrade(
            mint="mint",
            wallet="wallet",
            sol_change=-0.5,
            token_change=2.5,
        )
    ]
    assert trades[0].side == "buy"


def test_analyze_raw_transaction_detects_sale_to_zero() -> None:
    transaction = {
        "transaction": {
            "message": {
                "accountKeys": [
                    {"pubkey": "wallet", "signer": True},
                    "other-wallet",
                ]
            }
        },
        "meta": {
            "preBalances": [2_000_000_000, 0],
            "postBalances": [2_250_000_000, 0],
            "preTokenBalances": [
                {
                    "mint": "mint",
                    "owner": "wallet",
                    "uiTokenAmount": {
                        "uiAmount": None,
                        "uiAmountString": "3.25",
                    },
                }
            ],
            "postTokenBalances": [],
        },
    }

    trades = TokenAnalyzer().analyze_transaction(transaction, "wallet")

    assert trades == [
        TokenTrade(
            mint="mint",
            wallet="wallet",
            sol_change=0.25,
            token_change=-3.25,
        )
    ]
    assert trades[0].side == "sell"


@pytest.mark.parametrize("transaction", [{}, {"meta": {}}])
def test_analyze_transaction_without_changes_returns_empty_list(
    transaction: dict,
) -> None:
    assert TokenAnalyzer().analyze_transaction(transaction, "wallet") == []
