from types import SimpleNamespace

import pytest

from app.services.candidate_audit_progress_service import (
    CandidateAuditProgressService,
)


class FakeHeartbeats:
    async def list_by_prefix(
        self,
        prefix: str,
        *,
        limit: int,
    ) -> list[SimpleNamespace]:
        assert limit == 5_000
        if prefix == "candidate-pair:":
            return [
                SimpleNamespace(
                    service_name="candidate-pair:token",
                    details={
                        "batch_order": 1,
                        "symbol": "TOAD",
                        "token_address": "token",
                        "pair_address": "pair",
                        "traders": [
                            {
                                "rank": 1,
                                "wallet": "wallet-1",
                                "label": "himothy",
                            },
                            {"rank": 2, "wallet": "wallet-2"},
                        ],
                    },
                )
            ]
        return [
            SimpleNamespace(
                service_name="candidate:wallet-1",
                details={
                    "state": "in_progress",
                    "transactions_processed_total": 75,
                    "score_after": 69.33,
                },
            )
        ]


@pytest.mark.asyncio
async def test_progress_combines_pair_queue_with_wallet_audits() -> None:
    result = await CandidateAuditProgressService(
        FakeHeartbeats()  # type: ignore[arg-type]
    ).get(1_000)

    assert len(result) == 1
    assert result[0]["symbol"] == "TOAD"
    assert result[0]["started_traders"] == 1
    assert result[0]["completed_traders"] == 0
    assert result[0]["complete"] is False
    assert result[0]["traders"][0] == {
        "rank": 1,
        "wallet": "wallet-1",
        "label": "himothy",
        "transactions": 75,
        "maximum_transactions": 1_000,
        "score": 69.33,
        "state": "in_progress",
        "started": True,
    }
    assert result[0]["traders"][1]["started"] is False
