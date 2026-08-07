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
                f"Token score: {event.token_score:.2f} ({event.token_grade})",
                f"Buy size: {event.sol_amount:.6f} SOL",
                f"Token amount: {event.token_amount:.6f}",
                "",
                f"Token: https://solscan.io/token/{event.token_address}",
                f"Transaction: https://solscan.io/tx/{event.signature}",
                "",
                "Signal for manual review — not financial advice.",
            )
        )
