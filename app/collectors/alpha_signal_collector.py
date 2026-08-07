from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.core.event_bus import EventBus
from app.core.events import AlphaSignalGenerated, TradeScored
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.repositories.wallet_repository import WalletRepository
from app.services.alert_service import AlertService
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote
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
        maximum_trade_age_seconds: float,
        market_data: DexScreenerClient,
        market_min_liquidity_usd: float,
        market_min_volume_5m_usd: float,
        market_min_transactions_5m: int,
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
        self.maximum_trade_age_seconds = maximum_trade_age_seconds
        self.market_data = market_data
        self.market_min_liquidity_usd = market_min_liquidity_usd
        self.market_min_volume_5m_usd = market_min_volume_5m_usd
        self.market_min_transactions_5m = market_min_transactions_5m

    def register(self) -> None:
        self.event_bus.subscribe(TradeScored, self.handle_trade_scored)

    async def handle_trade_scored(self, event: TradeScored) -> None:
        if event.side != "buy" or not event.signature:
            return
        if event.transaction_at is not None:
            transaction_at = event.transaction_at
            if transaction_at.tzinfo is None:
                transaction_at = transaction_at.replace(tzinfo=UTC)
            if datetime.now(UTC) - transaction_at > timedelta(
                seconds=self.maximum_trade_age_seconds
            ):
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

        market = await self._qualifying_market(event.token_address)
        if market is None:
            return
        top_trader_count = await self.wallet_scores.count_top_buyers_for_token(
            event.token_address,
            self.wallet_threshold,
        )

        alert = await self.alerts.create_alpha_signal(
            event,
            wallet_score,
            token_score,
            market,
            top_trader_count,
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
                market_price_usd=market.price_usd,
                market_pair_url=market.pair_url,
                market_liquidity_usd=market.liquidity_usd,
                market_volume_5m_usd=market.volume_5m_usd,
                market_buys_5m=market.buys_5m,
                market_sells_5m=market.sells_5m,
                observed_top_trader_count=top_trader_count,
            )
        )

    async def _qualifying_market(
        self,
        token_address: str,
    ) -> TokenMarketQuote | None:
        try:
            market = await self.market_data.get_token_quote(token_address)
        except Exception:
            return None
        if market is None:
            return None
        if (
            market.liquidity_usd < self.market_min_liquidity_usd
            or market.volume_5m_usd < self.market_min_volume_5m_usd
            or market.transactions_5m < self.market_min_transactions_5m
        ):
            return None
        return market
