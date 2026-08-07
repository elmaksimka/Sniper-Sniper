from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.assets import NON_TARGET_MINTS
from app.infrastructure.models import (
    Alert,
    Token,
    TokenScoreSnapshot,
    Trade,
    WalletMonitor,
    WalletScoreSnapshot,
)
from app.services.score_backfill_service import ScoreBackfillService


@dataclass(frozen=True, slots=True)
class NonTargetCleanupResult:
    trades_deleted: int
    tokens_deleted: int
    wallet_scores_updated: int
    token_scores_updated: int
    monitors_disabled: int


class NonTargetCleanupService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def run(self, monitor_score_threshold: float = 65) -> NonTargetCleanupResult:
        token_ids = select(Token.id).where(Token.address.in_(NON_TARGET_MINTS))
        await self.session.execute(
            delete(Alert).where(
                Alert.entity_type == "token",
                Alert.entity_address.in_(NON_TARGET_MINTS),
            )
        )
        await self.session.execute(
            delete(TokenScoreSnapshot).where(
                TokenScoreSnapshot.token_id.in_(token_ids)
            )
        )
        trade_result = await self.session.execute(
            delete(Trade).where(Trade.token_id.in_(token_ids))
        )
        token_result = await self.session.execute(
            delete(Token).where(Token.address.in_(NON_TARGET_MINTS))
        )
        await self.session.commit()

        wallet_count, token_count = await ScoreBackfillService(
            self.session
        ).run_all()
        ineligible_wallet_ids = select(WalletScoreSnapshot.wallet_id).where(
            WalletScoreSnapshot.score < monitor_score_threshold
        )
        monitor_result = await self.session.execute(
            update(WalletMonitor)
            .where(
                WalletMonitor.enabled.is_(True),
                WalletMonitor.wallet_id.in_(ineligible_wallet_ids),
            )
            .values(
                enabled=False,
                updated_at=datetime.now(UTC),
                last_error="Disabled after non-target asset score cleanup",
            )
        )
        await self.session.commit()
        return NonTargetCleanupResult(
            trades_deleted=int(getattr(trade_result, "rowcount", 0) or 0),
            tokens_deleted=int(getattr(token_result, "rowcount", 0) or 0),
            wallet_scores_updated=wallet_count,
            token_scores_updated=token_count,
            monitors_disabled=int(getattr(monitor_result, "rowcount", 0) or 0),
        )
