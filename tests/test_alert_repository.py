from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from app.infrastructure.models import Alert
from app.repositories.alert_repository import AlertRepository


class FakeResult:
    def scalar_one_or_none(self) -> None:
        return None


class CompilingSession:
    def __init__(self) -> None:
        self.sql = ""
        self.committed = False

    async def execute(self, statement: Any) -> FakeResult:
        self.sql = str(statement.compile(dialect=postgresql.dialect()))
        return FakeResult()

    async def commit(self) -> None:
        self.committed = True


@pytest.mark.asyncio
async def test_alert_insert_uses_atomic_dedupe() -> None:
    session = CompilingSession()
    repository = AlertRepository(session)  # type: ignore[arg-type]

    alert = await repository.create_if_absent(
        {
            "entity_type": "wallet",
            "entity_address": "wallet",
            "alert_type": "wallet_score_grade",
            "severity": "high",
            "message": "milestone",
            "details": {},
            "dedupe_key": "dedupe",
        }
    )

    assert alert is None
    assert "ON CONFLICT (dedupe_key) DO NOTHING" in session.sql
    assert "RETURNING" in session.sql
    assert session.committed is True


def test_alert_metadata_uses_non_reserved_model_attribute() -> None:
    alert = Alert(details={"score": 75})
    assert alert.details == {"score": 75}
