from app.services.funding_parser import FundingParser


def test_extracts_outer_inner_and_enhanced_native_transfers() -> None:
    transaction = {
        "transaction": {
            "message": {
                "instructions": [
                    {
                        "program": "system",
                        "parsed": {
                            "type": "transfer",
                            "info": {
                                "source": "funder",
                                "destination": "wallet",
                                "lamports": 1_500_000_000,
                            },
                        },
                    },
                    {"program": "spl-token", "parsed": {"type": "transfer"}},
                ]
            }
        },
        "meta": {
            "innerInstructions": [
                {
                    "index": 2,
                    "instructions": [
                        {
                            "program": "system",
                            "parsed": {
                                "type": "transferWithSeed",
                                "info": {
                                    "source": "wallet",
                                    "destination": "next",
                                    "lamports": 250_000_000,
                                },
                            },
                        }
                    ],
                }
            ]
        },
        "nativeTransfers": [
            {
                "fromUserAccount": "enhanced-source",
                "toUserAccount": "enhanced-destination",
                "amount": 10_000_000,
            }
        ],
    }

    transfers = FundingParser().extract_transfers(transaction)

    assert [transfer.instruction_index for transfer in transfers] == [
        "outer:0",
        "inner:2:0",
        "native:0",
    ]
    assert transfers[0].source == "funder"
    assert transfers[0].destination == "wallet"
    assert transfers[0].amount_sol == 1.5
    assert transfers[1].amount_sol == 0.25
    assert transfers[2].amount_sol == 0.01


def test_ignores_malformed_and_non_positive_transfers() -> None:
    transaction = {
        "nativeTransfers": [
            {"fromUserAccount": "same", "toUserAccount": "same", "amount": 1},
            {"fromUserAccount": "source", "toUserAccount": "dest", "amount": 0},
            {"fromUserAccount": "source", "toUserAccount": "dest"},
        ]
    }

    assert FundingParser().extract_transfers(transaction) == []
