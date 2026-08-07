from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.analyzer import TokenTrade
from app.core.event_bus import EventBus
from app.core.events import NativeTransferObserved, TokenCreated, TradeObserved
from app.core.funding import NativeTransfer
from app.listeners.transaction_scanner import TransactionScanner
from app.services.metadata_service import MetadataService
from app.services.token_store import TokenStore


class TokenDetectionService:
    """Publish normalized token and trade events from wallet transactions."""

    def __init__(
        self,
        scanner: TransactionScanner,
        store: TokenStore,
        metadata: MetadataService,
        event_bus: EventBus,
    ) -> None:
        self.scanner = scanner
        self.store = store
        self.metadata = metadata
        self.event_bus = event_bus

    async def scan_wallet(
        self,
        wallet: str,
        limit: int = 10,
    ) -> list[str]:
        transactions = await self.scanner.scan_address(wallet, limit)
        return await self.process_transactions(transactions)

    async def process_transactions(
        self,
        transactions: list[dict[str, Any]],
    ) -> list[str]:
        found: set[str] = set()

        for transaction in transactions:
            trades = [
                trade
                for trade in transaction.get("trades", [])
                if isinstance(trade, TokenTrade)
            ]
            mints = set(transaction.get("tokens", []))
            mints.update(trade.mint for trade in trades)

            for mint in sorted(mints):
                if self.store.exists(mint):
                    continue

                metadata = await self.metadata.get_metadata(mint)
                await self.event_bus.publish(
                    TokenCreated(
                        token_address=mint,
                        creator=metadata.get("creator") or "unknown",
                        symbol=metadata.get("symbol"),
                        name=metadata.get("name"),
                        decimals=metadata.get("decimals"),
                        supply=metadata.get("supply"),
                    )
                )
                self.store.add(mint)
                found.add(mint)

            signature = transaction.get("signature")
            for trade in trades:
                await self.event_bus.publish(
                    TradeObserved(
                        token_address=trade.mint,
                        wallet=trade.wallet,
                        side=trade.side,
                        amount=abs(trade.token_change),
                        price=self._price(trade),
                        sol_change=trade.sol_change,
                        signature=(
                            signature if isinstance(signature, str) else None
                        ),
                        transaction_at=self._timestamp(
                            transaction.get("timestamp")
                        ),
                    )
                )

            if isinstance(signature, str):
                for transfer in transaction.get("native_transfers", []):
                    if not isinstance(transfer, NativeTransfer):
                        continue
                    await self.event_bus.publish(
                        NativeTransferObserved(
                            source=transfer.source,
                            destination=transfer.destination,
                            amount_sol=transfer.amount_sol,
                            instruction_index=transfer.instruction_index,
                            signature=signature,
                            transaction_at=self._timestamp(
                                transaction.get("timestamp")
                            ),
                        )
                    )

        result = sorted(found)
        print("Tokens found:", result)
        return result

    @staticmethod
    def _price(trade: TokenTrade) -> float:
        if (
            trade.token_change == 0
            or trade.token_change * trade.sol_change >= 0
        ):
            return 0.0

        return abs(trade.sol_change / trade.token_change)

    @staticmethod
    def _timestamp(value: object) -> datetime | None:
        if not isinstance(value, int | float):
            return None

        try:
            return datetime.fromtimestamp(value, UTC)
        except (OverflowError, OSError, ValueError):
            return None
