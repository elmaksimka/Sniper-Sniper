from __future__ import annotations

from datetime import datetime
from typing import Any

from app.repositories.heartbeat_repository import HeartbeatRepository
from app.services.candidate_audit_progress_service import (
    CandidateAuditProgressService,
)


class CopyGradeDashboardService:
    """Build a deduplicated dashboard of audited copy-trading candidates."""

    GROUPS = ("A/A", "B/A", "A/B")

    def __init__(
        self,
        heartbeats: HeartbeatRepository,
        maximum_transactions: int = 1_000,
    ) -> None:
        self.heartbeats = heartbeats
        self.maximum_transactions = maximum_transactions

    async def get(self) -> dict[str, Any]:
        rows = await self.heartbeats.list_by_prefix("candidate:", limit=5_000)
        pairs = await CandidateAuditProgressService(self.heartbeats).get(
            self.maximum_transactions
        )
        groups: dict[str, list[dict[str, Any]]] = {
            grade_pair: [] for grade_pair in self.GROUPS
        }
        updated_at: datetime | None = None
        for row in rows:
            if row.service_name.startswith(
                ("candidate-pair:", "candidate-source:", "candidate-discovery:")
            ):
                continue
            if not isinstance(row.details, dict):
                continue
            main_score = self._optional_float(row.details.get("score_after"))
            copy_score = self._optional_float(row.details.get("copy_score"))
            if main_score is None or copy_score is None:
                continue
            main_grade = self._main_grade(main_score)
            copy_grade = self._copy_grade(copy_score)
            grade_pair = f"{main_grade}/{copy_grade}"
            if grade_pair not in groups:
                continue
            wallet = row.service_name.removeprefix("candidate:").strip()
            if not wallet:
                continue
            groups[grade_pair].append(
                {
                    "wallet": wallet,
                    "main_score": round(main_score, 2),
                    "copy_score": round(copy_score, 2),
                    "main_grade": main_grade,
                    "copy_grade": copy_grade,
                    "copy_mode": str(row.details.get("copy_mode") or "").strip(),
                    "transactions": self._non_negative_int(
                        row.details.get("transactions_processed_total")
                    ),
                    "total_transactions": self._optional_non_negative_int(
                        row.details.get("transactions_available_total")
                    ),
                    "updated_at": row.last_heartbeat_at,
                }
            )
            if updated_at is None or row.last_heartbeat_at > updated_at:
                updated_at = row.last_heartbeat_at

        token_total = len(pairs)
        tokens_completed = sum(bool(pair.get("complete")) for pair in pairs)

        tokens = []
        for pair in pairs:
            traders = []
            for trader in pair.get("traders", []):
                main_score = self._optional_float(trader.get("score"))
                copy_score = self._optional_float(trader.get("copy_score"))
                traders.append(
                    {
                        "rank": self._non_negative_int(trader.get("rank")),
                        "wallet": str(trader.get("wallet") or "").strip(),
                        "label": str(trader.get("label") or "").strip(),
                        # Keep the source precision in token details. The rounded
                        # values above are only for the aggregate wallet table.
                        "main_score": main_score,
                        "copy_score": copy_score,
                        "main_grade": (
                            self._main_grade(main_score)
                            if main_score is not None
                            else None
                        ),
                        "copy_grade": (
                            self._copy_grade(copy_score)
                            if copy_score is not None
                            else None
                        ),
                        "copy_mode": str(trader.get("copy_mode") or "").strip(),
                        "transactions": self._non_negative_int(
                            trader.get("transactions")
                        ),
                        "total_transactions": self._optional_non_negative_int(
                            trader.get("total_transactions")
                        ),
                        "maximum_transactions": self._non_negative_int(
                            trader.get("maximum_transactions")
                        ),
                        "state": str(trader.get("state") or "pending"),
                        "started": bool(trader.get("started")),
                    }
                )
            tokens.append(
                {
                    "batch_order": self._non_negative_int(pair.get("batch_order")),
                    "symbol": str(pair.get("symbol") or "").strip(),
                    "token_address": str(pair.get("token_address") or "").strip(),
                    "pair_address": str(pair.get("pair_address") or "").strip(),
                    "complete": bool(pair.get("complete")),
                    "started_traders": self._non_negative_int(
                        pair.get("started_traders")
                    ),
                    "completed_traders": self._non_negative_int(
                        pair.get("completed_traders")
                    ),
                    "total_traders": self._non_negative_int(
                        pair.get("total_traders")
                    ),
                    "traders": traders,
                }
            )

        result_groups = []
        for grade_pair in self.GROUPS:
            items = groups[grade_pair]
            items.sort(
                key=lambda item: (
                    -float(item["main_score"]),
                    -float(item["copy_score"]),
                    str(item["wallet"]),
                )
            )
            result_groups.append(
                {
                    "grade_pair": grade_pair,
                    "count": len(items),
                    "items": items,
                }
            )
        return {
            "updated_at": updated_at,
            "total": sum(group["count"] for group in result_groups),
            "tokens_total": token_total,
            "tokens_completed": tokens_completed,
            "tokens_in_progress": token_total - tokens_completed,
            "tokens": tokens,
            "groups": result_groups,
        }

    @staticmethod
    def _main_grade(score: float) -> str:
        if score >= 80:
            return "A"
        if score >= 65:
            return "B"
        return "C"

    @staticmethod
    def _copy_grade(score: float) -> str:
        if score >= 75:
            return "A"
        if score >= 55:
            return "B"
        return "C"

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _non_negative_int(value: object) -> int:
        try:
            return max(0, int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _optional_non_negative_int(value: object) -> int | None:
        if value is None:
            return None
        try:
            return max(0, int(value))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
