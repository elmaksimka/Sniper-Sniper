from __future__ import annotations

from dataclasses import dataclass

from app.core.logging import get_logger
from app.services.dexscreener_client import (
    DexScreenerClient,
    DexScreenerTopTrader,
)


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
    token_addresses: tuple[str, ...] = ()


class TopTraderCandidateSource:
    """Find profitable wallets in DexScreener's Solana H24 order."""

    def __init__(
        self,
        dexscreener: DexScreenerClient,
        *,
        token_limit: int = 5,
        traders_per_token: int = 10,
        minimum_realized_pnl_usd: float = 0,
        minimum_realized_roi: float = 0,
        excluded_token_addresses: tuple[str, ...] = (),
    ) -> None:
        self.dexscreener = dexscreener
        self.token_limit = token_limit
        self.traders_per_token = traders_per_token
        self.minimum_realized_pnl_usd = minimum_realized_pnl_usd
        self.minimum_realized_roi = minimum_realized_roi
        self.excluded_token_addresses = set(excluded_token_addresses)
        self.logger = get_logger("top-trader-candidate-source")

    def exclude_tokens(self, token_addresses: list[str]) -> None:
        self.excluded_token_addresses = set(token_addresses)

    async def discover(self) -> ExternalCandidateBatch:
        trending = await self.dexscreener.get_solana_trending_h24()

        by_wallet: dict[
            str,
            tuple[int, int, str, list[DexScreenerTopTrader]],
        ] = {}
        selected = [
            token
            for token in trending
            if token.token_address not in self.excluded_token_addresses
        ][: self.token_limit]
        for token_rank, token in enumerate(selected, start=1):
            token_address = token.token_address
            traders = await self.dexscreener.get_pair_top_traders(
                token.pair_address,
                limit=self.traders_per_token,
            )
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
            risk_tags: tuple[str, ...] = ()
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
        return ExternalCandidateBatch(
            tuple(candidates),
            len(selected),
            tuple(token.token_address for token in selected),
        )
