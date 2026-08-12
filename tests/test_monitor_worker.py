from typing import Any

import pytest

from app.infrastructure.models import Wallet, WalletMonitor
from app.listeners.transaction_scanner import TransactionCatchUp
from app.services.monitor_worker import MonitorWorker


class FakeMonitorRepository:
    def __init__(self) -> None:
        self.monitors = [
            WalletMonitor(
                id=1,
                wallet_id=1,
                wallet=Wallet(id=1, address="good"),
                checkpoint_signature="old-good",
            ),
            WalletMonitor(
                id=2,
                wallet_id=2,
                wallet=Wallet(id=2, address="bad"),
                checkpoint_signature="old-bad",
            ),
        ]
        self.successes: list[tuple[str, str | None]] = []
        self.errors: list[tuple[str, str]] = []

    async def list_all(self, enabled_only: bool) -> list[WalletMonitor]:
        assert enabled_only is True
        return self.monitors

    async def mark_success(
        self,
        monitor: WalletMonitor,
        checkpoint: str | None,
    ) -> None:
        self.successes.append((monitor.wallet.address, checkpoint))

    async def mark_error(self, monitor: WalletMonitor, error: str) -> None:
        self.errors.append((monitor.wallet.address, error))


class FakeScanner:
    def __init__(self) -> None:
        self.wallets: list[str] = []

    async def scan_since(self, wallet: str, **_: Any) -> TransactionCatchUp:
        self.wallets.append(wallet)
        if wallet == "bad":
            raise RuntimeError("upstream unavailable")
        return TransactionCatchUp(
            transactions=[{"signature": "new-good"}],
            newest_signature="new-good",
            complete=True,
        )


class FakeDetectionService:
    def __init__(self) -> None:
        self.signatures: list[str] = []

    async def process_transactions(self, transactions: list[dict]) -> list[str]:
        self.signatures.extend(tx["signature"] for tx in transactions)
        return []


@pytest.mark.asyncio
async def test_worker_isolates_wallet_failures_and_advances_success() -> None:
    repository = FakeMonitorRepository()
    detection = FakeDetectionService()
    scanner = FakeScanner()
    worker = MonitorWorker(
        monitors=repository,  # type: ignore[arg-type]
        scanner=scanner,  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        page_size=100,
        max_pages=10,
        priority_addresses=("bad",),
    )

    processed = await worker.run_once()

    assert processed == 1
    assert scanner.wallets == ["bad", "good"]
    assert detection.signatures == ["new-good"]
    assert repository.successes == [("good", "new-good")]
    assert repository.errors == [("bad", "upstream unavailable")]


@pytest.mark.asyncio
async def test_worker_resyncs_overflow_without_replaying_partial_batch() -> None:
    repository = FakeMonitorRepository()
    repository.monitors = repository.monitors[:1]
    detection = FakeDetectionService()

    class OverflowScanner:
        async def scan_since(self, wallet: str, **_: Any) -> TransactionCatchUp:
            return TransactionCatchUp(
                transactions=[],
                newest_signature="current-head",
                complete=False,
            )

    worker = MonitorWorker(
        monitors=repository,  # type: ignore[arg-type]
        scanner=OverflowScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        page_size=100,
        max_pages=10,
    )

    assert await worker.run_once() == 0
    assert detection.signatures == []
    assert repository.successes == [("good", "current-head")]
    assert repository.errors == []
