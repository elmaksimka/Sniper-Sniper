from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.listeners.helius_client import HeliusClient
from app.listeners.transaction_scanner import TransactionScanner
from app.repositories.heartbeat_repository import HeartbeatRepository
from app.services.token_detection_service import TokenDetectionService


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    processed_transactions: int
    newest_signature: str | None
    complete: bool


class DexDiscoveryService:
    """Sample recent DEX program activity and ingest fee-payer trades."""

    def __init__(
        self,
        client: HeliusClient,
        scanner: TransactionScanner,
        detection: TokenDetectionService,
        cursors: HeartbeatRepository,
        page_size: int,
        max_pages: int,
    ) -> None:
        self.client = client
        self.scanner = scanner
        self.detection = detection
        self.cursors = cursors
        self.page_size = page_size
        self.max_pages = max_pages

    async def scan_program(self, program_id: str) -> DiscoveryResult:
        cursor_name = f"discovery:{program_id[:48]}"
        cursor = await self.cursors.get(cursor_name)
        checkpoint = (
            cursor.details.get("signature")
            if cursor is not None and isinstance(cursor.details, dict)
            else None
        )
        if not isinstance(checkpoint, str):
            checkpoint = None

        rows: list[dict[str, Any]] = []
        before: str | None = None
        newest_signature: str | None = None
        complete = checkpoint is None

        for _ in range(self.max_pages):
            response = await self.client.get_signature_page(
                program_id,
                self.page_size,
                before,
            )
            result = response.get("result")
            page = (
                [row for row in result if isinstance(row, dict)]
                if isinstance(result, list)
                else []
            )
            if not page:
                complete = True
                break
            if newest_signature is None:
                candidate = page[0].get("signature")
                newest_signature = candidate if isinstance(candidate, str) else None

            for row in page:
                signature = row.get("signature")
                if signature == checkpoint:
                    complete = True
                    break
                rows.append(row)
            if complete and checkpoint is not None:
                break
            if len(page) < self.page_size:
                complete = True
                break
            candidate = page[-1].get("signature")
            before = candidate if isinstance(candidate, str) else None
            if not before:
                break

        # On a cold start we intentionally sample only the configured window.
        if checkpoint is None:
            complete = True
        processed = 0
        for row in reversed(rows):
            signature = row.get("signature")
            if (
                not isinstance(signature, str)
                or not signature
                or row.get("err") is not None
            ):
                continue
            response = await self.client.get_transaction(signature)
            transaction = response.get("result")
            if not isinstance(transaction, dict):
                continue
            wallet = self._fee_payer(transaction)
            if wallet is None:
                continue
            normalized = self.scanner.normalize_transaction(
                transaction,
                wallet,
                signature,
            )
            if not normalized["trades"]:
                continue
            await self.detection.process_transactions([normalized])
            processed += 1

        if newest_signature:
            await self.cursors.beat(
                cursor_name,
                "dex-discovery",
                {
                    "signature": newest_signature,
                    "program_id": program_id,
                    "processed_transactions": processed,
                },
            )
        return DiscoveryResult(processed, newest_signature, complete)

    @staticmethod
    def _fee_payer(transaction: dict[str, Any]) -> str | None:
        account_keys = (
            transaction.get("transaction", {})
            .get("message", {})
            .get("accountKeys", [])
        )
        if not isinstance(account_keys, list) or not account_keys:
            return None
        first = account_keys[0]
        if isinstance(first, str):
            return first
        if isinstance(first, dict):
            pubkey = first.get("pubkey")
            if isinstance(pubkey, str) and first.get("signer") is not False:
                return pubkey
        return None
