from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.analyzer import TokenAnalyzer
from app.collectors.token_collector import TokenCollector
from app.collectors.trade_collector import TradeCollector
from app.collectors.score_collector import ScoreCollector
from app.collectors.alert_collector import AlertCollector
from app.core.config import get_settings
from app.core.event_bus import EventBus
from app.listeners.helius_client import HeliusClient
from app.listeners.transaction_scanner import TransactionScanner
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
        self.alert_service = AlertService(session)

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
        )
        self.alert_collector = AlertCollector(
            event_bus=self.event_bus,
            alert_service=self.alert_service,
            minimum_score=settings.wallet_score_alert_threshold,
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

    def setup(self) -> None:
        self.token_collector.register()
        self.trade_collector.register()
        self.score_collector.register()
        self.alert_collector.register()
