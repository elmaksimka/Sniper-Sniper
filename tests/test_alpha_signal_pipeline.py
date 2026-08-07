from types import SimpleNamespace
from typing import Any
from datetime import UTC, datetime, timedelta

import pytest

from app.collectors.alpha_signal_collector import AlphaSignalCollector
from app.core.event_bus import EventBus
from app.core.events import AlphaSignalGenerated, TradeScored
from app.core.trader_style import TraderStyleProfile
from app.infrastructure.models import Alert
from app.services.dexscreener_client import TokenMarketQuote


class AddressRepository:
    def __init__(self, entity: object) -> None:
        self.entity = entity

    async def get_by_address(self, address: str) -> object:
        return self.entity


class ScoreRepository:
    def __init__(self, score: float, grade: str) -> None:
        self.snapshot = SimpleNamespace(score=score, grade=grade)

    async def get_by_wallet_id(self, entity_id: int) -> object:
        return self.snapshot

    async def get_by_token_id(self, entity_id: int) -> object:
        return self.snapshot

    async def list_top_buyers_for_token(
        self,
        token_address: str,
        minimum_score: float,
    ) -> list[str]:
        return ["wallet", "second-holder"]


class EarlyScoring:
    def __init__(self, score: float, trades: int = 3, wallets: int = 2) -> None:
        self.score = SimpleNamespace(
            score=score,
            grade="C",
            methodology_version="early-token-v1",
            observed_trade_count=trades,
            observed_wallet_count=wallets,
        )

    async def score_early_token(self, address: str) -> object:
        return self.score


class FakeAlerts:
    def __init__(self) -> None:
        self.calls = 0

    async def create_alpha_signal(self, event: TradeScored, *_: Any) -> Alert:
        self.calls += 1
        return Alert(severity="high", message="alpha")


class FakeMarketData:
    def __init__(self, quote: TokenMarketQuote | None) -> None:
        self.quote = quote
        self.calls = 0

    async def get_token_quote(self, token_address: str) -> TokenMarketQuote | None:
        self.calls += 1
        return self.quote


class FakeTraderStyle:
    async def evaluate(self, wallet_address: str) -> TraderStyleProfile:
        return TraderStyleProfile(
            eligible=True,
            reason=None,
            total_trades=20,
            unique_tokens=8,
            max_trades_60s=3,
            max_distinct_tokens_60s=2,
            max_trades_per_token=3,
            max_side_switches_per_token=1,
            rapid_round_trips=0,
            long_hold_positions=2,
        )


def qualifying_market() -> FakeMarketData:
    return FakeMarketData(
        TokenMarketQuote(
            price_usd=0.01,
            pair_url="https://dexscreener.com/solana/pair",
            liquidity_usd=20_000,
            volume_5m_usd=7_500,
            buys_5m=8,
            sells_5m=4,
            pair_created_at_ms=int(datetime.now(UTC).timestamp() * 1000),
        )
    )


@pytest.mark.asyncio
async def test_qualifying_buy_emits_alpha_signal() -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(82, "A"),  # type: ignore[arg-type]
        scoring=EarlyScoring(70),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=45,
        token_min_trades=3,
        token_min_wallets=2,
        maximum_trade_age_seconds=300,
        market_data=qualifying_market(),  # type: ignore[arg-type]
        market_min_liquidity_usd=15_000,
        market_min_volume_5m_usd=5_000,
        market_min_transactions_5m=10,
        market_max_pair_age_minutes=60,
        trader_style=FakeTraderStyle(),  # type: ignore[arg-type]
    )
    generated: list[AlphaSignalGenerated] = []

    async def capture(event: AlphaSignalGenerated) -> None:
        generated.append(event)

    collector.register()
    event_bus.subscribe(AlphaSignalGenerated, capture)
    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side="buy",
            amount=100,
            sol_change=-2.5,
            signature="signature",
        )
    )

    assert alerts.calls == 1
    assert len(generated) == 1
    assert generated[0].wallet_score == 82
    assert generated[0].token_score == 70
    assert generated[0].sol_amount == 2.5
    assert generated[0].market_liquidity_usd == 20_000
    assert generated[0].market_volume_5m_usd == 7_500
    assert generated[0].observed_top_trader_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("side", "wallet_score", "token_score", "signature"),
    [
        ("sell", 90, 90, "signature"),
        ("buy", 64, 90, "signature"),
        ("buy", 90, 44, "signature"),
        ("buy", 90, 90, None),
    ],
)
async def test_non_qualifying_trade_is_filtered(
    side: str,
    wallet_score: float,
    token_score: float,
    signature: str | None,
) -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(wallet_score, "B"),  # type: ignore[arg-type]
        scoring=EarlyScoring(token_score),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=45,
        token_min_trades=3,
        token_min_wallets=2,
        maximum_trade_age_seconds=300,
        market_data=qualifying_market(),  # type: ignore[arg-type]
        market_min_liquidity_usd=15_000,
        market_min_volume_5m_usd=5_000,
        market_min_transactions_5m=10,
        market_max_pair_age_minutes=60,
        trader_style=FakeTraderStyle(),  # type: ignore[arg-type]
    )
    collector.register()

    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side=side,
            amount=100,
            sol_change=-2.5,
            signature=signature,
        )
    )

    assert alerts.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(("trades", "wallets"), [(2, 2), (3, 1)])
async def test_insufficient_early_evidence_is_filtered(
    trades: int,
    wallets: int,
) -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(82, "A"),  # type: ignore[arg-type]
        scoring=EarlyScoring(80, trades, wallets),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=45,
        token_min_trades=3,
        token_min_wallets=2,
        maximum_trade_age_seconds=300,
        market_data=qualifying_market(),  # type: ignore[arg-type]
        market_min_liquidity_usd=15_000,
        market_min_volume_5m_usd=5_000,
        market_min_transactions_5m=10,
        market_max_pair_age_minutes=60,
        trader_style=FakeTraderStyle(),  # type: ignore[arg-type]
    )
    collector.register()

    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side="buy",
            amount=100,
            sol_change=-2.5,
            signature="signature",
        )
    )

    assert alerts.calls == 0


@pytest.mark.asyncio
async def test_historical_buy_does_not_emit_alpha_signal() -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(82, "A"),  # type: ignore[arg-type]
        scoring=EarlyScoring(80),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=45,
        token_min_trades=3,
        token_min_wallets=2,
        maximum_trade_age_seconds=300,
        market_data=qualifying_market(),  # type: ignore[arg-type]
        market_min_liquidity_usd=15_000,
        market_min_volume_5m_usd=5_000,
        market_min_transactions_5m=10,
        market_max_pair_age_minutes=60,
        trader_style=FakeTraderStyle(),  # type: ignore[arg-type]
    )
    collector.register()

    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side="buy",
            amount=100,
            sol_change=-2.5,
            signature="historical-signature",
            transaction_at=datetime.now(UTC) - timedelta(hours=1),
        )
    )

    assert alerts.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "market",
    [
        TokenMarketQuote(
            price_usd=0.01,
            pair_url=None,
            liquidity_usd=14_999,
            volume_5m_usd=10_000,
            buys_5m=10,
        ),
        TokenMarketQuote(
            price_usd=0.01,
            pair_url=None,
            liquidity_usd=20_000,
            volume_5m_usd=4_999,
            buys_5m=10,
        ),
        TokenMarketQuote(
            price_usd=0.01,
            pair_url=None,
            liquidity_usd=20_000,
            volume_5m_usd=10_000,
            buys_5m=6,
            sells_5m=3,
        ),
        TokenMarketQuote(
            price_usd=0.01,
            pair_url=None,
            liquidity_usd=20_000,
            volume_5m_usd=10_000,
            buys_5m=10,
            pair_created_at_ms=int(
                (datetime.now(UTC) - timedelta(hours=2)).timestamp() * 1000
            ),
        ),
        None,
    ],
)
async def test_weak_or_missing_market_is_filtered(
    market: TokenMarketQuote | None,
) -> None:
    event_bus = EventBus()
    alerts = FakeAlerts()
    collector = AlphaSignalCollector(
        event_bus=event_bus,
        wallets=AddressRepository(SimpleNamespace(id=1)),  # type: ignore[arg-type]
        wallet_scores=ScoreRepository(82, "A"),  # type: ignore[arg-type]
        scoring=EarlyScoring(80, trades=10, wallets=5),  # type: ignore[arg-type]
        alerts=alerts,  # type: ignore[arg-type]
        wallet_threshold=65,
        token_threshold=45,
        token_min_trades=10,
        token_min_wallets=5,
        maximum_trade_age_seconds=300,
        market_data=FakeMarketData(market),  # type: ignore[arg-type]
        market_min_liquidity_usd=15_000,
        market_min_volume_5m_usd=5_000,
        market_min_transactions_5m=10,
        market_max_pair_age_minutes=60,
        trader_style=FakeTraderStyle(),  # type: ignore[arg-type]
    )
    collector.register()

    await event_bus.publish(
        TradeScored(
            token_address="token",
            wallet="wallet",
            side="buy",
            amount=100,
            sol_change=-2.5,
            signature="signature",
        )
    )

    assert alerts.calls == 0
