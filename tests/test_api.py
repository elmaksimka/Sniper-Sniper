from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_analytics_service, get_read_service
from app.api.dependencies import get_score_snapshot_service, get_scoring_service
from app.api.dependencies import get_token_score_snapshot_service
from app.api.dependencies import get_alert_service
from app.api.dependencies import get_funding_service, get_monitor_service
from app.api.dependencies import get_system_health_service
from app.core.analytics import (
    CreatorAnalytics,
    CreatorTokenAnalytics,
    ObservedTokenHolder,
    TokenAnalytics,
    TokenPosition,
    WalletAnalytics,
)
from app.core.scoring import TokenScore, WalletScore
from app.core.funding import FundingCounterparty, WalletFundingAnalytics
from app.infrastructure.models import (
    Alert,
    Token,
    Trade,
    Wallet,
    WalletMonitor,
    WalletScoreSnapshot,
    FundingTransfer,
    TokenScoreSnapshot,
)


class FakeReadService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.token = Token(
            id=1,
            address="mint",
            creator="creator",
            symbol="TKN",
            name="Token",
            decimals=6,
            supply=1_000_000,
            created_at=now,
        )
        self.wallet = Wallet(id=2, address="wallet", first_seen=now)
        self.trade = Trade(
            id=3,
            token_id=1,
            wallet_id=2,
            signature="signature",
            side="buy",
            amount=10,
            price=0.1,
            sol_change=-1,
            timestamp=now,
            token=self.token,
            wallet=self.wallet,
        )
        self.trade_filters: tuple | None = None

    async def list_tokens(
        self,
        limit: int,
        offset: int,
        creator: str | None,
    ) -> tuple[list[Token], int]:
        assert (limit, offset, creator) == (10, 5, "creator")
        return [self.token], 1

    async def get_token(self, address: str) -> Token | None:
        return self.token if address == self.token.address else None

    async def list_wallets(
        self,
        limit: int,
        offset: int,
    ) -> tuple[list[Wallet], int]:
        return [self.wallet], 1

    async def get_wallet(self, address: str) -> Wallet | None:
        return self.wallet if address == self.wallet.address else None

    async def list_trades(
        self,
        limit: int,
        offset: int,
        token_address: str | None,
        wallet_address: str | None,
        side: str | None,
    ) -> tuple[list[Trade], int]:
        self.trade_filters = (
            limit,
            offset,
            token_address,
            wallet_address,
            side,
        )
        return [self.trade], 1


class FakeAnalyticsService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.wallet = WalletAnalytics(
            address="wallet",
            total_trades=3,
            buy_count=2,
            sell_count=1,
            unique_tokens=2,
            sol_spent=2.5,
            sol_received=1.0,
            net_sol_change=-1.5,
            first_trade_at=now,
            last_trade_at=now,
        )
        self.token = TokenAnalytics(
            address="mint",
            total_trades=3,
            buy_count=2,
            sell_count=1,
            unique_wallets=2,
            buy_volume=20,
            sell_volume=5,
            net_token_flow=15,
            net_wallet_sol_change=-1.5,
            first_trade_at=now,
            last_trade_at=now,
        )
        self.include_closed: bool | None = None

    async def get_wallet(self, address: str) -> WalletAnalytics | None:
        return self.wallet if address == self.wallet.address else None

    async def get_token(self, address: str) -> TokenAnalytics | None:
        return self.token if address == self.token.address else None

    async def get_wallet_positions(
        self,
        address: str,
        include_closed: bool = False,
    ) -> list[TokenPosition] | None:
        self.include_closed = include_closed
        if address != self.wallet.address:
            return None

        return [
            TokenPosition(
                token_address="mint",
                quantity=10,
                cost_basis_sol=1,
                average_entry_price_sol=0.1,
                realized_pnl_sol=0.25,
                total_bought=15,
                total_sold=5,
                sol_spent=1.5,
                sol_received=0.75,
                unmatched_sell_quantity=0,
                trade_count=2,
            )
        ]

    async def get_token_holders(
        self,
        address: str,
        limit: int,
        offset: int,
        include_closed: bool = False,
    ) -> tuple[list[ObservedTokenHolder], int] | None:
        if address != self.token.address:
            return None
        assert (limit, offset, include_closed) == (10, 5, True)
        now = datetime.now(UTC)
        return (
            [
                ObservedTokenHolder(
                    wallet_address="holder",
                    quantity=7,
                    total_bought=10,
                    total_sold=3,
                    unmatched_sell_quantity=0,
                    trade_count=2,
                    first_trade_at=now,
                    last_trade_at=now,
                )
            ],
            1,
        )

    async def get_creator(
        self,
        address: str,
        token_limit: int = 10,
    ) -> CreatorAnalytics | None:
        if address != "creator":
            return None
        now = datetime.now(UTC)
        return CreatorAnalytics(
            creator_address=address,
            token_count=2,
            traded_token_count=1,
            total_trades=2,
            unique_traders=2,
            observed_sol_volume=1.5,
            net_wallet_sol_change=-0.5,
            first_token_created_at=now,
            latest_token_created_at=now,
            tokens=[
                CreatorTokenAnalytics(
                    token_address="creator-mint",
                    symbol="CRT",
                    name="Creator Token",
                    created_at=now,
                    total_trades=2,
                    unique_traders=2,
                    observed_sol_volume=1.5,
                    first_trade_at=now,
                    last_trade_at=now,
                )
            ][:token_limit],
        )


class FakeScoringService:
    async def score_wallet(self, address: str) -> WalletScore | None:
        if address != "wallet":
            return None

        return WalletScore(
            wallet_address="wallet",
            score=72.5,
            grade="B",
            methodology_version="wallet-v1",
            activity_score=15,
            diversification_score=10,
            exit_experience_score=15,
            realized_performance_score=25,
            data_quality_score=7.5,
            realized_pnl_sol=2,
            realized_roi=0.2,
            unmatched_sell_ratio=0.25,
        )

    async def score_token(self, address: str) -> TokenScore | None:
        if address != "mint":
            return None
        return TokenScore(
            token_address=address,
            score=72.5,
            grade="B",
            methodology_version="token-v1",
            activity_score=15,
            participation_score=10,
            holder_distribution_score=18,
            flow_balance_score=10,
            creator_history_score=12,
            data_quality_score=7.5,
            observed_holder_count=8,
            top_holder_share=0.25,
            incomplete_holder_ratio=0.1,
        )


class FakeScoreSnapshotService:
    def __init__(self) -> None:
        wallet = Wallet(id=2, address="wallet")
        self.snapshot = WalletScoreSnapshot(
            id=1,
            wallet_id=wallet.id,
            wallet=wallet,
            score=72.5,
            grade="B",
            methodology_version="wallet-v1",
            activity_score=15,
            diversification_score=10,
            exit_experience_score=15,
            realized_performance_score=25,
            data_quality_score=7.5,
            realized_pnl_sol=2,
            realized_roi=0.2,
            unmatched_sell_ratio=0.25,
            updated_at=datetime.now(UTC),
        )
        self.filters: tuple[int, int, str | None] | None = None

    async def leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None,
    ) -> tuple[list[WalletScoreSnapshot], int]:
        self.filters = (limit, offset, grade)
        return [self.snapshot], 1


class FakeTokenScoreSnapshotService:
    def __init__(self) -> None:
        token = Token(id=1, address="mint")
        self.snapshot = TokenScoreSnapshot(
            id=1,
            token_id=token.id,
            token=token,
            score=72.5,
            grade="B",
            methodology_version="token-v1",
            activity_score=15,
            participation_score=10,
            holder_distribution_score=18,
            flow_balance_score=10,
            creator_history_score=12,
            data_quality_score=7.5,
            observed_holder_count=8,
            top_holder_share=0.25,
            incomplete_holder_ratio=0.1,
            updated_at=datetime.now(UTC),
        )
        self.filters: tuple[int, int, str | None] | None = None

    async def leaderboard(
        self,
        limit: int,
        offset: int,
        grade: str | None,
    ) -> tuple[list[TokenScoreSnapshot], int]:
        self.filters = (limit, offset, grade)
        return [self.snapshot], 1


class FakeAlertService:
    def __init__(self) -> None:
        self.alert = Alert(
            id=1,
            entity_type="wallet",
            entity_address="wallet",
            alert_type="wallet_score_grade",
            severity="high",
            message="Wallet reached grade B",
            details={"score": 72.5, "grade": "B"},
            dedupe_key="wallet:wallet-v1:B",
            created_at=datetime.now(UTC),
            acknowledged_at=None,
        )
        self.filters: tuple | None = None

    async def list_alerts(
        self,
        limit: int,
        offset: int,
        entity_address: str | None,
        severity: str | None,
        acknowledged: bool | None,
    ) -> tuple[list[Alert], int]:
        self.filters = (
            limit,
            offset,
            entity_address,
            severity,
            acknowledged,
        )
        return [self.alert], 1

    async def acknowledge(self, alert_id: int) -> Alert | None:
        if alert_id != self.alert.id:
            return None
        self.alert.acknowledged_at = datetime.now(UTC)
        return self.alert


class FakeMonitorService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.monitor = WalletMonitor(
            id=1,
            wallet_id=1,
            wallet=Wallet(id=1, address="wallet"),
            enabled=True,
            checkpoint_signature="checkpoint",
            last_scanned_at=now,
            last_error=None,
            created_at=now,
            updated_at=now,
        )

    async def add(self, address: str) -> WalletMonitor:
        self.monitor.wallet.address = address
        self.monitor.enabled = True
        return self.monitor

    async def list(self, enabled_only: bool = False) -> list[WalletMonitor]:
        return [self.monitor] if not enabled_only or self.monitor.enabled else []

    async def set_enabled(
        self,
        address: str,
        enabled: bool,
    ) -> WalletMonitor | None:
        if address != self.monitor.wallet.address:
            return None
        self.monitor.enabled = enabled
        return self.monitor


class FakeFundingService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        source = Wallet(id=10, address="funder")
        destination = Wallet(id=11, address="wallet")
        self.transfer = FundingTransfer(
            id=12,
            source_wallet_id=source.id,
            destination_wallet_id=destination.id,
            source_wallet=source,
            destination_wallet=destination,
            amount_sol=1.5,
            signature="funding-signature",
            instruction_index="outer:0",
            timestamp=now,
        )
        self.filters: tuple | None = None

    async def list_transfers(
        self,
        limit: int,
        offset: int,
        wallet_address: str | None,
        direction: str | None,
    ) -> tuple[list[FundingTransfer], int]:
        self.filters = (limit, offset, wallet_address, direction)
        return [self.transfer], 1

    async def get_wallet_analytics(
        self,
        address: str,
        counterparty_limit: int,
    ) -> WalletFundingAnalytics | None:
        if address != "wallet":
            return None
        return WalletFundingAnalytics(
            wallet_address=address,
            incoming_transfer_count=2,
            outgoing_transfer_count=1,
            incoming_sol=2.0,
            outgoing_sol=0.5,
            net_sol=1.5,
            unique_funders=1,
            unique_destinations=1,
            first_funder="funder",
            first_funding_at=self.transfer.timestamp,
            counterparties=[
                FundingCounterparty(
                    address="funder",
                    direction="incoming",
                    transfer_count=2,
                    total_sol=2.0,
                    first_transfer_at=self.transfer.timestamp,
                    last_transfer_at=self.transfer.timestamp,
                )
            ][:counterparty_limit],
        )


class FakeSystemHealthService:
    def __init__(self, ready: bool = True) -> None:
        self.ready = ready

    async def readiness(self) -> dict:
        component_status = "ok" if self.ready else "error"
        return {
            "status": "ready" if self.ready else "not_ready",
            "checks": {
                "database": {"status": component_status},
                "helius": {"status": component_status},
                "worker": {"status": component_status},
            },
        }

def create_client() -> tuple[TestClient, FakeReadService]:
    application = create_app()
    service = FakeReadService()
    analytics = FakeAnalyticsService()
    scoring = FakeScoringService()
    snapshots = FakeScoreSnapshotService()
    token_snapshots = FakeTokenScoreSnapshotService()
    alerts = FakeAlertService()
    monitors = FakeMonitorService()
    funding = FakeFundingService()
    system_health = FakeSystemHealthService()
    application.dependency_overrides[get_read_service] = lambda: service
    application.dependency_overrides[get_analytics_service] = lambda: analytics
    application.dependency_overrides[get_scoring_service] = lambda: scoring
    application.dependency_overrides[get_score_snapshot_service] = (
        lambda: snapshots
    )
    application.dependency_overrides[get_token_score_snapshot_service] = (
        lambda: token_snapshots
    )
    application.dependency_overrides[get_alert_service] = lambda: alerts
    application.dependency_overrides[get_monitor_service] = lambda: monitors
    application.dependency_overrides[get_funding_service] = lambda: funding
    application.dependency_overrides[get_system_health_service] = (
        lambda: system_health
    )
    return TestClient(application), service


def test_health() -> None:
    client, _ = create_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_liveness_and_readiness() -> None:
    client, _ = create_client()

    live = client.get("/health/live")
    ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"


def test_readiness_returns_503_when_a_dependency_is_unhealthy() -> None:
    application = create_app()
    service = FakeSystemHealthService(ready=False)
    application.dependency_overrides[get_system_health_service] = lambda: service
    client = TestClient(application)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_list_tokens_returns_paginated_response() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/tokens",
        params={"limit": 10, "offset": 5, "creator": "creator"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 5
    assert payload["items"][0]["address"] == "mint"


def test_missing_token_returns_404() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/tokens/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Token not found"}


def test_list_trades_applies_filters_and_flattens_relations() -> None:
    client, service = create_client()

    response = client.get(
        "/api/v1/trades",
        params={
            "token_address": "mint",
            "wallet_address": "wallet",
            "side": "buy",
        },
    )

    assert response.status_code == 200
    assert service.trade_filters == (50, 0, "mint", "wallet", "buy")
    assert response.json()["items"][0] == {
        "id": 3,
        "signature": "signature",
        "token_address": "mint",
        "wallet_address": "wallet",
        "side": "buy",
        "amount": 10.0,
        "price": 0.1,
        "sol_change": -1.0,
        "timestamp": service.trade.timestamp.isoformat().replace("+00:00", "Z"),
    }


def test_trade_side_validation() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/trades", params={"side": "hold"})

    assert response.status_code == 422


def test_list_funding_transfers() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/funding/transfers",
        params={"wallet_address": "wallet", "direction": "incoming"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["source"] == "funder"
    assert payload["items"][0]["destination"] == "wallet"
    assert payload["items"][0]["amount_sol"] == 1.5


def test_funding_direction_validation() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/funding/transfers",
        params={"direction": "sideways"},
    )

    assert response.status_code == 422


def test_get_wallet_funding_analytics() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/funding/wallets/wallet",
        params={"counterparty_limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["incoming_sol"] == 2.0
    assert payload["outgoing_sol"] == 0.5
    assert payload["net_sol"] == 1.5
    assert payload["first_funder"] == "funder"
    assert payload["counterparties"][0]["direction"] == "incoming"
    assert payload["counterparties"][0]["total_sol"] == 2.0


def test_missing_wallet_funding_analytics_returns_404() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/funding/wallets/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Wallet not found"}


def test_get_wallet_analytics() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/analytics/wallets/wallet")

    assert response.status_code == 200
    assert response.json()["total_trades"] == 3
    assert response.json()["unique_tokens"] == 2
    assert response.json()["sol_spent"] == 2.5
    assert response.json()["net_sol_change"] == -1.5


def test_get_token_analytics() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/analytics/tokens/mint")

    assert response.status_code == 200
    assert response.json()["unique_wallets"] == 2
    assert response.json()["buy_volume"] == 20.0
    assert response.json()["net_token_flow"] == 15.0


def test_list_observed_token_holders() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/analytics/tokens/mint/holders",
        params={"limit": 10, "offset": 5, "include_closed": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["token_address"] == "mint"
    assert payload["total"] == 1
    assert payload["include_closed"] is True
    assert payload["items"][0]["wallet_address"] == "holder"
    assert payload["items"][0]["quantity"] == 7.0
    assert payload["items"][0]["has_incomplete_history"] is False


def test_missing_token_holders_returns_404() -> None:
    application = create_app()
    analytics = FakeAnalyticsService()
    application.dependency_overrides[get_analytics_service] = lambda: analytics
    client = TestClient(application)

    response = client.get(
        "/api/v1/analytics/tokens/missing/holders",
        params={"limit": 10, "offset": 5, "include_closed": True},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Token not found"}


def test_get_creator_analytics() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/analytics/creators/creator",
        params={"token_limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["creator_address"] == "creator"
    assert payload["token_count"] == 2
    assert payload["traded_token_count"] == 1
    assert payload["unique_traders"] == 2
    assert payload["observed_sol_volume"] == 1.5
    assert payload["net_wallet_sol_change"] == -0.5
    assert payload["tokens"][0]["token_address"] == "creator-mint"


def test_missing_creator_returns_404() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/analytics/creators/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Creator not found"}


def test_missing_analytics_entity_returns_404() -> None:
    client, _ = create_client()

    wallet_response = client.get("/api/v1/analytics/wallets/missing")
    token_response = client.get("/api/v1/analytics/tokens/missing")

    assert wallet_response.status_code == 404
    assert token_response.status_code == 404


def test_get_wallet_positions() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/analytics/wallets/wallet/positions",
        params={"include_closed": True},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["wallet_address"] == "wallet"
    assert payload["total"] == 1
    assert payload["items"][0]["quantity"] == 10.0
    assert payload["items"][0]["realized_pnl_sol"] == 0.25
    assert payload["items"][0]["has_incomplete_history"] is False


def test_get_wallet_score() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/scores/wallets/wallet")

    assert response.status_code == 200
    payload = response.json()
    assert payload["score"] == 72.5
    assert payload["grade"] == "B"
    assert payload["methodology_version"] == "wallet-v1"
    assert payload["realized_performance_score"] == 25.0


def test_missing_wallet_score_returns_404() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/scores/wallets/missing")

    assert response.status_code == 404


def test_get_token_score() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/scores/tokens/mint")

    assert response.status_code == 200
    payload = response.json()
    assert payload["score"] == 72.5
    assert payload["grade"] == "B"
    assert payload["methodology_version"] == "token-v1"
    assert payload["holder_distribution_score"] == 18.0
    assert payload["top_holder_share"] == 0.25


def test_missing_token_score_returns_404() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/scores/tokens/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Token not found"}


def test_token_score_leaderboard() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/scores/tokens",
        params={"limit": 10, "offset": 5, "grade": "B"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["token_address"] == "mint"
    assert payload["items"][0]["methodology_version"] == "token-v1"
    assert payload["items"][0]["updated_at"] is not None


def test_token_score_leaderboard_validates_grade() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/scores/tokens", params={"grade": "Z"})

    assert response.status_code == 422


def test_wallet_score_leaderboard() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/scores/wallets",
        params={"limit": 10, "offset": 5, "grade": "B"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 10
    assert payload["offset"] == 5
    assert payload["items"][0]["wallet_address"] == "wallet"
    assert payload["items"][0]["score"] == 72.5


def test_wallet_score_leaderboard_validates_grade() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/scores/wallets", params={"grade": "Z"})

    assert response.status_code == 422


def test_list_alerts_with_filters() -> None:
    client, _ = create_client()

    response = client.get(
        "/api/v1/alerts",
        params={
            "entity_address": "wallet",
            "severity": "high",
            "acknowledged": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["entity_address"] == "wallet"
    assert payload["items"][0]["metadata"] == {"score": 72.5, "grade": "B"}
    assert payload["items"][0]["acknowledged_at"] is None


def test_acknowledge_alert() -> None:
    client, _ = create_client()

    response = client.post("/api/v1/alerts/1/acknowledge")
    missing = client.post("/api/v1/alerts/999/acknowledge")

    assert response.status_code == 200
    assert response.json()["acknowledged_at"] is not None
    assert missing.status_code == 404


def test_monitor_management_api() -> None:
    client, _ = create_client()

    created = client.post("/api/v1/monitors", json={"address": "tracked"})
    listed = client.get("/api/v1/monitors")
    disabled = client.delete("/api/v1/monitors/tracked")
    enabled = client.post("/api/v1/monitors/tracked/enable")

    assert created.status_code == 201
    assert created.json()["wallet_address"] == "tracked"
    assert listed.json()["total"] == 1
    assert disabled.json()["enabled"] is False
    assert enabled.json()["enabled"] is True


def test_unknown_monitor_returns_404() -> None:
    client, _ = create_client()

    response = client.delete("/api/v1/monitors/missing")

    assert response.status_code == 404
