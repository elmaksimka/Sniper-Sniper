from types import SimpleNamespace

import pytest

from app.services.activity_stats_service import ActivityStatsService


class FakeResult:
    def one(self) -> object:
        return SimpleNamespace(
            total_transactions=125,
            total_tokens=48,
            recent_transactions=17,
            recent_tokens=9,
        )


class FakeSession:
    async def execute(self, statement: object) -> FakeResult:
        return FakeResult()


@pytest.mark.asyncio
async def test_activity_stats_maps_database_counts() -> None:
    service = ActivityStatsService(FakeSession())  # type: ignore[arg-type]

    stats = await service.get(30)

    assert stats.total_transactions == 125
    assert stats.total_tokens == 48
    assert stats.recent_transactions == 17
    assert stats.recent_tokens == 9
    assert stats.window_minutes == 30
