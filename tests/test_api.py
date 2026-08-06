from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.api.app import create_app
from app.api.dependencies import get_analytics_service, get_read_service
from app.api.dependencies import get_score_snapshot_service, get_scoring_service
from app.api.dependencies import get_alert_service
from app.core.analytics import TokenAnalytics, TokenPosition, WalletAnalytics
from app.core.scoring import WalletScore
from app.infrastructure.models import Alert, Token, Trade, Wallet, WalletScoreSnapshot


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


def create_client() -> tuple[TestClient, FakeReadService]:
    application = create_app()
    service = FakeReadService()
    analytics = FakeAnalyticsService()
    scoring = FakeScoringService()
    snapshots = FakeScoreSnapshotService()
    alerts = FakeAlertService()
    application.dependency_overrides[get_read_service] = lambda: service
    application.dependency_overrides[get_analytics_service] = lambda: analytics
    application.dependency_overrides[get_scoring_service] = lambda: scoring
    application.dependency_overrides[get_score_snapshot_service] = (
        lambda: snapshots
    )
    application.dependency_overrides[get_alert_service] = lambda: alerts
    return TestClient(application), service


def test_health() -> None:
    client, _ = create_client()

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


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
