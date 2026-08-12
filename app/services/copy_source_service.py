from __future__ import annotations

from app.repositories.heartbeat_repository import HeartbeatRepository
from app.services.monitor_service import MonitorService


class CopySourceService:
    """Keep live paper-copy sources aligned with the current A/A grade."""

    def __init__(
        self,
        heartbeats: HeartbeatRepository,
        monitors: MonitorService | None = None,
    ) -> None:
        self.heartbeats = heartbeats
        self.monitors = monitors

    async def list_addresses(self) -> tuple[str, ...]:
        rows = await self.heartbeats.list_by_prefix("candidate:", limit=5_000)
        addresses: set[str] = set()
        for row in rows:
            if row.service_name.startswith(
                ("candidate-pair:", "candidate-source:", "candidate-discovery:")
            ) or not isinstance(row.details, dict):
                continue
            if not self._is_aa(row.details):
                continue
            address = row.service_name.removeprefix("candidate:").strip()
            if address:
                addresses.add(address)
        return tuple(sorted(addresses))

    async def reconcile(self) -> tuple[str, ...]:
        addresses = await self.list_addresses()
        if self.monitors is not None:
            for address in addresses:
                await self.monitors.add(address)
        return addresses

    @staticmethod
    def _is_aa(details: dict[str, object]) -> bool:
        try:
            return float(details.get("score_after", 0)) >= 80 and float(
                details.get("copy_score", 0)
            ) >= 75
        except (TypeError, ValueError):
            return False
