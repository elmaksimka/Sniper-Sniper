from app.core.assets import USDC_MINT, USDT_MINT
from app.services.token_parser import SOL_MINT, TokenParser


def test_extract_tokens_filters_transfers_to_requested_wallet() -> None:
    transaction = {
        "tokenTransfers": [
            {
                "mint": "wanted-mint",
                "fromUserAccount": "sender",
                "toUserAccount": "wallet",
            },
            {
                "mint": "unrelated-mint",
                "fromUserAccount": "alice",
                "toUserAccount": "bob",
            },
            {
                "mint": SOL_MINT,
                "fromUserAccount": "sender",
                "toUserAccount": "wallet",
            },
            {
                "mint": USDC_MINT,
                "fromUserAccount": "sender",
                "toUserAccount": "wallet",
            },
            {
                "mint": USDT_MINT,
                "fromUserAccount": "sender",
                "toUserAccount": "wallet",
            },
        ]
    }

    assert TokenParser().extract_tokens(transaction, "wallet") == ["wanted-mint"]


def test_extract_tokens_uses_raw_balance_fallback() -> None:
    transaction = {
        "meta": {
            "preTokenBalances": [
                {"mint": "mint-b", "owner": "wallet"},
                {"mint": "other-mint", "owner": "other-wallet"},
            ],
            "postTokenBalances": [
                {"mint": "mint-a", "owner": "wallet"},
                {"mint": "mint-b", "owner": "wallet"},
            ],
        }
    }

    assert TokenParser().extract_tokens(transaction, "wallet") == [
        "mint-a",
        "mint-b",
    ]
