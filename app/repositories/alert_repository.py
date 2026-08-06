from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import Alert


class AlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_if_absent(self, values: dict[str, object]) -> Alert | None:
        statement = (
            insert(Alert)
            .values(**values)
            .on_conflict_do_nothing(index_elements=[Alert.dedupe_key])
            .returning(Alert)
        )
        result = await self.session.execute(statement)
        alert = result.scalar_one_or_none()
        await self.session.commit()
        return alert

    async def get(self, alert_id: int) -> Alert | None:
        result = await self.session.execute(
            select(Alert).where(Alert.id == alert_id)
        )
        return result.scalar_one_or_none()

    async def acknowledge(self, alert_id: int) -> Alert | None:
        alert = await self.get(alert_id)
        if alert is None:
            return None

        if alert.acknowledged_at is None:
            alert.acknowledged_at = datetime.now(UTC)
            await self.session.commit()
            await self.session.refresh(alert)
        return alert

    async def list_all(
        self,
        limit: int,
        offset: int,
        entity_address: str | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
    ) -> list[Alert]:
        conditions = self._filters(entity_address, severity, acknowledged)
        result = await self.session.execute(
            select(Alert)
            .where(*conditions)
            .order_by(Alert.created_at.desc(), Alert.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count(
        self,
        entity_address: str | None = None,
        severity: str | None = None,
        acknowledged: bool | None = None,
    ) -> int:
        conditions = self._filters(entity_address, severity, acknowledged)
        result = await self.session.execute(
            select(func.count(Alert.id)).where(*conditions)
        )
        return result.scalar_one()

    @staticmethod
    def _filters(
        entity_address: str | None,
        severity: str | None,
        acknowledged: bool | None,
    ) -> list:
        conditions = []
        if entity_address:
            conditions.append(Alert.entity_address == entity_address)
        if severity:
            conditions.append(Alert.severity == severity)
        if acknowledged is True:
            conditions.append(Alert.acknowledged_at.is_not(None))
        elif acknowledged is False:
            conditions.append(Alert.acknowledged_at.is_(None))
        return conditions
