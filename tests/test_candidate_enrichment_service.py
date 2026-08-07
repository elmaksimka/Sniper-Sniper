from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.candidate_enrichment_service import CandidateEnrichmentService


class FakeScores:
    async def list_leaderboard(self, **_: Any) -> list[object]:
        return [
            SimpleNamespace(
                wallet_id=1,
                score=43.2,
                wallet=SimpleNamespace(address="candidate"),
            )
        ]

    async def get_by_wallet_id(self, wallet_id: int) -> object:
        return SimpleNamespace(score=67)


class FakeMonitors:
    async def get_by_address(self, address: str) -> None:
        return None


class FakeScanner:
    async def scan_address(self, address: str, limit: int) -> list[dict[str, str]]:
        assert limit == 20
        return [{"signature": "new"}, {"signature": "old"}]


class FakeDetection:
    def __init__(self) -> None:
        self.signatures: list[str] = []

    async def process_transactions(self, transactions: list[dict[str, str]]) -> None:
        self.signatures = [item["signature"] for item in transactions]


class FakeCursors:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.saved: dict[str, object] | None = None

    async def get(self, name: str) -> object | None:
        return self.existing

    async def beat(
        self,
        name: str,
        instance_id: str,
        details: dict[str, object],
    ) -> object:
        self.saved = details
        return SimpleNamespace(details=details)


def service(cursors: FakeCursors, detection: FakeDetection) -> CandidateEnrichmentService:
    return CandidateEnrichmentService(
        scores=FakeScores(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=FakeScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        cursors=cursors,  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
    )


@pytest.mark.asyncio
async def test_candidate_history_is_ingested_oldest_first_and_promoted() -> None:
    cursors = FakeCursors()
    detection = FakeDetection()

    result = await service(cursors, detection).run_once()

    assert detection.signatures == ["old", "new"]
    assert result.wallets_enriched == 1
    assert result.transactions_processed == 2
    assert result.wallets_promoted == 1
    assert cursors.saved is not None
    assert cursors.saved["state"] == "complete"
    assert cursors.saved["score_after"] == 67


@pytest.mark.asyncio
async def test_completed_candidate_is_not_fetched_again() -> None:
    cursor = SimpleNamespace(
        details={"state": "complete"},
        last_heartbeat_at=datetime.now(UTC),
    )
    detection = FakeDetection()

    result = await service(FakeCursors(cursor), detection).run_once()

    assert result.wallets_enriched == 0
    assert detection.signatures == []
