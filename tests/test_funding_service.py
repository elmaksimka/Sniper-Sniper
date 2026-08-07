from typing import Any

import pytest

from app.core.funding import WalletFundingAnalytics
from app.infrastructure.models import FundingTransfer, Wallet
from app.services.funding_service import FundingService


class FakeFundingRepository:
    def __init__(self) -> None:
        self.transfer: FundingTransfer | None = None
        self.create_calls = 0

    async def get_by_identity(
        self, signature: str, instruction_index: str
    ) -> FundingTransfer | None:
        if (
            self.transfer is not None
            and self.transfer.signature == signature
            and self.transfer.instruction_index == instruction_index
        ):
            return self.transfer
        return None

    async def create(self, transfer: FundingTransfer) -> FundingTransfer:
        self.create_calls += 1
        transfer.id = self.create_calls
        self.transfer = transfer
        return transfer

    async def get_wallet_analytics(
        self,
        wallet_id: int,
        wallet_address: str,
        counterparty_limit: int,
    ) -> WalletFundingAnalytics:
        assert (wallet_id, wallet_address, counterparty_limit) == (1, "wallet", 5)
        return WalletFundingAnalytics(
            wallet_address="wallet",
            incoming_transfer_count=2,
            outgoing_transfer_count=1,
            incoming_sol=2.0,
            outgoing_sol=0.5,
            net_sol=1.5,
            unique_funders=1,
            unique_destinations=1,
            first_funder="funder",
            first_funding_at=None,
            counterparties=[],
        )


class FakeWalletRepository:
    async def get_by_address(self, address: str) -> Wallet | None:
        return Wallet(id=1, address=address) if address == "wallet" else None


@pytest.mark.asyncio
async def test_create_transfer_is_idempotent() -> None:
    service = FundingService(None)  # type: ignore[arg-type]
    repository = FakeFundingRepository()
    service_with_fake: Any = service
    service_with_fake.repository = repository

    first = await service.create_transfer(1, 2, 0.5, "sig", "outer:0")
    second = await service.create_transfer(1, 2, 0.5, "sig", "outer:0")

    assert second is first
    assert repository.create_calls == 1


@pytest.mark.asyncio
async def test_get_wallet_analytics_checks_wallet_existence() -> None:
    service = FundingService(None)  # type: ignore[arg-type]
    repository = FakeFundingRepository()
    service_with_fake: Any = service
    service_with_fake.repository = repository
    service_with_fake.wallets = FakeWalletRepository()

    analytics = await service.get_wallet_analytics("wallet", 5)
    missing = await service.get_wallet_analytics("missing", 5)

    assert analytics is not None
    assert analytics.net_sol == 1.5
    assert missing is None
