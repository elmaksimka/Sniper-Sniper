from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.copy_trading import CopyTradingScoreCalculator
from app.core.logging import get_logger
from app.infrastructure.models import WalletScoreSnapshot
from app.listeners.transaction_scanner import TransactionScanner
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.token_detection_service import TokenDetectionService
from app.services.top_trader_candidate_source import TopTraderCandidateSource
from app.services.trader_style_service import TraderStyleService


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

    H24_DISCOVERY_CURSOR = "candidate-discovery:dexscreener-h24"
    EXTERNAL_QUEUE_VERSION = 4

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
        adaptive_initial_transactions: int = 300,
        adaptive_continuation_score: float = 75,
        adaptive_max_unmatched_sell_ratio: float = 0.25,
        adaptive_min_realized_positions: int = 5,
        adaptive_min_priced_trade_ratio: float = 0.6,
        trader_style: TraderStyleService | None = None,
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
        self.adaptive_initial_transactions = adaptive_initial_transactions
        self.adaptive_continuation_score = adaptive_continuation_score
        self.adaptive_max_unmatched_sell_ratio = adaptive_max_unmatched_sell_ratio
        self.adaptive_min_realized_positions = adaptive_min_realized_positions
        self.adaptive_min_priced_trade_ratio = adaptive_min_priced_trade_ratio
        self.trader_style = trader_style
        self.copy_score_calculator = CopyTradingScoreCalculator()
        self.logger = get_logger("candidate-enrichment")

    async def run_once(self) -> CandidateEnrichmentResult:
        external_addresses: list[str] = []
        external_token_count = 0
        if self.external_source is not None:
            discovery_cursor = await self.cursors.get(self.H24_DISCOVERY_CURSOR)
            discovery_details = getattr(discovery_cursor, "details", None)
            processed_tokens = (
                [str(token) for token in discovery_details.get("tokens", [])]
                if isinstance(discovery_details, dict)
                and isinstance(discovery_details.get("tokens"), list)
                else []
            )
            self.external_source.exclude_tokens(processed_tokens)
            external = await self.external_source.discover()
            if not external.token_addresses and processed_tokens:
                processed_tokens = []
                self.external_source.exclude_tokens(processed_tokens)
                external = await self.external_source.discover()
            if external.token_addresses:
                processed_tokens.extend(external.token_addresses)
                await self.cursors.beat(
                    self.H24_DISCOVERY_CURSOR,
                    "dexscreener-h24",
                    {"tokens": list(dict.fromkeys(processed_tokens))},
                )
            batch_order = int(datetime.now(UTC).timestamp() * 1_000)
            for pair in external.pairs:
                await self.cursors.beat(
                    f"candidate-pair:{pair.token_address}",
                    "dexscreener-pair-audit",
                    {
                        "queue_version": self.EXTERNAL_QUEUE_VERSION,
                        "batch_order": batch_order,
                        "pair_address": pair.pair_address,
                        "token_address": pair.token_address,
                        "symbol": pair.symbol,
                        "traders": [
                            {
                                "rank": candidate.trader_rank,
                                "wallet": candidate.address,
                                "label": candidate.label,
                                "realized_pnl_usd": (candidate.realized_pnl_usd),
                            }
                            for candidate in pair.candidates
                        ],
                    },
                )
            for candidate in external.candidates:
                source_name = f"candidate-source:{candidate.address}"
                existing_source = await self.cursors.get(source_name)
                existing_details = getattr(existing_source, "details", None)
                if (
                    isinstance(existing_details, dict)
                    and existing_details.get("queue_version")
                    == self.EXTERNAL_QUEUE_VERSION
                ):
                    known_tokens = existing_details.get("source_tokens")
                    source_tokens = (
                        [str(token) for token in known_tokens]
                        if isinstance(known_tokens, list)
                        else [str(existing_details.get("source_token", ""))]
                    )
                    if candidate.source_token_address in source_tokens:
                        continue
                    source_tokens.append(candidate.source_token_address)
                    await self.cursors.beat(
                        source_name,
                        "top-trader-source",
                        {
                            **existing_details,
                            "source_tokens": source_tokens,
                            "profitable_tokens": int(
                                existing_details.get("profitable_tokens", 1)
                            )
                            + 1,
                            "realized_pnl_usd": float(
                                existing_details.get("realized_pnl_usd", 0)
                            )
                            + candidate.realized_pnl_usd,
                        },
                    )
                    continue
                await self.cursors.beat(
                    source_name,
                    "top-trader-source",
                    {
                        "queue_version": self.EXTERNAL_QUEUE_VERSION,
                        "batch_order": batch_order,
                        "token_rank": candidate.token_rank,
                        "trader_rank": candidate.trader_rank,
                        "source_token": candidate.source_token_address,
                        "source_tokens": [candidate.source_token_address],
                        "wallet": candidate.address,
                        "profitable_tokens": candidate.profitable_tokens,
                        "realized_pnl_usd": candidate.realized_pnl_usd,
                        "risk_tags": list(candidate.risk_tags),
                        "label": candidate.label,
                    },
                )
            external_token_count = external.token_count

        queued = [
            item
            for item in await self.cursors.list_by_prefix("candidate-source:")
            if isinstance(item.details, dict)
            and item.details.get("queue_version") == self.EXTERNAL_QUEUE_VERSION
        ]
        queued.sort(
            key=lambda item: self._source_priority(item.details),
        )
        external_addresses = [
            item.service_name.removeprefix("candidate-source:") for item in queued
        ]
        external_address_set = set(external_addresses)

        (
            priority_candidates,
            source_token_count,
        ) = await self.scores.list_top_token_trader_candidates(
            minimum_score=self.minimum_score,
            window_hours=self.source_window_hours,
            token_limit=self.source_token_limit,
            traders_per_token=self.source_traders_per_token,
            minimum_token_trades=self.source_minimum_token_trades,
            minimum_token_wallets=self.source_minimum_token_wallets,
            minimum_observed_minutes=(self.source_minimum_observed_minutes),
            minimum_current_multiple=(self.source_minimum_current_multiple),
            early_entry_minutes=self.source_early_entry_minutes,
            early_entry_max_multiple=(self.source_early_entry_max_multiple),
        )
        leaderboard = await self.scores.list_leaderboard(
            limit=1000,
            offset=0,
        )
        seen_wallet_ids = {item.wallet_id for item in priority_candidates}
        snapshots = [
            *priority_candidates,
            *(item for item in leaderboard if item.wallet_id not in seen_wallet_ids),
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
        audit_cursors = await self.cursors.list_by_prefix("candidate:")
        cursors_by_address = {
            item.service_name.removeprefix("candidate:"): item
            for item in audit_cursors
            if item.service_name.startswith("candidate:")
        }
        candidate_rows.sort(
            key=lambda item: self._candidate_priority(cursors_by_address.get(item[0]))
        )
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
            cursor_name = f"candidate:{address}"
            cursor = cursors_by_address.get(address)
            if cursor is None:
                cursor = await self.cursors.get(cursor_name)
            cursor_details = getattr(cursor, "details", None)
            saved = cursor_details if isinstance(cursor_details, dict) else {}
            full_history_upgrade = (
                self._is_selected_copy_grade(saved)
                and saved.get("state") == "complete"
                and saved.get("audit_version") != 3
            )
            missing_transaction_total = (
                self._optional_non_negative_int(
                    saved.get("transactions_available_total")
                )
                is None
            )
            if (
                missing_transaction_total
                and saved.get("state") == "complete"
                and not full_history_upgrade
            ):
                attempted += 1
                try:
                    available_total = await self.scanner.count_address_transactions(
                        address
                    )
                    await self.cursors.beat(
                        cursor_name,
                        "candidate-enrichment",
                        {
                            **saved,
                            "transactions_available_total": available_total,
                        },
                    )
                except Exception:
                    self.logger.exception(
                        "candidate_transaction_count_failed",
                        wallet=address,
                    )
                continue
            existing_monitor = await self.monitors.get_by_address(address)
            if existing_monitor is not None and existing_monitor.enabled:
                if address not in external_address_set and not full_history_upgrade:
                    continue
                if (
                    saved.get("state") == "complete"
                    and saved.get("audit_version") in {2, 3}
                    and not full_history_upgrade
                ):
                    continue
            if not full_history_upgrade and not self._ready(cursor):
                if address in external_address_set and saved.get("state") in {
                    "in_progress",
                    "error",
                }:
                    break
                continue
            resumable = saved.get("audit_version") in {2, 3} and saved.get("state") in {
                "in_progress",
                "error",
            }
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
                int(saved.get("transactions_processed_total", 0)) if resumable else 0
            )
            try:
                saved_full_history = self._is_selected_copy_grade(saved)
                remaining = (
                    self.history_limit
                    if saved_full_history
                    else max(self.maximum_history_transactions - history_total, 0)
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
                updated = (
                    await self.scores.get_by_wallet_id(candidate_snapshot.wallet_id)
                    if candidate_snapshot is not None
                    else await self.scores.get_by_wallet_address(address)
                )
                copy_assessment = None
                if updated is not None and self.trader_style is not None:
                    style = await self.trader_style.evaluate(address)
                    copy_assessment = self.copy_score_calculator.calculate(
                        updated,
                        style,
                    )
                full_history_required = saved_full_history or self._is_selected_scores(
                    updated.score if updated is not None else None,
                    copy_assessment.score if copy_assessment is not None else None,
                )
                available_total = self._optional_non_negative_int(
                    saved.get("transactions_available_total")
                )
                if available_total is None:
                    available_total = await self.scanner.count_address_transactions(
                        address
                    )
                history_capped = (
                    history_total >= self.maximum_history_transactions
                    and not full_history_required
                )
                early_stopped = (
                    False
                    if full_history_required
                    else self._should_stop_early(history_total, updated)
                )
                audit_complete = (
                    page.pagination_token is None or history_capped or early_stopped
                )
                audit_state = "complete" if audit_complete else "in_progress"
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
                        "audit_version": 3,
                        "wallet": address,
                        "transactions_processed": len(transactions),
                        "transactions_processed_total": history_total,
                        "pagination_token": (
                            None if audit_complete else page.pagination_token
                        ),
                        "history_capped": history_capped,
                        "early_stopped": early_stopped,
                        "full_history_required": full_history_required,
                        "transactions_available_total": (
                            available_total
                            if available_total is not None
                            else history_total
                            if page.pagination_token is None
                            else None
                        ),
                        "score_before": (
                            candidate_snapshot.score
                            if candidate_snapshot is not None
                            else None
                        ),
                        "score_after": updated.score if updated is not None else None,
                        "copy_score": (
                            copy_assessment.score
                            if copy_assessment is not None
                            else None
                        ),
                        "copy_mode": (
                            copy_assessment.mode
                            if copy_assessment is not None
                            else None
                        ),
                    },
                )
                enriched += 1
                processed += len(transactions)
                promoted += int(was_promoted)
                last_wallet = address
                last_score_before = (
                    candidate_snapshot.score if candidate_snapshot is not None else None
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
                        "audit_version": 3,
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

    def _should_stop_early(
        self,
        history_total: int,
        snapshot: WalletScoreSnapshot | None,
    ) -> bool:
        if history_total < self.adaptive_initial_transactions or snapshot is None:
            return False
        if snapshot.score >= self.adaptive_continuation_score:
            return False
        return (
            snapshot.unmatched_sell_ratio <= self.adaptive_max_unmatched_sell_ratio
            and snapshot.priced_trade_ratio >= self.adaptive_min_priced_trade_ratio
            and snapshot.realized_position_count >= self.adaptive_min_realized_positions
        )

    @classmethod
    def _is_selected_copy_grade(cls, details: dict[str, object]) -> bool:
        return cls._is_selected_scores(
            details.get("score_after"),
            details.get("copy_score"),
        )

    @staticmethod
    def _is_selected_scores(main_score: object, copy_score: object) -> bool:
        try:
            main = float(main_score)  # type: ignore[arg-type]
            copy = float(copy_score)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
        return (main >= 80 and copy >= 55) or (65 <= main < 80 and copy >= 75)

    @staticmethod
    def _optional_non_negative_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return max(0, int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _ready(self, cursor: object | None) -> bool:
        if cursor is None:
            return True
        details = getattr(cursor, "details", None)
        if not isinstance(details, dict):
            return True
        if details.get("state") == "complete" and details.get("audit_version") == 2:
            return False
        if details.get("state") == "in_progress":
            return True
        last_attempt = getattr(cursor, "last_heartbeat_at", None)
        if not isinstance(last_attempt, datetime):
            return True
        if last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=UTC)
        return datetime.now(UTC) - last_attempt >= timedelta(seconds=self.retry_seconds)

    @classmethod
    def _candidate_priority(cls, cursor: object | None) -> tuple[int, datetime]:
        details = getattr(cursor, "details", None)
        selected_full_history = isinstance(details, dict) and (
            (
                details.get("state") in {"in_progress", "error"}
                and (
                    details.get("full_history_required") is True
                    or cls._is_selected_copy_grade(details)
                )
            )
            or (
                details.get("state") == "complete"
                and details.get("audit_version") != 3
                and cls._is_selected_copy_grade(details)
            )
        )
        last_attempt = getattr(cursor, "last_heartbeat_at", None)
        if not isinstance(last_attempt, datetime):
            last_attempt = datetime.min.replace(tzinfo=UTC)
        elif last_attempt.tzinfo is None:
            last_attempt = last_attempt.replace(tzinfo=UTC)
        return (0 if selected_full_history else 1, last_attempt)

    @staticmethod
    def _source_priority(details: object) -> tuple[int, int, int]:
        if (
            not isinstance(details, dict)
            or details.get("queue_version")
            != CandidateEnrichmentService.EXTERNAL_QUEUE_VERSION
        ):
            return (2**63 - 1, 0, 0)
        try:
            batch_order = int(details.get("batch_order", 0))
        except (TypeError, ValueError):
            batch_order = 0
        try:
            token_rank = int(details.get("token_rank", 0))
        except (TypeError, ValueError):
            token_rank = 0
        try:
            trader_rank = int(details.get("trader_rank", 0))
        except (TypeError, ValueError):
            trader_rank = 0
        return (batch_order, token_rank, trader_rank)
