from __future__ import annotations

from typing import Any

from app.repositories.heartbeat_repository import HeartbeatRepository


class CandidateAuditProgressService:
    """Build Telegram-ready progress for DexScreener top-trader audits."""

    def __init__(self, heartbeats: HeartbeatRepository) -> None:
        self.heartbeats = heartbeats

    async def get(self, maximum_transactions: int) -> list[dict[str, Any]]:
        pair_rows = await self.heartbeats.list_by_prefix(
            "candidate-pair:",
            limit=5_000,
        )
        audit_rows = await self.heartbeats.list_by_prefix(
            "candidate:",
            limit=5_000,
        )
        audits = {
            row.service_name.removeprefix("candidate:"): row.details
            for row in audit_rows
            if row.service_name.startswith("candidate:")
            and not row.service_name.startswith(
                ("candidate-pair:", "candidate-source:", "candidate-discovery:")
            )
            and isinstance(row.details, dict)
        }

        pairs: list[dict[str, Any]] = []
        for row in pair_rows:
            details = row.details
            if not isinstance(details, dict):
                continue
            raw_traders = details.get("traders")
            if not isinstance(raw_traders, list):
                continue
            traders: list[dict[str, Any]] = []
            for raw_trader in raw_traders:
                if not isinstance(raw_trader, dict):
                    continue
                wallet = str(raw_trader.get("wallet", "")).strip()
                if not wallet:
                    continue
                audit = audits.get(wallet, {})
                total = self._non_negative_int(
                    audit.get("transactions_processed_total", 0)
                )
                state = str(audit.get("state", "pending"))
                history_capped = bool(audit.get("history_capped", False))
                displayed_maximum = (
                    total
                    if state == "complete" and not history_capped
                    else maximum_transactions
                )
                started = total > 0 or state == "complete"
                traders.append(
                    {
                        "rank": self._non_negative_int(
                            raw_trader.get("rank", 0)
                        ),
                        "wallet": wallet,
                        "label": str(raw_trader.get("label") or "").strip(),
                        "transactions": total,
                        "maximum_transactions": displayed_maximum,
                        "score": self._optional_float(audit.get("score_after")),
                        "state": state,
                        "started": started,
                    }
                )
            traders.sort(key=lambda trader: int(trader["rank"]))
            started_count = sum(bool(trader["started"]) for trader in traders)
            completed_count = sum(
                trader["state"] == "complete" for trader in traders
            )
            pairs.append(
                {
                    "batch_order": self._non_negative_int(
                        details.get("batch_order", 0)
                    ),
                    "symbol": str(details.get("symbol") or "").strip(),
                    "token_address": str(
                        details.get("token_address") or ""
                    ).strip(),
                    "pair_address": str(
                        details.get("pair_address") or ""
                    ).strip(),
                    "started_traders": started_count,
                    "completed_traders": completed_count,
                    "total_traders": len(traders),
                    "complete": bool(traders)
                    and completed_count == len(traders),
                    "traders": traders,
                }
            )
        pairs.sort(key=lambda pair: int(pair["batch_order"]))
        return pairs

    @staticmethod
    def _non_negative_int(value: object) -> int:
        if not isinstance(value, (int, float, str, bytes, bytearray)):
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
