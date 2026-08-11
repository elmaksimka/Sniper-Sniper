from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.candidate_enrichment_service import CandidateEnrichmentService
from app.services.top_trader_candidate_source import (
    ExternalCandidateBatch,
    ExternalTraderCandidate,
)


class FakeScores:
    async def list_top_token_trader_candidates(
        self,
        **_: Any,
    ) -> tuple[list[object], int]:
        return await self.list_leaderboard(), 1

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

    async def get_by_wallet_address(self, address: str) -> object:
        return SimpleNamespace(score=68)


class FakeMonitors:
    def __init__(self) -> None:
        self.lookups = 0
        self.checkpoint_signature: str | None = None

    async def get_by_address(self, address: str) -> object | None:
        self.lookups += 1
        if self.lookups == 1:
            return None
        return SimpleNamespace(enabled=True)

    async def mark_success(
        self,
        monitor: object,
        checkpoint_signature: str | None,
    ) -> None:
        self.checkpoint_signature = checkpoint_signature


class FakeScanner:
    total_transactions = 2

    async def count_address_transactions(self, wallet: str) -> int:
        return self.total_transactions

    async def scan_page(
        self,
        address: str,
        limit: int,
        pagination_token: str | None,
    ) -> object:
        assert limit == 20
        return SimpleNamespace(
            transactions=[{"signature": "new"}, {"signature": "old"}],
            pagination_token=None,
        )


class FakeDetection:
    def __init__(self) -> None:
        self.signatures: list[str] = []

    async def process_transactions(self, transactions: list[dict[str, str]]) -> None:
        self.signatures = [item["signature"] for item in transactions]


class FakeCursors:
    def __init__(self, existing: object | None = None) -> None:
        self.existing = existing
        self.saved: dict[str, object] | None = None
        self.source_records: list[object] = []

    async def get(self, name: str) -> object | None:
        return self.existing

    async def beat(
        self,
        name: str,
        instance_id: str,
        details: dict[str, object],
    ) -> object:
        self.saved = details
        if name.startswith("candidate-source:"):
            self.source_records.append(
                SimpleNamespace(service_name=name, details=details)
            )
        return SimpleNamespace(details=details)

    async def list_by_prefix(self, prefix: str) -> list[object]:
        return [
            item
            for item in self.source_records
            if item.service_name.startswith(prefix)
        ]


def service(
    cursors: FakeCursors,
    detection: FakeDetection,
    scanner: FakeScanner | None = None,
) -> CandidateEnrichmentService:
    return CandidateEnrichmentService(
        scores=FakeScores(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=scanner or FakeScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        cursors=cursors,  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
    )


def test_adaptive_audit_only_stops_when_low_score_data_is_complete_enough() -> None:
    enrichment = service(FakeCursors(), FakeDetection())
    complete_low_score = SimpleNamespace(
        score=60,
        unmatched_sell_ratio=0.1,
        priced_trade_ratio=0.9,
        realized_position_count=10,
    )
    incomplete_low_score = SimpleNamespace(
        score=55,
        unmatched_sell_ratio=0.8,
        priced_trade_ratio=0.9,
        realized_position_count=10,
    )
    strong_score = SimpleNamespace(
        score=76,
        unmatched_sell_ratio=0,
        priced_trade_ratio=1,
        realized_position_count=20,
    )

    assert enrichment._should_stop_early(299, complete_low_score) is False  # type: ignore[arg-type]
    assert enrichment._should_stop_early(300, incomplete_low_score) is False  # type: ignore[arg-type]
    assert enrichment._should_stop_early(300, strong_score) is False  # type: ignore[arg-type]
    assert enrichment._should_stop_early(300, complete_low_score) is True  # type: ignore[arg-type]


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
    assert result.source_token_count == 1
    assert result.source_candidate_count == 1
    assert result.source_window_hours == 24
    assert result.audit_state == "complete"
    assert result.history_transactions_total == 2
    assert cursors.saved is not None
    assert cursors.saved["state"] == "complete"
    assert cursors.saved["score_after"] == 67


@pytest.mark.asyncio
async def test_completed_candidate_only_backfills_missing_transaction_total() -> None:
    cursor = SimpleNamespace(
        details={"state": "complete", "audit_version": 2},
        last_heartbeat_at=datetime.now(UTC),
    )
    detection = FakeDetection()
    cursors = FakeCursors(cursor)

    result = await service(cursors, detection).run_once()

    assert result.wallets_enriched == 0
    assert result.last_wallet is None
    assert detection.signatures == []
    assert cursors.saved is not None
    assert cursors.saved["transactions_available_total"] == 2


@pytest.mark.asyncio
async def test_in_progress_full_history_audit_precedes_total_count_backfill() -> None:
    class PrioritizedScores(FakeScores):
        async def list_leaderboard(self, **_: Any) -> list[object]:
            return [
                SimpleNamespace(
                    wallet_id=1,
                    score=45,
                    wallet=SimpleNamespace(address="needs-total"),
                ),
                SimpleNamespace(
                    wallet_id=2,
                    score=96,
                    wallet=SimpleNamespace(address="full-history"),
                ),
            ]

    old = datetime(2026, 1, 1, tzinfo=UTC)
    records = {
        "needs-total": SimpleNamespace(
            service_name="candidate:needs-total",
            details={"state": "complete", "audit_version": 3},
            last_heartbeat_at=old,
        ),
        "full-history": SimpleNamespace(
            service_name="candidate:full-history",
            details={
                "state": "in_progress",
                "audit_version": 3,
                "full_history_required": True,
                "pagination_token": "older-page",
                "transactions_processed_total": 100,
                "transactions_available_total": 1_000,
                "score_after": 96,
                "copy_score": 83,
            },
            last_heartbeat_at=old,
        ),
    }

    class PrioritizedCursors(FakeCursors):
        async def get(self, name: str) -> object | None:
            return records.get(name.removeprefix("candidate:"))

        async def list_by_prefix(self, prefix: str) -> list[object]:
            if prefix == "candidate:":
                return list(records.values())
            return []

    class RecordingScanner(FakeScanner):
        def __init__(self) -> None:
            self.addresses: list[str] = []

        async def scan_page(
            self,
            address: str,
            limit: int,
            pagination_token: str | None,
        ) -> object:
            self.addresses.append(address)
            return await super().scan_page(address, limit, pagination_token)

    scanner = RecordingScanner()
    enrichment = CandidateEnrichmentService(
        scores=PrioritizedScores(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=scanner,  # type: ignore[arg-type]
        detection=FakeDetection(),  # type: ignore[arg-type]
        cursors=PrioritizedCursors(),  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
    )

    result = await enrichment.run_once()

    assert scanner.addresses == ["full-history"]
    assert result.last_wallet == "full-history"


@pytest.mark.asyncio
async def test_selected_copy_grade_upgrades_capped_audit_to_full_history() -> None:
    cursor = SimpleNamespace(
        details={
            "state": "complete",
            "audit_version": 2,
            "transactions_processed_total": 1_000,
            "history_capped": True,
            "score_after": 88,
            "copy_score": 70,
        },
        last_heartbeat_at=datetime.now(UTC),
    )
    cursors = FakeCursors(cursor)

    result = await service(cursors, FakeDetection()).run_once()

    assert result.wallets_enriched == 1
    assert result.history_transactions_total == 2
    assert cursors.saved is not None
    assert cursors.saved["audit_version"] == 3
    assert cursors.saved["full_history_required"] is True
    assert cursors.saved["history_capped"] is False
    assert cursors.saved["transactions_available_total"] == 2


@pytest.mark.asyncio
async def test_selected_copy_grade_continues_past_old_thousand_transaction_cap() -> None:
    cursor = SimpleNamespace(
        details={
            "state": "in_progress",
            "audit_version": 3,
            "pagination_token": "older-page",
            "transactions_processed_total": 1_000,
            "score_after": 79,
            "copy_score": 80,
        },
        last_heartbeat_at=datetime.now(UTC),
    )
    cursors = FakeCursors(cursor)

    class LongHistoryScanner(FakeScanner):
        total_transactions = 1_002

    result = await service(
        cursors,
        FakeDetection(),
        LongHistoryScanner(),
    ).run_once()

    assert result.history_transactions_total == 1_002
    assert cursors.saved is not None
    assert cursors.saved["history_capped"] is False
    assert cursors.saved["transactions_available_total"] == 1_002


@pytest.mark.asyncio
async def test_existing_high_score_candidate_is_enriched() -> None:
    class HighScoreCandidates(FakeScores):
        async def list_leaderboard(self, **_: Any) -> list[object]:
            return [
                SimpleNamespace(
                    wallet_id=1,
                    score=88.0,
                    wallet=SimpleNamespace(address="high-score-candidate"),
                )
            ]

    detection = FakeDetection()
    enrichment = CandidateEnrichmentService(
        scores=HighScoreCandidates(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=FakeScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        cursors=FakeCursors(),  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
    )

    result = await enrichment.run_once()

    assert result.wallets_enriched == 1
    assert result.last_wallet == "high-score-candidate"
    assert detection.signatures == ["old", "new"]


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

        async def scan_page(
            self,
            address: str,
            limit: int,
            pagination_token: str | None,
        ) -> object:
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


@pytest.mark.asyncio
async def test_external_top_trader_is_enriched_before_local_candidates() -> None:
    class FakeExternalSource:
        def exclude_tokens(self, token_addresses: list[str]) -> None:
            assert token_addresses == []

        async def discover(self) -> ExternalCandidateBatch:
            return ExternalCandidateBatch(
                (
                    ExternalTraderCandidate(
                        "external-wallet",
                        profitable_tokens=2,
                        realized_pnl_usd=20_000,
                        risk_tags=(),
                    ),
                ),
                token_count=5,
                token_addresses=("source-token",),
            )

    detection = FakeDetection()
    enrichment = CandidateEnrichmentService(
        scores=FakeScores(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=FakeScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        cursors=FakeCursors(),  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
        external_source=FakeExternalSource(),  # type: ignore[arg-type]
    )

    result = await enrichment.run_once()

    assert result.last_wallet == "external-wallet"
    assert result.last_score_before is None
    assert result.last_score_after == 68
    assert result.source_token_count == 5
    assert result.source_candidate_count == 1


@pytest.mark.asyncio
async def test_candidate_history_resumes_from_saved_pagination_token() -> None:
    cursor = SimpleNamespace(
        details={
            "state": "in_progress",
            "audit_version": 2,
            "pagination_token": "before-signature",
            "transactions_processed_total": 75,
        },
        last_heartbeat_at=datetime.now(UTC),
    )

    class ResumingScanner(FakeScanner):
        async def scan_page(
            self,
            address: str,
            limit: int,
            pagination_token: str | None,
        ) -> object:
            assert pagination_token == "before-signature"
            return SimpleNamespace(
                transactions=[{"signature": "older"}],
                pagination_token=None,
            )

    enrichment = CandidateEnrichmentService(
        scores=FakeScores(),  # type: ignore[arg-type]
        monitors=FakeMonitors(),  # type: ignore[arg-type]
        scanner=ResumingScanner(),  # type: ignore[arg-type]
        detection=FakeDetection(),  # type: ignore[arg-type]
        cursors=FakeCursors(cursor),  # type: ignore[arg-type]
        minimum_score=35,
        history_limit=20,
        maximum_candidates=1,
        retry_seconds=1800,
    )

    result = await enrichment.run_once()

    assert result.audit_state == "complete"
    assert result.history_transactions_total == 76
