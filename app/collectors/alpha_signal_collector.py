from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import AlphaSignalGenerated, TradeScored
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.alert_service import AlertService
from app.services.scoring_service import ScoringService


class AlphaSignalCollector:
    """Create a signal when a top wallet buys a promising early token."""

    def __init__(
        self,
        event_bus: EventBus,
        wallets: WalletRepository,
        wallet_scores: ScoreSnapshotRepository,
        scoring: ScoringService,
        alerts: AlertService,
        wallet_threshold: float,
        token_threshold: float,
        token_min_trades: int,
        token_min_wallets: int,
    ) -> None:
        self.event_bus = event_bus
        self.wallets = wallets
        self.wallet_scores = wallet_scores
        self.scoring = scoring
        self.alerts = alerts
        self.wallet_threshold = wallet_threshold
        self.token_threshold = token_threshold
        self.token_min_trades = token_min_trades
        self.token_min_wallets = token_min_wallets

    def register(self) -> None:
        self.event_bus.subscribe(TradeScored, self.handle_trade_scored)

    async def handle_trade_scored(self, event: TradeScored) -> None:
        if event.side != "buy" or not event.signature:
            return

        wallet = await self.wallets.get_by_address(event.wallet)
        if wallet is None:
            return

        wallet_score = await self.wallet_scores.get_by_wallet_id(wallet.id)
        token_score = await self.scoring.score_early_token(event.token_address)
        if wallet_score is None or token_score is None:
            return
        if (
            wallet_score.score < self.wallet_threshold
            or token_score.score < self.token_threshold
            or wallet_score.grade not in {"A", "B"}
            or token_score.observed_trade_count < self.token_min_trades
            or token_score.observed_wallet_count < self.token_min_wallets
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
                token_score_methodology=token_score.methodology_version,
                observed_trade_count=token_score.observed_trade_count,
                observed_wallet_count=token_score.observed_wallet_count,
                token_amount=event.amount,
                sol_amount=abs(event.sol_change),
                signature=event.signature,
                severity=alert.severity,
                message=alert.message,
            )
        )
