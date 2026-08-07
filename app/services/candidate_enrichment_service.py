from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.logging import get_logger
from app.listeners.transaction_scanner import TransactionScanner
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.token_detection_service import TokenDetectionService


@dataclass(frozen=True, slots=True)
class CandidateEnrichmentResult:
    wallets_enriched: int
    transactions_processed: int
    wallets_promoted: int


class CandidateEnrichmentService:
    """Backfill bounded history for the strongest not-yet-promoted wallets."""

    def __init__(
        self,
        scores: ScoreSnapshotRepository,
        monitors: MonitorRepository,
        scanner: TransactionScanner,
        detection: TokenDetectionService,
        cursors: HeartbeatRepository,
        minimum_score: float,
        history_limit: int,
        maximum_candidates: int,
        retry_seconds: float,
    ) -> None:
        self.scores = scores
        self.monitors = monitors
        self.scanner = scanner
        self.detection = detection
        self.cursors = cursors
        self.minimum_score = minimum_score
        self.history_limit = history_limit
        self.maximum_candidates = maximum_candidates
        self.retry_seconds = retry_seconds
        self.logger = get_logger("candidate-enrichment")

    async def run_once(self) -> CandidateEnrichmentResult:
        candidates = await self.scores.list_leaderboard(
            limit=1000,
            offset=0,
        )
        enriched = 0
        processed = 0
        promoted = 0

        for snapshot in candidates:
            if enriched >= self.maximum_candidates:
                break
            if snapshot.score < self.minimum_score or snapshot.score >= 65:
                continue

            address = snapshot.wallet.address
            if await self.monitors.get_by_address(address) is not None:
                continue
            cursor_name = f"candidate:{address}"
            cursor = await self.cursors.get(cursor_name)
            if not self._ready(cursor):
                continue

            try:
                transactions = await self.scanner.scan_address(
                    address,
                    limit=self.history_limit,
                )
                if transactions:
                    await self.detection.process_transactions(
                        list(reversed(transactions))
                    )
                updated = await self.scores.get_by_wallet_id(snapshot.wallet_id)
                was_promoted = bool(updated is not None and updated.score >= 65)
                monitor = await self.monitors.get_by_address(address)
                if monitor is not None and transactions:
                    newest_signature = transactions[0].get("signature")
                    await self.monitors.mark_success(
                        monitor,
                        (
                            newest_signature
                            if isinstance(newest_signature, str)
                            else None
                        ),
                    )
                await self.cursors.beat(
                    cursor_name,
                    "candidate-enrichment",
                    {
                        "state": "complete",
                        "wallet": address,
                        "transactions_processed": len(transactions),
                        "score_before": snapshot.score,
                        "score_after": updated.score if updated is not None else None,
                    },
                )
                enriched += 1
                processed += len(transactions)
                promoted += int(was_promoted)
            except Exception as error:
                await self.cursors.beat(
                    cursor_name,
                    "candidate-enrichment",
                    {
                        "state": "error",
                        "wallet": address,
                        "error": str(error)[:256],
                    },
                )
                self.logger.exception(
                    "candidate_enrichment_failed",
                    wallet=address,
                )

        return CandidateEnrichmentResult(enriched, processed, promoted)

    def _ready(self, cursor: object | None) -> bool:
        if cursor is None:
            return True
        details = getattr(cursor, "details", None)
        if not isinstance(details, dict):
            return True
        if details.get("state") == "complete":
            return False
        last_attempt = getattr(cursor, "last_heartbeat_at", None)
        if not isinstance(last_attempt, datetime):
            return True
        if last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=UTC)
        return datetime.now(UTC) - last_attempt >= timedelta(
            seconds=self.retry_seconds
        )
