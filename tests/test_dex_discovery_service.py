from types import SimpleNamespace
from typing import Any

import pytest

from app.services.dex_discovery_service import DexDiscoveryService


class FakeClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.pages: list[str | None] = []

    async def get_signature_page(
        self,
        address: str,
        limit: int,
        before: str | None,
    ) -> dict[str, Any]:
        self.pages.append(before)
        return {"result": self.rows}

    async def get_transaction(self, signature: str) -> dict[str, Any]:
        return {
            "result": {
                "transaction": {
                    "message": {
                        "accountKeys": [
                            {"pubkey": f"wallet-{signature}", "signer": True}
                        ]
                    }
                },
                "meta": {},
            }
        }


class FakeScanner:
    def normalize_transaction(
        self,
        transaction: dict[str, Any],
        wallet: str,
        signature: str,
    ) -> dict[str, Any]:
        return {
            "signature": signature,
            "wallet": wallet,
            "trades": [SimpleNamespace(mint="mint")],
        }


class FakeDetection:
    def __init__(self) -> None:
        self.signatures: list[str] = []

    async def process_transactions(
        self,
        transactions: list[dict[str, Any]],
    ) -> list[str]:
        self.signatures.extend(item["signature"] for item in transactions)
        return []


class FakeCursors:
    def __init__(self, checkpoint: str | None = None) -> None:
        self.checkpoint = checkpoint
        self.saved: dict[str, Any] | None = None

    async def get(self, service_name: str) -> object | None:
        if self.checkpoint is None:
            return None
        return SimpleNamespace(details={"signature": self.checkpoint})

    async def beat(
        self,
        service_name: str,
        instance_id: str,
        details: dict[str, Any],
    ) -> object:
        self.saved = details
        return SimpleNamespace(details=details)


@pytest.mark.asyncio
async def test_cold_start_samples_recent_program_transactions_oldest_first() -> None:
    rows = [
        {"signature": "new", "err": None},
        {"signature": "old", "err": None},
    ]
    client = FakeClient(rows)
    detection = FakeDetection()
    cursors = FakeCursors()
    service = DexDiscoveryService(
        client=client,  # type: ignore[arg-type]
        scanner=FakeScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        cursors=cursors,  # type: ignore[arg-type]
        page_size=2,
        max_pages=1,
    )

    result = await service.scan_program("program")

    assert result.complete is True
    assert result.processed_transactions == 2
    assert detection.signatures == ["old", "new"]
    assert cursors.saved == {
        "signature": "new",
        "program_id": "program",
        "processed_transactions": 2,
    }


@pytest.mark.asyncio
async def test_existing_cursor_processes_only_newer_transactions() -> None:
    rows = [
        {"signature": "new", "err": None},
        {"signature": "checkpoint", "err": None},
        {"signature": "old", "err": None},
    ]
    detection = FakeDetection()
    service = DexDiscoveryService(
        client=FakeClient(rows),  # type: ignore[arg-type]
        scanner=FakeScanner(),  # type: ignore[arg-type]
        detection=detection,  # type: ignore[arg-type]
        cursors=FakeCursors("checkpoint"),  # type: ignore[arg-type]
        page_size=3,
        max_pages=1,
    )

    result = await service.scan_program("program")

    assert result.complete is True
    assert result.processed_transactions == 1
    assert detection.signatures == ["new"]


@pytest.mark.asyncio
async def test_gap_is_sampled_and_cursor_advances() -> None:
    rows = [
        {"signature": "new", "err": None},
        {"signature": "newer-than-missing-checkpoint", "err": None},
    ]
    cursors = FakeCursors("missing")
    service = DexDiscoveryService(
        client=FakeClient(rows),  # type: ignore[arg-type]
        scanner=FakeScanner(),  # type: ignore[arg-type]
        detection=FakeDetection(),  # type: ignore[arg-type]
        cursors=cursors,  # type: ignore[arg-type]
        page_size=2,
        max_pages=1,
    )

    result = await service.scan_program("program")

    assert result.complete is False
    assert result.processed_transactions == 2
    assert cursors.saved is not None
    assert cursors.saved["signature"] == "new"


def test_fee_payer_requires_first_signing_account() -> None:
    assert DexDiscoveryService._fee_payer(
        {
            "transaction": {
                "message": {
                    "accountKeys": [{"pubkey": "wallet", "signer": True}]
                }
            }
        }
    ) == "wallet"
    assert DexDiscoveryService._fee_payer(
        {
            "transaction": {
                "message": {
                    "accountKeys": [{"pubkey": "wallet", "signer": False}]
                }
            }
        }
    ) is None
