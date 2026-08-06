from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.listeners.helius_client import HeliusClient
from app.repositories.heartbeat_repository import HeartbeatRepository


class SystemHealthService:
    def __init__(
        self,
        session: AsyncSession,
        helius_client: HeliusClient,
        worker_stale_after_seconds: float,
        check_timeout_seconds: float,
    ) -> None:
        self.session = session
        self.helius_client = helius_client
        self.heartbeats = HeartbeatRepository(session)
        self.worker_stale_after_seconds = worker_stale_after_seconds
        self.check_timeout_seconds = check_timeout_seconds

    async def readiness(self) -> dict[str, Any]:
        database_ok = await self._database_ready()
        helius_ok = await self._helius_ready()
        worker = await self._worker_ready(database_ok)
        ready = database_ok and helius_ok and worker["status"] == "ok"
        return {
            "status": "ready" if ready else "not_ready",
            "checks": {
                "database": {"status": "ok" if database_ok else "error"},
                "helius": {"status": "ok" if helius_ok else "error"},
                "worker": worker,
            },
        }

    async def _database_ready(self) -> bool:
        try:
            async with asyncio.timeout(self.check_timeout_seconds):
                await self.session.execute(text("SELECT 1"))
        except Exception:
            return False
        return True

    async def _helius_ready(self) -> bool:
        try:
            async with asyncio.timeout(self.check_timeout_seconds):
                response = await self.helius_client.get_health()
            return response.get("error") is None and response.get("result") == "ok"
        except Exception:
            return False

    async def _worker_ready(self, database_ok: bool) -> dict[str, Any]:
        if not database_ok:
            return {"status": "error", "reason": "database_unavailable"}

        try:
            async with asyncio.timeout(self.check_timeout_seconds):
                heartbeat = await self.heartbeats.get("monitor-worker")
        except Exception:
            return {"status": "error", "reason": "heartbeat_unavailable"}
        if heartbeat is None:
            return {"status": "error", "reason": "heartbeat_missing"}

        heartbeat_at = heartbeat.last_heartbeat_at
        if heartbeat_at.tzinfo is None:
            heartbeat_at = heartbeat_at.replace(tzinfo=UTC)
        age_seconds = max(
            0.0,
            (datetime.now(UTC) - heartbeat_at).total_seconds(),
        )
        status = (
            "ok"
            if age_seconds <= self.worker_stale_after_seconds
            else "error"
        )
        return {
            "status": status,
            "reason": None if status == "ok" else "heartbeat_stale",
            "instance_id": heartbeat.instance_id,
            "last_heartbeat_at": heartbeat_at,
            "age_seconds": round(age_seconds, 3),
            "details": heartbeat.details,
        }
