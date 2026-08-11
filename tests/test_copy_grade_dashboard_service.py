from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.copy_grade_dashboard_service import CopyGradeDashboardService


class FakeHeartbeats:
    async def list_by_prefix(self, prefix: str, *, limit: int) -> list[SimpleNamespace]:
        assert limit == 5_000
        now = datetime.now(UTC)
        if prefix == "candidate-pair:":
            return [
                SimpleNamespace(
                    service_name="candidate-pair:one",
                    details={
                        "batch_order": 1,
                        "symbol": "ONE",
                        "traders": [{"rank": 1, "wallet": "wallet-aa"}],
                    },
                    last_heartbeat_at=now,
                ),
                SimpleNamespace(
                    service_name="candidate-pair:two",
                    details={
                        "batch_order": 2,
                        "symbol": "TWO",
                        "traders": [{"rank": 1, "wallet": "wallet-ba"}],
                    },
                    last_heartbeat_at=now,
                ),
            ]
        assert prefix == "candidate:"
        return [
            self.row("wallet-aa", 91.234, 80.126, "manual", 1000, now),
            self.row("wallet-ba", 79.17, 75.49, "manual", 1000, now),
            self.row("wallet-ab", 88.0, 72.5, "manual", 500, now),
            self.row("wallet-bb", 70.0, 60.0, "manual", 300, now),
            self.row("wallet-cc", 40.0, 40.0, "unsuitable", 20, now),
            SimpleNamespace(
                service_name="candidate-pair:token",
                details={"score_after": 99, "copy_score": 99},
                last_heartbeat_at=now + timedelta(seconds=1),
            ),
        ]

    @staticmethod
    def row(
        wallet: str,
        main: float,
        copy: float,
        mode: str,
        transactions: int,
        updated_at: datetime,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            service_name=f"candidate:{wallet}",
            details={
                "score_after": main,
                "copy_score": copy,
                "copy_mode": mode,
                "transactions_processed_total": transactions,
                "state": "complete" if wallet == "wallet-aa" else "in_progress",
            },
            last_heartbeat_at=updated_at,
        )


@pytest.mark.asyncio
async def test_dashboard_returns_selected_copy_grade_groups() -> None:
    result = await CopyGradeDashboardService(FakeHeartbeats()).get()  # type: ignore[arg-type]

    assert result["total"] == 3
    assert result["tokens_total"] == 2
    assert result["tokens_completed"] == 1
    assert result["tokens_in_progress"] == 1
    assert [token["symbol"] for token in result["tokens"]] == ["ONE", "TWO"]
    assert result["tokens"][0]["traders"][0]["main_score"] == 91.234
    assert result["tokens"][0]["traders"][0]["copy_score"] == 80.126
    assert [group["grade_pair"] for group in result["groups"]] == [
        "A/A",
        "B/A",
        "A/B",
    ]
    assert [group["count"] for group in result["groups"]] == [1, 1, 1]
    aa_wallet = result["groups"][0]["items"][0]
    assert aa_wallet["wallet"] == "wallet-aa"
    assert aa_wallet["main_score"] == 91.23
    assert aa_wallet["copy_score"] == 80.13
    assert aa_wallet["transactions"] == 1000
