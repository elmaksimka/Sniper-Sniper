from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ScoreUpdated
from app.infrastructure.models import Alert
from app.repositories.alert_repository import AlertRepository


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AlertRepository(session)

    async def create_score_alert(self, event: ScoreUpdated) -> Alert | None:
        severity = "critical" if event.grade == "A" else "high"
        dedupe_key = (
            f"{event.entity_type}-score:{event.entity}:"
            f"{event.methodology_version}:{event.grade}"
        )
        label = event.entity_type.capitalize()
        return await self.repository.create_if_absent(
            {
                "entity_type": event.entity_type,
                "entity_address": event.entity,
                "alert_type": f"{event.entity_type}_score_grade",
                "severity": severity,
                "message": (
                    f"{label} {event.entity} reached grade {event.grade} "
                    f"with score {event.score:.2f}"
                ),
                "details": {
                    "score": event.score,
                    "grade": event.grade,
                    "methodology_version": event.methodology_version,
                },
                "dedupe_key": dedupe_key,
                "created_at": datetime.now(UTC),
            }
        )

    async def list_alerts(
        self,
        limit: int,
        offset: int,
        entity_address: str | None,
        severity: str | None,
        acknowledged: bool | None,
        entity_type: str | None = None,
    ) -> tuple[list[Alert], int]:
        filters = (entity_address, severity, acknowledged, entity_type)
        return (
            await self.repository.list_all(limit, offset, *filters),
            await self.repository.count(*filters),
        )

    async def acknowledge(self, alert_id: int) -> Alert | None:
        return await self.repository.acknowledge(alert_id)
