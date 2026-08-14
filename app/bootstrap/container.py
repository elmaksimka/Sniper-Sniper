from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer import TokenAnalyzer
from app.collectors.token_collector import TokenCollector
from app.collectors.trade_collector import TradeCollector
from app.collectors.score_collector import ScoreCollector
from app.collectors.alert_collector import AlertCollector
from app.collectors.funding_collector import FundingCollector
from app.collectors.alpha_signal_collector import AlphaSignalCollector
from app.collectors.trader_promotion_collector import TraderPromotionCollector
from app.collectors.paper_copy_collector import PaperCopyCollector
from app.core.config import get_settings
from app.core.event_bus import EventBus
from app.core.events import AlphaSignalGenerated
from app.listeners.helius_client import HeliusClient
from app.listeners.transaction_scanner import TransactionScanner
from app.notifications.telegram import TelegramNotifier
from app.repositories.score_snapshot_repository import ScoreSnapshotRepository
from app.repositories.wallet_repository import WalletRepository
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.repositories.monitor_repository import MonitorRepository
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.services.metadata_service import MetadataService
from app.services.alert_service import AlertService
from app.services.score_snapshot_service import ScoreSnapshotService
from app.services.scoring_service import ScoringService
from app.services.token_detection_service import TokenDetectionService
from app.services.token_parser import TokenParser
from app.services.token_service import TokenService
from app.services.token_store import TokenStore
from app.services.trade_service import TradeService
from app.services.wallet_service import WalletService
from app.services.funding_service import FundingService
from app.services.token_score_snapshot_service import TokenScoreSnapshotService
from app.services.dex_discovery_service import DexDiscoveryService
from app.services.dexscreener_client import DexScreenerClient
from app.services.monitor_service import MonitorService
from app.services.trader_style_service import TraderStyleService
from app.services.paper_copy_service import PaperCopyService


class Container:
    def __init__(
        self,
        session: AsyncSession,
        helius_client: HeliusClient | None = None,
    ) -> None:
        settings = get_settings()
        self.event_bus = EventBus()

        self.token_service = TokenService(session)
        self.wallet_service = WalletService(session)
        self.trade_service = TradeService(session)
        self.scoring_service = ScoringService(session)
        self.score_snapshot_service = ScoreSnapshotService(session)
        self.token_score_snapshot_service = TokenScoreSnapshotService(session)
        self.alert_service = AlertService(session)
        self.funding_service = FundingService(session)
        self.monitor_service = MonitorService(session)
        self.market_data_client = DexScreenerClient()
        self.trader_style_service = TraderStyleService(
            session,
            min_history_trades=settings.alpha_trader_min_history_trades,
            min_hold_minutes=settings.alpha_trader_min_hold_minutes,
            max_distinct_tokens_60s=(settings.alpha_trader_max_distinct_tokens_60s),
            max_side_switches_per_token=(
                settings.alpha_trader_max_side_switches_per_token
            ),
            side_switch_window_minutes=(
                settings.alpha_trader_side_switch_window_minutes
            ),
            rapid_round_trip_seconds=(settings.alpha_trader_rapid_round_trip_seconds),
            max_rapid_round_trips=(settings.alpha_trader_max_rapid_round_trips),
        )
        self.telegram_notifier = TelegramNotifier(
            settings.telegram_bot_token,
            settings.telegram_recipients,
            market_data_client=self.market_data_client,
        )

        self.token_collector = TokenCollector(
            event_bus=self.event_bus,
            token_service=self.token_service,
        )
        self.trade_collector = TradeCollector(
            event_bus=self.event_bus,
            token_service=self.token_service,
            wallet_service=self.wallet_service,
            trade_service=self.trade_service,
        )
        self.score_collector = ScoreCollector(
            event_bus=self.event_bus,
            scoring_service=self.scoring_service,
            snapshot_service=self.score_snapshot_service,
            wallet_service=self.wallet_service,
            token_snapshot_service=self.token_score_snapshot_service,
            token_service=self.token_service,
        )
        self.alert_collector = AlertCollector(
            event_bus=self.event_bus,
            alert_service=self.alert_service,
            minimum_score=settings.wallet_score_alert_threshold,
            token_minimum_score=settings.token_score_alert_threshold,
        )
        self.funding_collector = FundingCollector(
            event_bus=self.event_bus,
            wallet_service=self.wallet_service,
            funding_service=self.funding_service,
        )
        self.alpha_signal_collector = AlphaSignalCollector(
            event_bus=self.event_bus,
            wallets=WalletRepository(session),
            wallet_scores=ScoreSnapshotRepository(session),
            scoring=self.scoring_service,
            alerts=self.alert_service,
            wallet_threshold=settings.alpha_wallet_score_threshold,
            token_threshold=settings.alpha_early_token_score_threshold,
            token_min_trades=settings.alpha_early_token_min_trades,
            token_min_wallets=settings.alpha_early_token_min_wallets,
            maximum_trade_age_seconds=settings.alpha_signal_max_age_seconds,
            market_data=self.market_data_client,
            market_min_liquidity_usd=settings.alpha_market_min_liquidity_usd,
            market_min_volume_5m_usd=settings.alpha_market_min_volume_5m_usd,
            market_min_transactions_5m=(settings.alpha_market_min_transactions_5m),
            market_max_pair_age_minutes=(settings.alpha_market_max_pair_age_minutes),
            trader_style=self.trader_style_service,
        )
        self.trader_promotion_collector = TraderPromotionCollector(
            event_bus=self.event_bus,
            monitors=MonitorRepository(session),
            monitor_service=self.monitor_service,
            minimum_score=settings.auto_promote_wallet_score,
            maximum_monitors=settings.auto_promote_max_monitors,
            scores=ScoreSnapshotRepository(session),
            trader_style=self.trader_style_service,
        )
        self.paper_copy_service = PaperCopyService(
            PaperCopyRepository(session),
            self.market_data_client,
            quote_retry_seconds=settings.paper_copy_quote_retry_seconds,
            quote_max_attempts=settings.paper_copy_quote_max_attempts,
            source_wallets=settings.paper_copy_sources,
            portfolio_wallet=settings.paper_copy_portfolio_wallet,
            minimum_source_value_usd=(settings.paper_copy_minimum_source_value_usd),
            maximum_trade_age_seconds=(settings.paper_copy_max_signal_age_seconds),
        )
        self.paper_copy_collector = PaperCopyCollector(
            self.event_bus,
            self.paper_copy_service,
        )

        self.helius_client = helius_client or HeliusClient()
        self.token_parser = TokenParser()
        self.token_analyzer = TokenAnalyzer()
        self.metadata_service = MetadataService(self.helius_client)
        self.token_store = TokenStore()

        self.scanner = TransactionScanner(
            helius=self.helius_client,
            parser=self.token_parser,
            analyzer=self.token_analyzer,
        )
        self.token_detection_service = TokenDetectionService(
            scanner=self.scanner,
            store=self.token_store,
            metadata=self.metadata_service,
            event_bus=self.event_bus,
        )
        self.dex_discovery_service = DexDiscoveryService(
            client=self.helius_client,
            scanner=self.scanner,
            detection=self.token_detection_service,
            cursors=HeartbeatRepository(session),
            page_size=settings.discovery_page_size,
            max_pages=settings.discovery_max_pages,
        )

    def setup(
        self,
        *,
        register_trader_promotion: bool = True,
        register_paper_copy: bool = False,
    ) -> None:
        self.token_collector.register()
        self.trade_collector.register()
        self.score_collector.register()
        self.alert_collector.register()
        self.funding_collector.register()
        self.alpha_signal_collector.register()
        if register_trader_promotion:
            self.trader_promotion_collector.register()
        if register_paper_copy:
            self.paper_copy_collector.register()
        self.event_bus.subscribe(
            AlphaSignalGenerated,
            self.telegram_notifier.handle_alpha_signal,
        )
