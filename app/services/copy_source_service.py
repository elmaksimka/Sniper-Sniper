from __future__ import annotations

from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.services.monitor_service import MonitorService


class CopySourceService:
    """Select known automatic sources that passed paper-trading probation."""

    def __init__(
        self,
        heartbeats: HeartbeatRepository,
        monitors: MonitorService | None = None,
        scores: ScoreSnapshotRepository | None = None,
    ) -> None:
        self.heartbeats = heartbeats
        self.monitors = monitors
        self.scores = scores

    async def list_addresses(self) -> tuple[str, ...]:
        rows = await self.heartbeats.list_by_prefix("candidate:", limit=5_000)
        addresses: set[str] = set()
        for row in rows:
            if row.service_name.startswith(
                ("candidate-pair:", "candidate-source:", "candidate-discovery:")
            ) or not isinstance(row.details, dict):
                continue
            if not self._is_automatic_candidate(row.details):
                continue
            address = row.service_name.removeprefix("candidate:").strip()
            if not address:
                continue
            if self.scores is not None:
                snapshot = await self.scores.get_by_wallet_address(address)
                if snapshot is None or not self._passed_probation(snapshot):
                    continue
            addresses.add(address)
        return tuple(sorted(addresses))

    async def reconcile(self) -> tuple[str, ...]:
        addresses = await self.list_addresses()
        if self.monitors is not None:
            for address in addresses:
                await self.monitors.add(address)
        return addresses

    @staticmethod
    def _is_automatic_candidate(details: dict[str, object]) -> bool:
        try:
            return (
                str(details.get("copy_mode") or "").strip() == "automatic"
                and float(str(details.get("score_after", 0))) >= 60
                and float(str(details.get("copy_score", 0))) >= 75
            )
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _passed_probation(snapshot: object) -> bool:
        return (
            int(getattr(snapshot, "realized_position_count", 0)) >= 2
            and float(getattr(snapshot, "realized_pnl_sol", 0)) > 0
            and float(getattr(snapshot, "realized_pnl_ex_top_position_sol", 0)) > 0
            and float(getattr(snapshot, "pnl_concentration_ratio", 1)) <= 0.85
        )
