from __future__ import annotations

from app.core.event_bus import EventBus
from app.core.events import TradeScored, TokenUpdated, TradeObserved, WalletUpdated
from app.services.token_service import TokenService
from app.services.trade_service import TradeService
from app.services.wallet_service import WalletService


class TradeCollector:
    """Persist normalized trade events and their related entities."""

    def __init__(
        self,
        event_bus: EventBus,
        token_service: TokenService,
        wallet_service: WalletService,
        trade_service: TradeService,
    ) -> None:
        self.event_bus = event_bus
        self.token_service = token_service
        self.wallet_service = wallet_service
        self.trade_service = trade_service

    def register(self) -> None:
        self.event_bus.subscribe(TradeObserved, self.handle_trade_observed)

    async def handle_trade_observed(self, event: TradeObserved) -> None:
        token = await self.token_service.create_token(event.token_address)
        wallet = await self.wallet_service.create_wallet(event.wallet)

        await self.trade_service.create_trade(
            token_id=token.id,
            wallet_id=wallet.id,
            side=event.side,
            amount=event.amount,
            price=event.price,
            sol_change=event.sol_change,
            signature=event.signature,
            timestamp=event.transaction_at,
        )

        await self.event_bus.publish(WalletUpdated(wallet=wallet.address))
        await self.event_bus.publish(TokenUpdated(token_address=token.address))
        await self.event_bus.publish(
            TradeScored(
                token_address=token.address,
                wallet=wallet.address,
                side=event.side,
                amount=event.amount,
                sol_change=event.sol_change,
                signature=event.signature,
                transaction_at=event.transaction_at,
            )
        )
