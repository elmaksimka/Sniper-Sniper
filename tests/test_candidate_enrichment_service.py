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
    assert result.last_wallet == "candidate"
    assert result.last_score_before == 43.2
    assert result.last_score_after == 67
    assert result.history_limit == 20
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
    assert result.last_wallet is None
    assert detection.signatures == []


@pytest.mark.asyncio
async def test_failed_candidates_are_bounded_by_attempt_limit() -> None:
    class MultipleScores(FakeScores):
        async def list_leaderboard(self, **_: Any) -> list[object]:
            return [
                SimpleNamespace(
                    wallet_id=index,
                    score=43.2,
                    wallet=SimpleNamespace(address=f"candidate-{index}"),
                )
                for index in range(3)
            ]

    class FailingScanner(FakeScanner):
        def __init__(self) -> None:
            self.calls = 0

        async def scan_address(
            self,
            address: str,
            limit: int,
        ) -> list[dict[str, str]]:
            self.calls += 1
            raise RuntimeError("rate limited")

    scanner = FailingScanner()
    enrichment = CandidateEnrichmentService(
        scores=MultipleScores(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=scanner,  # type: ignore[arg-type]
        detection=FakeDetection(),  # type: ignore[arg-type]
        cursors=FakeCursors(),  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
    )

    result = await enrichment.run_once()

    assert scanner.calls == 1
    assert result.wallets_enriched == 0
