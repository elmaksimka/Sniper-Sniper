from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import AlphaSignalGenerated, TradeScored
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.repositories.token_repository import TokenRepository
from app.repositories.token_score_snapshot_repository import (
    TokenScoreSnapshotRepository,
)
from app.repositories.wallet_repository import WalletRepository
from app.services.alert_service import AlertService


class AlphaSignalCollector:
    """Create a signal when a highly scored wallet buys a highly scored token."""

    def __init__(
        self,
        event_bus: EventBus,
        wallets: WalletRepository,
        tokens: TokenRepository,
        wallet_scores: ScoreSnapshotRepository,
        token_scores: TokenScoreSnapshotRepository,
        alerts: AlertService,
        wallet_threshold: float,
        token_threshold: float,
    ) -> None:
        self.event_bus = event_bus
        self.wallets = wallets
        self.tokens = tokens
        self.wallet_scores = wallet_scores
        self.token_scores = token_scores
        self.alerts = alerts
        self.wallet_threshold = wallet_threshold
        self.token_threshold = token_threshold

    def register(self) -> None:
        self.event_bus.subscribe(TradeScored, self.handle_trade_scored)

    async def handle_trade_scored(self, event: TradeScored) -> None:
        if event.side != "buy" or not event.signature:
            return

        wallet = await self.wallets.get_by_address(event.wallet)
        token = await self.tokens.get_by_address(event.token_address)
        if wallet is None or token is None:
            return

        wallet_score = await self.wallet_scores.get_by_wallet_id(wallet.id)
        token_score = await self.token_scores.get_by_token_id(token.id)
        if wallet_score is None or token_score is None:
            return
        if (
            wallet_score.score < self.wallet_threshold
            or token_score.score < self.token_threshold
            or wallet_score.grade not in {"A", "B"}
            or token_score.grade not in {"A", "B"}
        ):
            return

        alert = await self.alerts.create_alpha_signal(
            event,
            wallet_score,
            token_score,
        )
        if alert is None:
            return

        await self.event_bus.publish(
            AlphaSignalGenerated(
                wallet=event.wallet,
                token_address=event.token_address,
                wallet_score=wallet_score.score,
                wallet_grade=wallet_score.grade,
                token_score=token_score.score,
                token_grade=token_score.grade,
                token_amount=event.amount,
                sol_amount=abs(event.sol_change),
                signature=event.signature,
                severity=alert.severity,
                message=alert.message,
            )
        )
