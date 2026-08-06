from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.logging import get_logger


class PostgresLeaderElector:
    """Hold a session-level PostgreSQL advisory lock on a dedicated connection."""

    def __init__(self, engine: AsyncEngine, lock_key: int) -> None:
        self._engine = engine
        self._lock_key = lock_key
        self._connection: AsyncConnection | None = None
        self._logger = get_logger("worker-leader")

    @property
    def is_leader(self) -> bool:
        return self._connection is not None

    async def try_acquire(self) -> bool:
        if self._connection is not None:
            return True

        connection = await self._engine.connect()
        try:
            acquired = await connection.scalar(
                text("SELECT pg_try_advisory_lock(:lock_key)"),
                {"lock_key": self._lock_key},
            )
            await connection.commit()
        except BaseException:
            await self._close(connection)
            raise

        if not acquired:
            await self._close(connection)
            return False

        self._connection = connection
        self._logger.info("worker_leadership_acquired", lock_key=self._lock_key)
        return True

    async def verify(self) -> bool:
        connection = self._connection
        if connection is None:
            return False

        try:
            await connection.scalar(text("SELECT 1"))
            await connection.commit()
        except SQLAlchemyError as exc:
            self._logger.warning("worker_leadership_lost", error=str(exc))
            self._connection = None
            await self._close(connection)
            return False
        return True

    async def release(self) -> None:
        connection = self._connection
        self._connection = None
        if connection is None:
            return

        try:
            await connection.scalar(
                text("SELECT pg_advisory_unlock(:lock_key)"),
                {"lock_key": self._lock_key},
            )
            await connection.commit()
        except SQLAlchemyError as exc:
            self._logger.warning("worker_leadership_release_failed", error=str(exc))
        finally:
            await self._close(connection)
            self._logger.info("worker_leadership_released", lock_key=self._lock_key)

    async def _close(self, connection: AsyncConnection) -> None:
        try:
            await connection.close()
        except SQLAlchemyError as exc:
            self._logger.warning("worker_leader_connection_close_failed", error=str(exc))
