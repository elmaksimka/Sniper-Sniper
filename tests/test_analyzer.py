import pytest

from app.analyzer import TokenAnalyzer, TokenTrade
from app.core.assets import USDC_MINT, USDT_MINT, WRAPPED_SOL_MINT


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


def test_swap_event_allocates_sol_and_fee_once_to_bought_token() -> None:
    transaction = {
        "fee": 5_000,
        "feePayer": "wallet",
        "events": {
            "swap": {
                "nativeInput": {
                    "account": "wallet",
                    "amount": "1000000000",
                },
                "tokenOutputs": [],
            }
        },
        "accountData": [
            {
                "account": "wallet",
                "nativeBalanceChange": -1_000_005_000,
                "tokenBalanceChanges": [
                    {
                        "mint": "mint",
                        "userAccount": "wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "100000000",
                            "decimals": 6,
                        },
                    }
                ],
            }
        ],
    }

    trades = TokenAnalyzer().analyze_transaction(transaction, "wallet")

    assert trades == [
        TokenTrade(
            mint="mint",
            wallet="wallet",
            sol_change=-1.000005,
            token_change=100,
        )
    ]


def test_token_to_token_swap_does_not_treat_network_fee_as_cost() -> None:
    transaction = {
        "fee": 5_000,
        "feePayer": "wallet",
        "events": {
            "swap": {
                "tokenInputs": [{}],
                "tokenOutputs": [{}],
            }
        },
        "accountData": [
            {
                "account": "wallet",
                "nativeBalanceChange": -5_000,
                "tokenBalanceChanges": [
                    {
                        "mint": "input-mint",
                        "userAccount": "wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "-10",
                            "decimals": 0,
                        },
                    },
                    {
                        "mint": "output-mint",
                        "userAccount": "wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "20",
                            "decimals": 0,
                        },
                    },
                ],
            }
        ],
    }

    trades = TokenAnalyzer().analyze_transaction(transaction, "wallet")

    assert trades == [
        TokenTrade("input-mint", "wallet", 0.0, -10.0),
        TokenTrade("output-mint", "wallet", 0.0, 20.0),
    ]


def test_ambiguous_multi_token_buy_does_not_duplicate_sol() -> None:
    transaction = {
        "fee": 5_000,
        "feePayer": "wallet",
        "events": {
            "swap": {
                "nativeInput": {
                    "account": "wallet",
                    "amount": "1000000000",
                }
            }
        },
        "accountData": [
            {
                "account": "wallet",
                "nativeBalanceChange": -1_000_005_000,
                "tokenBalanceChanges": [
                    {
                        "mint": "mint-a",
                        "userAccount": "wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "10",
                            "decimals": 0,
                        },
                    },
                    {
                        "mint": "mint-b",
                        "userAccount": "wallet",
                        "rawTokenAmount": {
                            "tokenAmount": "20",
                            "decimals": 0,
                        },
                    },
                ],
            }
        ],
    }

    trades = TokenAnalyzer().analyze_transaction(transaction, "wallet")

    assert sum(trade.sol_change for trade in trades) == 0
    assert {trade.mint for trade in trades} == {"mint-a", "mint-b"}


def test_token_transfer_removes_fee_only_balance_change() -> None:
    transaction = {
        "fee": 5_000,
        "feePayer": "wallet",
        "accountData": [
            {
                "account": "wallet",
                "nativeBalanceChange": -5_000,
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

    trades = TokenAnalyzer().analyze_transaction(transaction, "wallet")

    assert trades[0].sol_change == 0


def test_quote_assets_are_not_emitted_as_trades() -> None:
    transaction = {
        "accountData": [
            {
                "account": "wallet",
                "nativeBalanceChange": 0,
                "tokenBalanceChanges": [
                    {
                        "mint": WRAPPED_SOL_MINT,
                        "userAccount": "wallet",
                        "rawTokenAmount": {"tokenAmount": "-1", "decimals": 0},
                    },
                    {
                        "mint": USDC_MINT,
                        "userAccount": "wallet",
                        "rawTokenAmount": {"tokenAmount": "-1", "decimals": 0},
                    },
                    {
                        "mint": USDT_MINT,
                        "userAccount": "wallet",
                        "rawTokenAmount": {"tokenAmount": "-1", "decimals": 0},
                    },
                    {
                        "mint": "target-mint",
                        "userAccount": "wallet",
                        "rawTokenAmount": {"tokenAmount": "10", "decimals": 0},
                    },
                ],
            }
        ]
    }

    assert TokenAnalyzer().analyze_transaction(transaction, "wallet") == [
        TokenTrade("target-mint", "wallet", 0.0, 10.0)
    ]
