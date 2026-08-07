from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import httpx

from app.core.events import AlphaSignalGenerated
from app.core.logging import get_logger


class TelegramNotifier:
    """Deliver alpha signals through the Telegram Bot API."""

    def __init__(
        self,
        bot_token: str,
        recipients: Iterable[str],
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.recipients = tuple(dict.fromkeys(str(item).strip() for item in recipients))
        self._client = http_client
        self.logger = get_logger("telegram-notifier")

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.recipients)

    async def handle_alpha_signal(self, event: AlphaSignalGenerated) -> None:
        if not self.enabled:
            return
        await self.send_text(self.format_alpha_signal(event))

    async def send_text(self, text: str) -> dict[str, bool]:
        if not self.enabled:
            return {}
        results: dict[str, bool] = {}
        for recipient in self.recipients:
            try:
                results[recipient] = await self._send(recipient, text)
            except Exception:
                results[recipient] = False
                self.logger.error(
                    "telegram_delivery_failed",
                    recipient=recipient,
                )
        return results

    async def send_worker_started(
        self,
        monitor_interval_seconds: float,
        discovery_interval_seconds: float,
        discovery_page_size: int,
        discovery_source_count: int,
    ) -> None:
        await self.send_text(
            "\n".join(
                (
                    "✅ Alpha Engine запущено",
                    "",
                    f"Топ-гаманці: кожні {monitor_interval_seconds:g} с",
                    f"DEX discovery: кожні {discovery_interval_seconds:g} с",
                    (
                        "Охоплення discovery: "
                        f"{discovery_page_size} транзакцій × "
                        f"{discovery_source_count} джерела"
                    ),
                    "Telegram alpha-сигнали активні.",
                )
            )
        )

    async def send_worker_status(self, details: dict[str, Any]) -> None:
        failures = int(details.get("discovery_failures", 0))
        rpc_state = "норма" if failures == 0 else f"backoff ({failures})"
        window_minutes = int(details.get("status_window_minutes", 30))
        await self.send_text(
            "\n".join(
                (
                    "🟢 Alpha Engine працює",
                    "",
                    f"RPC/discovery: {rpc_state}",
                    "",
                    (
                        "За весь час: "
                        f"{int(details.get('total_transactions', 0))} "
                        "транзакцій / "
                        f"{int(details.get('total_tokens', 0))} токенів"
                    ),
                    (
                        f"За останні {window_minutes} хв: "
                        f"{int(details.get('recent_transactions', 0))} "
                        "транзакцій / "
                        f"{int(details.get('recent_tokens', 0))} активних токенів"
                    ),
                    "",
                    (
                        "Останній discovery: "
                        f"{int(details.get('discovered_transactions', 0))} "
                        "транзакцій"
                    ),
                    (
                        "Топ-гаманці, останній цикл: "
                        f"{int(details.get('processed_transactions', 0))} "
                        "транзакцій"
                    ),
                    "Система продовжує моніторинг.",
                )
            )
        )

    async def send_discovery_degraded(
        self,
        failures: int,
        retry_seconds: float,
    ) -> None:
        await self.send_text(
            "\n".join(
                (
                    "🟡 Alpha Engine: RPC перевантажений",
                    f"Невдалих discovery-циклів поспіль: {failures}",
                    f"Наступна спроба приблизно через {retry_seconds:g} с.",
                    "Моніторинг уже відомих топ-гаманців продовжується.",
                )
            )
        )

    async def send_discovery_recovered(self) -> None:
        await self.send_text(
            "🟢 Alpha Engine: RPC/discovery відновлено. Звичайний графік активний."
        )

    async def send_worker_stopped(self) -> None:
        await self.send_text("⏹ Alpha Engine зупинено. Моніторинг не виконується.")

    async def _send(self, recipient: str, text: str) -> bool:
        payload: dict[str, Any] = {
            "chat_id": recipient,
            "text": text[:4096],
            "disable_web_page_preview": True,
        }
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        if self._client is not None:
            response = await self._client.post(url, json=payload)
        else:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        return isinstance(data, dict) and data.get("ok") is True

    @staticmethod
    def format_alpha_signal(event: AlphaSignalGenerated) -> str:
        return "\n".join(
            (
                "🚨 ALPHA SIGNAL — TOP TRADER BUY",
                "",
                f"Trader: {event.wallet}",
                f"Trader score: {event.wallet_score:.2f} ({event.wallet_grade})",
                f"Token: {event.token_address}",
                f"Early token score: {event.token_score:.2f} ({event.token_grade})",
                (
                    "Observed: "
                    f"{event.observed_trade_count} trades / "
                    f"{event.observed_wallet_count} wallets"
                ),
                f"Buy size: {event.sol_amount:.6f} SOL",
                f"Token amount: {event.token_amount:.6f}",
                "",
                f"Token: https://solscan.io/token/{event.token_address}",
                f"Transaction: https://solscan.io/tx/{event.signature}",
                "",
                "Signal for manual review — not financial advice.",
            )
        )
