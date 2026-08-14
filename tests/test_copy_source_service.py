from types import SimpleNamespace

import pytest

from app.services.copy_source_service import CopySourceService


class FakeHeartbeats:
    async def list_by_prefix(self, prefix: str, *, limit: int) -> list[object]:
        assert prefix == "candidate:"
        assert limit == 5_000
        return [
            SimpleNamespace(
                service_name="candidate:aa-two",
                details={"score_after": 80, "copy_score": 75, "copy_mode": "automatic"},
            ),
            SimpleNamespace(
                service_name="candidate:aa-one",
                details={"score_after": 95, "copy_score": 83, "copy_mode": "automatic"},
            ),
            SimpleNamespace(
                service_name="candidate:ab",
                details={"score_after": 90, "copy_score": 70, "copy_mode": "manual"},
            ),
            SimpleNamespace(
                service_name="candidate-pair:token",
                details={"score_after": 99, "copy_score": 99, "copy_mode": "automatic"},
            ),
        ]


class FakeMonitors:
    def __init__(self) -> None:
        self.added: list[str] = []

    async def add(self, address: str) -> None:
        self.added.append(address)


class FakeScores:
    async def get_by_wallet_address(self, address: str) -> SimpleNamespace:
        return SimpleNamespace(
            realized_position_count=19,
            realized_pnl_sol=2,
            realized_pnl_ex_top_position_sol=1,
            pnl_concentration_ratio=0.5,
        )


@pytest.mark.asyncio
async def test_reconcile_returns_and_monitors_all_current_aa_wallets() -> None:
    monitors = FakeMonitors()
    service = CopySourceService(
        FakeHeartbeats(),  # type: ignore[arg-type]
        monitors,  # type: ignore[arg-type]
    )

    addresses = await service.reconcile()

    assert addresses == ("aa-one", "aa-two")
    assert monitors.added == ["aa-one", "aa-two"]


@pytest.mark.asyncio
async def test_probation_rejects_automatic_wallet_without_robust_history() -> None:
    service = CopySourceService(
        FakeHeartbeats(),  # type: ignore[arg-type]
        scores=FakeScores(),  # type: ignore[arg-type]
    )

    assert await service.list_addresses() == ()
