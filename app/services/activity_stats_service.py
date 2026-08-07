from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.activity import WorkerActivityStats
from app.infrastructure.models import Token, Trade


class ActivityStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, window_minutes: int) -> WorkerActivityStats:
        cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
        total_transactions = (
            select(func.count(func.distinct(Trade.signature)))
            .where(Trade.signature.is_not(None))
            .scalar_subquery()
        )
        total_tokens = select(func.count(Token.id)).scalar_subquery()
        recent_transactions = (
            select(func.count(func.distinct(Trade.signature)))
            .where(
                Trade.signature.is_not(None),
                Trade.timestamp >= cutoff,
            )
            .scalar_subquery()
        )
        recent_tokens = (
            select(func.count(func.distinct(Trade.token_id)))
            .where(Trade.timestamp >= cutoff)
            .scalar_subquery()
        )
        result = await self.session.execute(
            select(
                total_transactions.label("total_transactions"),
                total_tokens.label("total_tokens"),
                recent_transactions.label("recent_transactions"),
                recent_tokens.label("recent_tokens"),
            )
        )
        row = result.one()
        return WorkerActivityStats(
            total_transactions=int(row.total_transactions),
            total_tokens=int(row.total_tokens),
            recent_transactions=int(row.recent_transactions),
            recent_tokens=int(row.recent_tokens),
            window_minutes=window_minutes,
        )
