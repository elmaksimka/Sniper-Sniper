from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import httpx

from app.core.logging import get_logger
from app.services.birdeye_client import BirdeyeClient, TokenTopTrader
from app.services.dexscreener_client import DexScreenerClient


@dataclass(frozen=True, slots=True)
class ExternalTraderCandidate:
    address: str
    profitable_tokens: int
    realized_pnl_usd: float
    risk_tags: tuple[str, ...]
    source_token_address: str = ""
    token_rank: int = 0
    trader_rank: int = 0


@dataclass(frozen=True, slots=True)
class ExternalCandidateBatch:
    candidates: tuple[ExternalTraderCandidate, ...]
    token_count: int


class TopTraderCandidateSource:
    """Find profitable wallets behind fresh profiled DexScreener tokens."""

    RISK_TAGS = frozenset({"dev", "bundler", "sniper", "insider"})

    def __init__(
        self,
        dexscreener: DexScreenerClient,
        birdeye: BirdeyeClient,
        *,
        token_limit: int = 5,
        traders_per_token: int = 10,
        maximum_pair_age_hours: float = 24,
        minimum_realized_pnl_usd: float = 0,
        minimum_realized_roi: float = 0,
    ) -> None:
        self.dexscreener = dexscreener
        self.birdeye = birdeye
        self.token_limit = token_limit
        self.traders_per_token = traders_per_token
        self.maximum_pair_age_hours = maximum_pair_age_hours
        self.minimum_realized_pnl_usd = minimum_realized_pnl_usd
        self.minimum_realized_roi = minimum_realized_roi
        self.logger = get_logger("top-trader-candidate-source")

    async def discover(self) -> ExternalCandidateBatch:
        profiles = await self.dexscreener.get_latest_solana_profiles()
        ranked: list[tuple[float, str]] = []
        now_ms = datetime.now(UTC).timestamp() * 1000
        for token_address in profiles:
            metrics = await self.dexscreener.get_token_trending_metrics(
                token_address
            )
            if metrics is None or metrics.pair_created_at_ms is None:
                continue
            age_hours = (now_ms - metrics.pair_created_at_ms) / 3_600_000
            if age_hours < 0 or age_hours > self.maximum_pair_age_hours:
                continue
            ranked.append((metrics.trend_score, token_address))
        ranked.sort(reverse=True)

        by_wallet: dict[str, tuple[int, int, str, list[TokenTopTrader]]] = {}
        selected = ranked[: self.token_limit]
        for token_rank, (_, token_address) in enumerate(selected, start=1):
            try:
                traders = await self.birdeye.get_top_traders(
                    token_address,
                    limit=self.traders_per_token,
                )
            except httpx.HTTPError:
                self.logger.exception(
                    "token_top_traders_fetch_failed",
                    token=token_address,
                )
                continue
            for trader_rank, trader in enumerate(traders, start=1):
                if trader.realized_pnl_usd < self.minimum_realized_pnl_usd:
                    continue
                if trader.realized_roi < self.minimum_realized_roi:
                    continue
                existing = by_wallet.get(trader.wallet)
                if existing is None:
                    by_wallet[trader.wallet] = (
                        token_rank,
                        trader_rank,
                        token_address,
                        [trader],
                    )
                else:
                    existing[3].append(trader)

        candidates = []
        for wallet, (
            token_rank,
            trader_rank,
            token_address,
            wins,
        ) in by_wallet.items():
            risk_tags = tuple(
                sorted(
                    {
                        tag
                        for win in wins
                        for tag in win.tags
                        if tag in self.RISK_TAGS
                    }
                )
            )
            candidates.append(
                ExternalTraderCandidate(
                    address=wallet,
                    profitable_tokens=len(wins),
                    realized_pnl_usd=sum(
                        win.realized_pnl_usd for win in wins
                    ),
                    risk_tags=risk_tags,
                    source_token_address=token_address,
                    token_rank=token_rank,
                    trader_rank=trader_rank,
                )
            )
        candidates.sort(
            key=lambda candidate: (candidate.token_rank, candidate.trader_rank),
        )
        self.logger.info(
            "top_trader_candidates_discovered",
            tokens=len(selected),
            candidates=len(candidates),
            safe_candidates=sum(
                not candidate.risk_tags for candidate in candidates
            ),
        )
        return ExternalCandidateBatch(tuple(candidates), len(selected))
