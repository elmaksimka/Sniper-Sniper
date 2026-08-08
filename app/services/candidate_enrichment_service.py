from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.logging import get_logger
from app.infrastructure.models import WalletScoreSnapshot
from app.listeners.transaction_scanner import TransactionScanner
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.token_detection_service import TokenDetectionService
from app.services.top_trader_candidate_source import TopTraderCandidateSource


@dataclass(frozen=True, slots=True)
class CandidateEnrichmentResult:
    wallets_enriched: int
    transactions_processed: int
    wallets_promoted: int
    last_wallet: str | None
    last_score_before: float | None
    last_score_after: float | None
    history_limit: int
    source_token_count: int
    source_candidate_count: int
    source_window_hours: int
    audit_state: str = "idle"
    history_transactions_total: int = 0
    history_capped: bool = False


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
        source_window_hours: int = 24,
        source_token_limit: int = 25,
        source_traders_per_token: int = 10,
        source_minimum_token_trades: int = 10,
        source_minimum_token_wallets: int = 5,
        source_minimum_observed_minutes: float = 30,
        source_minimum_current_multiple: float = 3,
        source_early_entry_minutes: float = 30,
        source_early_entry_max_multiple: float = 2,
        external_source: TopTraderCandidateSource | None = None,
        maximum_history_transactions: int = 1_000,
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
        self.source_window_hours = source_window_hours
        self.source_token_limit = source_token_limit
        self.source_traders_per_token = source_traders_per_token
        self.source_minimum_token_trades = source_minimum_token_trades
        self.source_minimum_token_wallets = source_minimum_token_wallets
        self.source_minimum_observed_minutes = source_minimum_observed_minutes
        self.source_minimum_current_multiple = source_minimum_current_multiple
        self.source_early_entry_minutes = source_early_entry_minutes
        self.source_early_entry_max_multiple = source_early_entry_max_multiple
        self.external_source = external_source
        self.maximum_history_transactions = maximum_history_transactions
        self.logger = get_logger("candidate-enrichment")

    async def run_once(self) -> CandidateEnrichmentResult:
        external_addresses: list[str] = []
        external_token_count = 0
        if self.external_source is not None:
            external = await self.external_source.discover()
            for candidate in external.candidates:
                await self.cursors.beat(
                    f"candidate-source:{candidate.address}",
                    "top-trader-source",
                    {
                        "wallet": candidate.address,
                        "profitable_tokens": candidate.profitable_tokens,
                        "realized_pnl_usd": candidate.realized_pnl_usd,
                        "risk_tags": list(candidate.risk_tags),
                    },
                )
            external_token_count = external.token_count

        queued = await self.cursors.list_by_prefix("candidate-source:")
        queued.sort(
            key=lambda item: self._source_priority(item.details),
            reverse=True,
        )
        external_addresses = [
            item.service_name.removeprefix("candidate-source:")
            for item in queued
        ]

        priority_candidates, source_token_count = (
            await self.scores.list_top_token_trader_candidates(
                minimum_score=self.minimum_score,
                window_hours=self.source_window_hours,
                token_limit=self.source_token_limit,
                traders_per_token=self.source_traders_per_token,
                minimum_token_trades=self.source_minimum_token_trades,
                minimum_token_wallets=self.source_minimum_token_wallets,
                minimum_observed_minutes=(
                    self.source_minimum_observed_minutes
                ),
                minimum_current_multiple=(
                    self.source_minimum_current_multiple
                ),
                early_entry_minutes=self.source_early_entry_minutes,
                early_entry_max_multiple=(
                    self.source_early_entry_max_multiple
                ),
            )
        )
        leaderboard = await self.scores.list_leaderboard(
            limit=1000,
            offset=0,
        )
        seen_wallet_ids = {item.wallet_id for item in priority_candidates}
        snapshots = [
            *priority_candidates,
            *(
                item
                for item in leaderboard
                if item.wallet_id not in seen_wallet_ids
            ),
        ]
        candidate_rows: list[tuple[str, WalletScoreSnapshot | None]] = []
        seen_addresses: set[str] = set()
        for address in external_addresses:
            if address not in seen_addresses:
                candidate_rows.append((address, None))
                seen_addresses.add(address)
        for snapshot in snapshots:
            address = snapshot.wallet.address
            if address not in seen_addresses:
                candidate_rows.append((address, snapshot))
                seen_addresses.add(address)
        enriched = 0
        attempted = 0
        processed = 0
        promoted = 0
        last_wallet: str | None = None
        last_score_before: float | None = None
        last_score_after: float | None = None
        last_audit_state = "idle"
        last_history_total = 0
        last_history_capped = False

        for address, candidate_snapshot in candidate_rows:
            if attempted >= self.maximum_candidates:
                break
            existing_monitor = await self.monitors.get_by_address(address)
            if existing_monitor is not None and existing_monitor.enabled:
                continue
            cursor_name = f"candidate:{address}"
            cursor = await self.cursors.get(cursor_name)
            if not self._ready(cursor):
                continue
            cursor_details = getattr(cursor, "details", None)
            saved = cursor_details if isinstance(cursor_details, dict) else {}
            resumable = (
                saved.get("audit_version") == 2
                and saved.get("state") in {"in_progress", "error"}
            )
            if (
                candidate_snapshot is not None
                and candidate_snapshot.score < self.minimum_score
                and not resumable
            ):
                continue

            attempted += 1
            pagination_token = (
                saved.get("pagination_token")
                if resumable and isinstance(saved.get("pagination_token"), str)
                else None
            )
            history_total = (
                int(saved.get("transactions_processed_total", 0))
                if resumable
                else 0
            )
            try:
                remaining = max(
                    self.maximum_history_transactions - history_total,
                    0,
                )
                page = await self.scanner.scan_page(
                    address,
                    limit=min(self.history_limit, remaining),
                    pagination_token=pagination_token,
                )
                transactions = page.transactions
                if transactions:
                    await self.detection.process_transactions(
                        list(reversed(transactions))
                    )
                history_total += len(transactions)
                history_capped = (
                    history_total >= self.maximum_history_transactions
                )
                audit_complete = page.pagination_token is None or history_capped
                audit_state = "complete" if audit_complete else "in_progress"
                updated = (
                    await self.scores.get_by_wallet_id(
                        candidate_snapshot.wallet_id
                    )
                    if candidate_snapshot is not None
                    else await self.scores.get_by_wallet_address(address)
                )
                monitor = await self.monitors.get_by_address(address)
                was_promoted = bool(monitor is not None and monitor.enabled)
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
                        "state": audit_state,
                        "audit_version": 2,
                        "wallet": address,
                        "transactions_processed": len(transactions),
                        "transactions_processed_total": history_total,
                        "pagination_token": (
                            None if audit_complete else page.pagination_token
                        ),
                        "history_capped": history_capped,
                        "score_before": (
                            candidate_snapshot.score
                            if candidate_snapshot is not None
                            else None
                        ),
                        "score_after": updated.score if updated is not None else None,
                    },
                )
                enriched += 1
                processed += len(transactions)
                promoted += int(was_promoted)
                last_wallet = address
                last_score_before = (
                    candidate_snapshot.score
                    if candidate_snapshot is not None
                    else None
                )
                last_score_after = updated.score if updated is not None else None
                last_audit_state = audit_state
                last_history_total = history_total
                last_history_capped = history_capped
            except Exception as error:
                await self.cursors.beat(
                    cursor_name,
                    "candidate-enrichment",
                    {
                        "state": "error",
                        "audit_version": 2,
                        "wallet": address,
                        "error": str(error)[:256],
                        "transactions_processed_total": history_total,
                        "pagination_token": pagination_token,
                    },
                )
                self.logger.exception(
                    "candidate_enrichment_failed",
                    wallet=address,
                )

        return CandidateEnrichmentResult(
            enriched,
            processed,
            promoted,
            last_wallet,
            last_score_before,
            last_score_after,
            self.history_limit,
            external_token_count or source_token_count,
            len(external_addresses) or len(priority_candidates),
            self.source_window_hours,
            last_audit_state,
            last_history_total,
            last_history_capped,
        )

    def _ready(self, cursor: object | None) -> bool:
        if cursor is None:
            return True
        details = getattr(cursor, "details", None)
        if not isinstance(details, dict):
            return True
        if (
            details.get("state") == "complete"
            and details.get("audit_version") == 2
        ):
            return False
        if details.get("state") == "in_progress":
            return True
        last_attempt = getattr(cursor, "last_heartbeat_at", None)
        if not isinstance(last_attempt, datetime):
            return True
        if last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=UTC)
        return datetime.now(UTC) - last_attempt >= timedelta(
            seconds=self.retry_seconds
        )

    @staticmethod
    def _source_priority(details: object) -> tuple[bool, int, float]:
        if not isinstance(details, dict):
            return (False, 0, 0.0)
        risk_tags = details.get("risk_tags")
        safe = not isinstance(risk_tags, list) or not risk_tags
        try:
            profitable_tokens = int(details.get("profitable_tokens", 0))
        except (TypeError, ValueError):
            profitable_tokens = 0
        try:
            realized_pnl = float(details.get("realized_pnl_usd", 0))
        except (TypeError, ValueError):
            realized_pnl = 0.0
        return (safe, profitable_tokens, realized_pnl)
