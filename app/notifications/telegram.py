from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import httpx

from app.core.events import AlphaSignalGenerated
from app.core.logging import get_logger
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote


class TelegramNotifier:
    """Deliver alpha signals through the Telegram Bot API."""

    def __init__(
        self,
        bot_token: str,
        recipients: Iterable[str],
        http_client: httpx.AsyncClient | None = None,
        market_data_client: DexScreenerClient | None = None,
        retry_delays_seconds: tuple[float, ...] = (1.0, 3.0),
    ) -> None:
        self.bot_token = bot_token.strip()
        self.recipients = tuple(dict.fromkeys(str(item).strip() for item in recipients))
        self._client = http_client
        self._retry_delays_seconds = retry_delays_seconds
        self.market_data = market_data_client or DexScreenerClient()
        self.logger = get_logger("telegram-notifier")

    @property
    def enabled(self) -> bool:
        return bool(self.bot_token and self.recipients)

    async def handle_alpha_signal(self, event: AlphaSignalGenerated) -> None:
        if not self.enabled:
            return
        quote = self._event_quote(event)
        if quote is None:
            try:
                quote = await self.market_data.get_token_quote(event.token_address)
            except Exception:
                self.logger.warning(
                    "dexscreener_quote_failed",
                    token_address=event.token_address,
                )
        await self.send_text(self.format_alpha_signal(event, quote))

    @staticmethod
    def _event_quote(event: AlphaSignalGenerated) -> TokenMarketQuote | None:
        if event.market_price_usd is None:
            return None
        return TokenMarketQuote(
            price_usd=event.market_price_usd,
            pair_url=event.market_pair_url,
            liquidity_usd=event.market_liquidity_usd or 0,
            volume_5m_usd=event.market_volume_5m_usd or 0,
            buys_5m=event.market_buys_5m or 0,
            sells_5m=event.market_sells_5m or 0,
        )

    async def send_text(self, text: str) -> dict[str, bool]:
        if not self.enabled:
            return {}
        results: dict[str, bool] = {}
        for recipient in self.recipients:
            attempts = len(self._retry_delays_seconds) + 1
            for attempt in range(1, attempts + 1):
                try:
                    results[recipient] = await self._send(recipient, text)
                    break
                except Exception as exc:
                    if attempt >= attempts:
                        results[recipient] = False
                        self._log_delivery_failure(recipient, attempt, exc)
                        break
                    self.logger.warning(
                        "telegram_delivery_retry",
                        recipient=recipient,
                        attempt=attempt,
                        attempts=attempts,
                        error_type=type(exc).__name__,
                    )
                    await asyncio.sleep(self._retry_delays_seconds[attempt - 1])
        return results

    def _log_delivery_failure(
        self,
        recipient: str,
        attempt: int,
        exc: Exception,
    ) -> None:
        fields: dict[str, Any] = {
            "recipient": recipient,
            "attempts": attempt,
            "error_type": type(exc).__name__,
        }
        if isinstance(exc, httpx.HTTPStatusError):
            fields["status_code"] = exc.response.status_code
            try:
                body = exc.response.json()
                if isinstance(body, dict):
                    fields["description"] = str(body.get("description", ""))[:300]
            except ValueError:
                pass
        self.logger.error("telegram_delivery_failed", **fields)

    async def send_worker_started(
        self,
        monitor_interval_seconds: float,
        rpc_discovery_interval_seconds: float,
        candidate_refresh_interval_seconds: float,
        candidate_token_limit: int,
        traders_per_token: int,
        history_page_size: int,
        maximum_history_transactions: int,
        external_discovery_enabled: bool,
    ) -> None:
        external_status = (
            (
                "Джерело кандидатів: DexScreener Solana H24\n"
                f"Черга: {candidate_token_limit} монет × топ-{traders_per_token} "
                "трейдерів за realized PnL\n"
                f"Глибокий аудит: по одному гаманцю, сторінками "
                f"{history_page_size}, до {maximum_history_transactions} "
                "транзакцій\n"
                f"Оновлення монет: кожні "
                f"{candidate_refresh_interval_seconds / 3600:g} год"
            )
            if external_discovery_enabled
            else "DexScreener H24 discovery: вимкнено"
        )
        await self.send_text(
            "\n".join(
                (
                    "✅ Alpha Engine запущено",
                    "",
                    external_status,
                    "Порядок: усі трейдери монети → наступна монета",
                    f"Моніторинг A/B: кожні {monitor_interval_seconds:g} с",
                    (
                        "Фоновий RPC discovery: кожні "
                        f"{rpc_discovery_interval_seconds:g} с"
                    ),
                    "Telegram alpha-сигнали активні.",
                )
            )
        )

    async def send_worker_status(self, details: dict[str, Any]) -> dict[str, bool]:
        failures = int(details.get("discovery_failures", 0))
        rpc_state = "норма" if failures == 0 else f"backoff ({failures})"
        window_minutes = int(details.get("status_window_minutes", 30))
        results = await self.send_text(
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
                        f"{int(details.get('total_tokens', 0))} торгових токенів"
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
                    (
                        "Кандидатів оброблено: "
                        f"{int(details.get('candidate_wallets_enriched', 0))}"
                    ),
                    TelegramNotifier._candidate_source_status(details),
                    TelegramNotifier._candidate_status(details),
                    (
                        "Історія кандидата: "
                        f"{int(details.get('candidate_history_transactions_total', 0))} "
                        "транзакцій загалом; остання сторінка "
                        f"{int(details.get('candidate_history_transactions', 0))} "
                        "транзакцій; стан "
                        f"{str(details.get('candidate_audit_state', 'idle'))}"
                    ),
                    (
                        "Нових топ-гаманців: "
                        f"{int(details.get('candidate_wallets_promoted', 0))}"
                    ),
                    "",
                    TelegramNotifier._top_wallets_status(details),
                    "Система продовжує моніторинг.",
                )
            )
        )
        for message in self._candidate_audit_progress_messages(details):
            progress_results = await self.send_text(message)
            for recipient, delivered in progress_results.items():
                results[recipient] = results.get(recipient, True) and delivered
        return results

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
    def format_alpha_signal(
        event: AlphaSignalGenerated,
        quote: TokenMarketQuote | None = None,
    ) -> str:
        estimated_value = (
            event.token_amount * quote.price_usd if quote is not None else None
        )
        dex_url = (
            quote.pair_url
            if quote is not None and quote.pair_url
            else f"https://dexscreener.com/solana/{event.token_address}"
        )
        sol_size = (
            f"{event.sol_amount:.6f} SOL"
            if event.sol_amount > 0
            else "not detected"
        )
        usd_size = (
            TelegramNotifier._format_usd(estimated_value)
            if estimated_value is not None
            else "unavailable (token may not be indexed yet)"
        )
        return "\n".join(
            (
                (
                    "🔥 ALPHA SIGNAL — STRONG CONSENSUS"
                    if event.observed_top_trader_count >= 2
                    else "🚨 ALPHA SIGNAL — TOP TRADER BUY"
                ),
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
                f"Top traders in token: {event.observed_top_trader_count}",
                (
                    "Trader style: holder — "
                    f"{event.trader_long_hold_positions} proven 30m+ holds / "
                    f"max {event.trader_max_distinct_tokens_60s} tokens per 60s / "
                    f"{event.trader_rapid_round_trips} rapid round trips / "
                    f"max {event.trader_max_side_switches_per_token} side switches"
                ),
                f"Buy size: {sol_size}",
                f"Estimated buy value: {usd_size}",
                (
                    "Market: "
                    f"{TelegramNotifier._format_usd_amount(quote.liquidity_usd)} "
                    "liquidity / "
                    f"{TelegramNotifier._format_usd_amount(quote.volume_5m_usd)} "
                    "5m volume"
                ) if quote is not None else "Market: unavailable",
                (
                    f"5m transactions: {quote.buys_5m} buys / "
                    f"{quote.sells_5m} sells"
                ) if quote is not None else "5m transactions: unavailable",
                f"Token amount: {event.token_amount:.6f}",
                "",
                f"Dexscreener: {dex_url}",
                f"Token: https://solscan.io/token/{event.token_address}",
                f"Transaction: https://solscan.io/tx/{event.signature}",
                "",
                "Signal for manual review — not financial advice.",
            )
        )

    @staticmethod
    def _format_usd(value: float) -> str:
        if value >= 1:
            return f"~${value:,.2f} (current DEX price)"
        return f"~${value:.6f} (current DEX price)"

    @staticmethod
    def _format_usd_amount(value: float) -> str:
        return f"${value:,.0f}"

    @staticmethod
    def _candidate_status(details: dict[str, Any]) -> str:
        wallet = str(details.get("candidate_last_wallet", "")).strip()
        if not wallet:
            return "Останній кандидат: немає в цьому циклі"
        before = details.get("candidate_last_score_before")
        after = details.get("candidate_last_score_after")
        try:
            if before is None or after is None:
                raise ValueError
            score_change = f"{float(before):.2f} → {float(after):.2f}"
        except (TypeError, ValueError):
            score_change = "score unavailable"
        return f"Останній кандидат: {wallet} ({score_change})"

    @staticmethod
    def _candidate_source_status(details: dict[str, Any]) -> str:
        hours = int(details.get("candidate_source_window_hours", 24))
        tokens = int(details.get("candidate_source_tokens", 0))
        candidates = int(details.get("candidate_source_candidates", 0))
        return (
            f"Воронка {hours} год: {tokens} winner-токенів / "
            f"{candidates} ранніх трейдерів"
        )

    @staticmethod
    def _candidate_audit_progress_messages(
        details: dict[str, Any],
    ) -> tuple[str, ...]:
        raw_pairs = details.get("candidate_audit_pairs")
        if not isinstance(raw_pairs, list) or not raw_pairs:
            return ()
        pairs = [pair for pair in raw_pairs if isinstance(pair, dict)]
        if not pairs:
            return ()

        completed_pairs = sum(bool(pair.get("complete")) for pair in pairs)
        header = "\n".join(
            (
                "📊 DexScreener — прогрес аудиту",
                (
                    f"Пари: {len(pairs)} розпочато · "
                    f"{completed_pairs} завершено"
                ),
            )
        )
        blocks = [TelegramNotifier._candidate_pair_progress(pair) for pair in pairs]
        messages: list[str] = []
        current = header
        for block in blocks:
            proposed = f"{current}\n\n{block}"
            if len(proposed) <= 3_900:
                current = proposed
                continue
            messages.append(current)
            current = f"📊 Прогрес аудиту — продовження\n\n{block}"
        messages.append(current)
        return tuple(messages)

    @staticmethod
    def _candidate_pair_progress(pair: dict[str, Any]) -> str:
        symbol = str(pair.get("symbol") or "").strip()
        token = str(pair.get("token_address") or "").strip()
        pair_name = symbol or TelegramNotifier._short_address(token)
        started = TelegramNotifier._safe_int(pair.get("started_traders"))
        total = TelegramNotifier._safe_int(pair.get("total_traders"))
        lines = [f"🪙 {pair_name} · {started}/{total} топ-трейдерів"]
        raw_traders = pair.get("traders")
        traders = raw_traders if isinstance(raw_traders, list) else []
        started_traders = [
            trader
            for trader in traders
            if isinstance(trader, dict) and bool(trader.get("started"))
        ]
        if started_traders:
            lines.append("№  Трейдер             Транзакції  Рейтинг")
        for trader in started_traders:
            rank = TelegramNotifier._safe_int(trader.get("rank"))
            wallet = str(trader.get("wallet") or "").strip()
            label = str(trader.get("label") or "").strip()
            identity = label or TelegramNotifier._short_address(wallet)
            if label and wallet:
                identity = f"{label} ({TelegramNotifier._short_address(wallet)})"
            if len(identity) > 24:
                identity = f"{identity[:23]}…"
            transactions = TelegramNotifier._safe_int(
                trader.get("transactions")
            )
            maximum = TelegramNotifier._safe_int(
                trader.get("maximum_transactions")
            )
            state = str(trader.get("state") or "")
            transaction_status = f"{transactions}/{maximum}"
            if state == "complete":
                transaction_status += " ✓"
            score = TelegramNotifier._format_optional_score(trader.get("score"))
            lines.append(
                f"{rank:<2} {identity:<25} {transaction_status:<11} {score}"
            )
        waiting = max(0, total - started)
        if waiting:
            lines.append(f"Очікують аналізу: {waiting}")
        return "\n".join(lines)

    @staticmethod
    def _safe_int(value: object) -> int:
        if not isinstance(value, (int, float, str, bytes, bytearray)):
            return 0
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _format_optional_score(value: object) -> str:
        try:
            return f"{float(value):.2f}"  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return "—"

    @staticmethod
    def _short_address(address: str) -> str:
        if len(address) <= 13:
            return address or "невідомо"
        return f"{address[:6]}…{address[-4:]}"

    @staticmethod
    def _top_wallets_status(details: dict[str, Any]) -> str:
        wallets = details.get("top_wallets", ())
        if not isinstance(wallets, (list, tuple)) or not wallets:
            return "Активні топ-гаманці A/B: немає"

        eligible_wallets = [
            wallet
            for wallet in wallets
            if isinstance(wallet, dict)
            and str(wallet.get("grade", "")).strip() in {"A", "B"}
        ]
        if not eligible_wallets:
            return "Активні топ-гаманці A/B: немає"

        lines = [f"Активні топ-гаманці A/B ({len(eligible_wallets)}):"]
        for wallet in eligible_wallets:
            address = str(wallet.get("address", "")).strip()
            if not address:
                continue
            try:
                raw_score = wallet.get("score")
                if not isinstance(raw_score, (int, float, str)):
                    raise ValueError
                score = f"{float(raw_score):.2f}"
            except (TypeError, ValueError):
                score = "рейтинг недоступний"
            grade = str(wallet.get("grade", "")).strip()
            suffix = f" ({grade})" if grade else ""
            lines.append(f"• {address} — {score}{suffix}")
        return "\n".join(lines)
