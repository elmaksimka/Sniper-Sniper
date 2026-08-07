from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import ScoreUpdated, TradeScored
from app.core.scoring import EarlyTokenScore
from app.infrastructure.models import Alert, WalletScoreSnapshot
from app.repositories.alert_repository import AlertRepository
from app.services.dexscreener_client import TokenMarketQuote
from app.core.trader_style import TraderStyleProfile


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = AlertRepository(session)

    async def create_score_alert(self, event: ScoreUpdated) -> Alert | None:
        severity = "critical" if event.grade == "A" else "high"
        dedupe_key = (
            f"{event.entity_type}-score:{event.entity}:"
            f"{event.methodology_version}:{event.grade}"
        )
        label = event.entity_type.capitalize()
        return await self.repository.create_if_absent(
            {
                "entity_type": event.entity_type,
                "entity_address": event.entity,
                "alert_type": f"{event.entity_type}_score_grade",
                "severity": severity,
                "message": (
                    f"{label} {event.entity} reached grade {event.grade} "
                    f"with score {event.score:.2f}"
                ),
                "details": {
                    "score": event.score,
                    "grade": event.grade,
                    "methodology_version": event.methodology_version,
                },
                "dedupe_key": dedupe_key,
                "created_at": datetime.now(UTC),
            }
        )

    async def create_alpha_signal(
        self,
        event: TradeScored,
        wallet_score: WalletScoreSnapshot,
        token_score: EarlyTokenScore,
        market: TokenMarketQuote | None = None,
        top_trader_count: int = 1,
        trader_style: TraderStyleProfile | None = None,
    ) -> Alert | None:
        if not event.signature:
            return None
        severity = (
            "critical"
            if wallet_score.grade == "A" and token_score.grade == "A"
            else "high"
        )
        details = {
            "wallet": event.wallet,
            "wallet_score": wallet_score.score,
            "wallet_grade": wallet_score.grade,
            "token_score": token_score.score,
            "token_grade": token_score.grade,
            "token_score_methodology": token_score.methodology_version,
            "observed_trade_count": token_score.observed_trade_count,
            "observed_wallet_count": token_score.observed_wallet_count,
            "token_amount": event.amount,
            "sol_amount": abs(event.sol_change),
            "signature": event.signature,
            "observed_top_trader_count": top_trader_count,
        }
        if market is not None:
            details.update(
                {
                    "market_price_usd": market.price_usd,
                    "market_pair_url": market.pair_url,
                    "market_liquidity_usd": market.liquidity_usd,
                    "market_volume_5m_usd": market.volume_5m_usd,
                    "market_buys_5m": market.buys_5m,
                    "market_sells_5m": market.sells_5m,
                }
            )
        if trader_style is not None:
            details.update(
                {
                    "trader_long_hold_positions": (
                        trader_style.long_hold_positions
                    ),
                    "trader_max_trades_60s": trader_style.max_trades_60s,
                    "trader_max_distinct_tokens_60s": (
                        trader_style.max_distinct_tokens_60s
                    ),
                    "trader_rapid_round_trips": (
                        trader_style.rapid_round_trips
                    ),
                    "trader_max_side_switches_per_token": (
                        trader_style.max_side_switches_per_token
                    ),
                }
            )
        return await self.repository.create_if_absent(
            {
                "entity_type": "token",
                "entity_address": event.token_address,
                "alert_type": "top_trader_token_buy",
                "severity": severity,
                "message": (
                    f"Top trader {event.wallet} bought token "
                    f"{event.token_address}: wallet {wallet_score.score:.2f} "
                    f"({wallet_score.grade}), token {token_score.score:.2f} "
                    f"({token_score.grade})"
                ),
                "details": details,
                "dedupe_key": (
                    f"alpha-buy:{event.signature}:"
                    f"{event.wallet}:{event.token_address}"
                ),
                "created_at": datetime.now(UTC),
            }
        )

    async def list_alerts(
        self,
        limit: int,
        offset: int,
        entity_address: str | None,
        severity: str | None,
        acknowledged: bool | None,
        entity_type: str | None = None,
    ) -> tuple[list[Alert], int]:
        filters = (entity_address, severity, acknowledged, entity_type)
        return (
            await self.repository.list_all(limit, offset, *filters),
            await self.repository.count(*filters),
        )

    async def acknowledge(self, alert_id: int) -> Alert | None:
        return await self.repository.acknowledge(alert_id)
