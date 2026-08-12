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
                details={"score_after": 80, "copy_score": 75},
            ),
            SimpleNamespace(
                service_name="candidate:aa-one",
                details={"score_after": 95, "copy_score": 83},
            ),
            SimpleNamespace(
                service_name="candidate:ab",
                details={"score_after": 90, "copy_score": 70},
            ),
            SimpleNamespace(
                service_name="candidate-pair:token",
                details={"score_after": 99, "copy_score": 99},
            ),
        ]


class FakeMonitors:
    def __init__(self) -> None:
        self.added: list[str] = []

    async def add(self, address: str) -> None:
        self.added.append(address)


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
