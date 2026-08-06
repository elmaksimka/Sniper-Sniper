from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.infrastructure.leader_election import PostgresLeaderElector


class FakeConnection:
    def __init__(self, acquire_result: bool) -> None:
        self.acquire_result = acquire_result
        self.closed = False
        self.calls: list[tuple[str, dict[str, int] | None]] = []
        self.fail_verification = False
        self.commits = 0

    async def scalar(
        self,
        statement: object,
        parameters: dict[str, int] | None = None,
    ) -> bool | int:
        sql = str(statement)
        self.calls.append((sql, parameters))
        if sql == "SELECT 1":
            if self.fail_verification:
                raise SQLAlchemyError("connection lost")
            return 1
        if "pg_try_advisory_lock" in sql:
            return self.acquire_result
        return True

    async def close(self) -> None:
        self.closed = True

    async def commit(self) -> None:
        self.commits += 1


class FakeEngine:
    def __init__(self, *connections: FakeConnection) -> None:
        self.connections = list(connections)
        self.connect_calls = 0

    async def connect(self) -> FakeConnection:
        connection = self.connections[self.connect_calls]
        self.connect_calls += 1
        return connection


@pytest.mark.asyncio
async def test_elector_holds_and_releases_advisory_lock() -> None:
    connection = FakeConnection(acquire_result=True)
    engine = FakeEngine(connection)
    engine_value: Any = engine
    elector = PostgresLeaderElector(engine=engine_value, lock_key=42)

    assert await elector.try_acquire() is True
    assert elector.is_leader is True
    assert await elector.try_acquire() is True
    assert engine.connect_calls == 1
    assert await elector.verify() is True

    await elector.release()

    assert elector.is_leader is False
    assert connection.closed is True
    assert any("pg_advisory_unlock" in sql for sql, _ in connection.calls)
    assert connection.calls[0][1] == {"lock_key": 42}
    assert connection.commits == 3


@pytest.mark.asyncio
async def test_elector_closes_standby_connection() -> None:
    connection = FakeConnection(acquire_result=False)
    engine = FakeEngine(connection)
    engine_value: Any = engine
    elector = PostgresLeaderElector(engine=engine_value, lock_key=42)

    assert await elector.try_acquire() is False

    assert elector.is_leader is False
    assert connection.closed is True


@pytest.mark.asyncio
async def test_elector_detects_lost_connection() -> None:
    connection = FakeConnection(acquire_result=True)
    engine = FakeEngine(connection)
    engine_value: Any = engine
    elector = PostgresLeaderElector(engine=engine_value, lock_key=42)
    assert await elector.try_acquire() is True
    connection.fail_verification = True

    assert await elector.verify() is False

    assert elector.is_leader is False
    assert connection.closed is True
