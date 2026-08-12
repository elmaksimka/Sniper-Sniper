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
                    "copy_score": 61.25,
                    "copy_mode": "manual",
                },
            ),
            SimpleNamespace(
                service_name="candidate:wallet-2",
                details={
                    "state": "complete",
                    "transactions_processed_total": 330,
                    "transactions_available_total": 320,
                    "history_capped": False,
                    "score_after": 95.7,
                },
            ),
        ]


@pytest.mark.asyncio
async def test_progress_combines_pair_queue_with_wallet_audits() -> None:
    result = await CandidateAuditProgressService(
        FakeHeartbeats()  # type: ignore[arg-type]
    ).get(1_000)

    assert len(result) == 1
    assert result[0]["symbol"] == "TOAD"
    assert result[0]["started_traders"] == 2
    assert result[0]["completed_traders"] == 1
    assert result[0]["complete"] is False
    assert result[0]["traders"][0] == {
        "rank": 1,
        "wallet": "wallet-1",
        "label": "himothy",
        "transactions": 75,
        "total_transactions": None,
        "maximum_transactions": 1_000,
        "score": 69.33,
        "copy_score": 61.25,
        "copy_mode": "manual",
        "state": "in_progress",
        "early_stopped": False,
        "started": True,
    }
    assert result[0]["traders"][1]["started"] is True
    assert result[0]["traders"][1]["transactions"] == 330
    assert result[0]["traders"][1]["total_transactions"] == 330
    assert result[0]["traders"][1]["maximum_transactions"] == 330


def test_early_stopped_audit_keeps_configured_maximum_in_display() -> None:
    assert (
        CandidateAuditProgressService._displayed_maximum(
            total=300,
            state="complete",
            history_capped=False,
            early_stopped=True,
            maximum_transactions=1_000,
        )
        == 1_000
    )
    assert (
        CandidateAuditProgressService._displayed_maximum(
            total=330,
            state="complete",
            history_capped=False,
            early_stopped=False,
            maximum_transactions=1_000,
        )
        == 330
    )
