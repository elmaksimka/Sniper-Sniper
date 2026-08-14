from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256

from app.infrastructure.models import (
    PaperCopyOrder,
    PaperCopyPortfolio,
    PaperCopyPosition,
)
from app.listeners.helius_client import HeliusClient
from app.repositories.paper_copy_repository import PaperCopyRepository
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote
from app.services.paper_copy_service import PaperCopyService


@dataclass(frozen=True, slots=True)
class PaperCopyReconciliationResult:
    wallets_checked: int = 0
    positions_checked: int = 0
    positions_reduced: int = 0
    positions_closed: int = 0
    positions_increased: int = 0
    positions_deferred: int = 0
    positions_repriced: int = 0
    prices_deferred: int = 0


class PaperCopyReconciliationService:
    """Align paper-copy source positions with confirmed on-chain balances."""

    def __init__(
        self,
        repository: PaperCopyRepository,
        balances: HeliusClient,
        market_data: DexScreenerClient | None = None,
    ) -> None:
        self.repository = repository
        self.balances = balances
        self.market_data = market_data or DexScreenerClient()
        self.paper_copy = PaperCopyService(repository, self.market_data)

    async def reconcile(
        self,
        portfolio_wallet: str,
        *,
        refresh_prices: bool = False,
    ) -> PaperCopyReconciliationResult:
        portfolio = await self.repository.get_portfolio(portfolio_wallet)
        if portfolio is None or not portfolio.enabled:
            return PaperCopyReconciliationResult()

        positions = await self.repository.list_open_positions(portfolio.id)
        pending = await self.repository.pending_position_keys(portfolio.id)
        by_wallet: dict[str, list[PaperCopyPosition]] = {}
        deferred = 0
        for position in positions:
            key = (position.source_wallet, position.token_address)
            if key in pending:
                deferred += 1
                continue
            by_wallet.setdefault(position.source_wallet, []).append(position)

        reduced = closed = increased = checked = repriced = prices_deferred = 0
        for wallet, wallet_positions in by_wallet.items():
            current = await self.balances.get_token_balances(wallet)
            for position in wallet_positions:
                checked += 1
                actual = max(0.0, current.get(position.token_address, 0.0))
                tracked = max(0.0, position.source_quantity)
                tolerance = max(1e-9, tracked * 1e-9)
                quote = None
                if refresh_prices or actual < tracked - tolerance:
                    quote = await self._get_market_quote(position.token_address)
                if actual > tracked + tolerance:
                    position.source_quantity = actual
                    position.updated_at = datetime.now(UTC)
                    increased += 1
                elif actual < tracked - tolerance:
                    await self._reduce_position(position, portfolio, actual, quote)
                    reduced += 1
                    if actual <= tolerance:
                        closed += 1

                if refresh_prices and position.quantity > 0:
                    if quote is None or quote.price_usd <= 0:
                        prices_deferred += 1
                    else:
                        position.last_price_usd = quote.price_usd
                        position.updated_at = datetime.now(UTC)
                        repriced += 1

        if increased or repriced:
            portfolio.updated_at = datetime.now(UTC)
            await self.repository.session.commit()
        return PaperCopyReconciliationResult(
            wallets_checked=len(by_wallet),
            positions_checked=checked,
            positions_reduced=reduced,
            positions_closed=closed,
            positions_increased=increased,
            positions_deferred=deferred,
            positions_repriced=repriced,
            prices_deferred=prices_deferred,
        )

    async def _get_market_quote(self, token_address: str) -> TokenMarketQuote | None:
        try:
            return await self.market_data.get_token_quote(token_address)
        except Exception:
            return None

    async def _reduce_position(
        self,
        position: PaperCopyPosition,
        portfolio: PaperCopyPortfolio,
        actual: float,
        quote: TokenMarketQuote | None,
    ) -> None:
        now = datetime.now(UTC)
        source_amount = max(0.0, position.source_quantity - actual)
        fingerprint = (
            f"{position.portfolio_id}:{position.source_wallet}:"
            f"{position.token_address}:{position.source_quantity:.12g}:{actual:.12g}"
        )
        order = PaperCopyOrder(
            portfolio_id=position.portfolio_id,
            source_wallet=position.source_wallet,
            source_signature=f"reconcile-{sha256(fingerprint.encode()).hexdigest()[:40]}",
            token_address=position.token_address,
            side="sell",
            source_amount=source_amount,
            source_transaction_at=now,
            execute_after=now,
            status="pending",
            attempts=0,
            reason="on-chain balance reconciliation",
            notification_sent=False,
            created_at=now,
        )
        self.repository.session.add(order)
        await self.repository.session.flush()

        if quote is None:
            quote = TokenMarketQuote(
                price_usd=max(0.0, position.last_price_usd),
                pair_url=None,
            )
        await self.paper_copy._fill_sell(order, portfolio, position, quote)
