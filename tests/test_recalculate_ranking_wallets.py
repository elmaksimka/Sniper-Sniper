from types import SimpleNamespace

from app.recalculate_ranking_wallets import ranking_addresses


def test_ranking_addresses_only_reads_candidate_pair_traders() -> None:
    rows = [
        SimpleNamespace(
            details={
                "traders": [
                    {"wallet": "wallet-b"},
                    {"wallet": "wallet-a"},
                    {"wallet": "wallet-b"},
                    {"wallet": ""},
                ]
            }
        ),
        SimpleNamespace(details={"unrelated": "wallet-c"}),
    ]

    assert ranking_addresses(rows) == ("wallet-a", "wallet-b")
