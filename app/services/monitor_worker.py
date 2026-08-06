from __future__ import annotations

from app.core.logging import get_logger
from app.listeners.transaction_scanner import TransactionScanner
from app.repositories.monitor_repository import MonitorRepository
from app.services.token_detection_service import TokenDetectionService


class MonitorWorker:
    def __init__(
        self,
        monitors: MonitorRepository,
        scanner: TransactionScanner,
        detection: TokenDetectionService,
        page_size: int,
        max_pages: int,
    ) -> None:
        self.monitors = monitors
        self.scanner = scanner
        self.detection = detection
        self.page_size = page_size
        self.max_pages = max_pages
        self.logger = get_logger("monitor-worker")

    async def run_once(self) -> int:
        processed = 0
        monitors = await self.monitors.list_all(enabled_only=True)

        for monitor in monitors:
            address = monitor.wallet.address
            try:
                batch = await self.scanner.scan_since(
                    address,
                    checkpoint_signature=monitor.checkpoint_signature,
                    page_size=self.page_size,
                    max_pages=self.max_pages,
                )
                if not batch.complete:
                    await self.monitors.mark_error(
                        monitor,
                        "Catch-up exceeded page boundary; checkpoint unchanged",
                    )
                    continue

                if batch.transactions:
                    await self.detection.process_transactions(batch.transactions)
                    processed += len(batch.transactions)

                checkpoint = (
                    batch.newest_signature or monitor.checkpoint_signature
                )
                await self.monitors.mark_success(monitor, checkpoint)
            except Exception as error:
                await self.monitors.mark_error(monitor, str(error))
                self.logger.exception(
                    "wallet_scan_failed",
                    wallet=address,
                    error=str(error),
                )

        return processed
