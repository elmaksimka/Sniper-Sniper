from app.detectors.token_detector import TokenDetector


def test_detect_calculates_wallet_balance_changes() -> None:
    meta = {
        "preTokenBalances": [
            {
                "mint": "mint",
                "owner": "wallet",
                "uiTokenAmount": {"uiAmount": 1.5},
            },
            {
                "mint": "mint",
                "owner": "other-wallet",
                "uiTokenAmount": {"uiAmount": 100},
            },
        ],
        "postTokenBalances": [
            {
                "mint": "mint",
                "owner": "wallet",
                "uiTokenAmount": {"uiAmount": 4},
            }
        ],
    }

    assert TokenDetector().detect(meta, "wallet") == [
        {
            "mint": "mint",
            "before": 1.5,
            "after": 4.0,
            "change": 2.5,
        }
    ]
