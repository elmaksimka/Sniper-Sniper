from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models import ServiceHeartbeat


class HeartbeatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, service_name: str) -> ServiceHeartbeat | None:
        return await self.session.get(ServiceHeartbeat, service_name)

    async def beat(
        self,
        service_name: str,
        instance_id: str,
        details: dict | None = None,
    ) -> ServiceHeartbeat:
        heartbeat = await self.get(service_name)
        if heartbeat is None:
            heartbeat = ServiceHeartbeat(
                service_name=service_name,
                instance_id=instance_id,
            )
            self.session.add(heartbeat)

        heartbeat.instance_id = instance_id
        heartbeat.last_heartbeat_at = datetime.now(UTC)
        heartbeat.details = details or {}
        await self.session.commit()
        return heartbeat
