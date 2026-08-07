from typing import Any

import pytest

from app.infrastructure.models import FundingTransfer
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
