from __future__ import annotations

import asyncio
from collections.abc import Iterable
from typing import Any

import httpx

from app.core.events import AlphaSignalGenerated
from app.core.logging import get_logger
from app.infrastructure.models import PaperCopyOrder, PaperCopyPortfolio
from app.services.dexscreener_client import DexScreenerClient, TokenMarketQuote
from app.services.paper_copy_report_service import PaperCopyReport


class TelegramNotifier:
    """Deliver alpha signals through the Telegram Bot API."""

    def __init__(
        self,
        bot_token: str,
        recipients: Iterable[str],
        http_client: httpx.AsyncClient | None = None,
        market_data_client: DexScreenerClient | None = None,
        retry_delays_seconds: tuple[float, ...] = (1.0, 3.0),
        worker_summary_enabled: bool = True,
    ) -> None:
        self.bot_token = bot_token.strip()
        self.recipients = tuple(dict.fromkeys(str(item).strip() for item in recipients))
        self._client = http_client
        self._retry_delays_seconds = retry_delays_seconds
        self.worker_summary_enabled = worker_summary_enabled
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

    async def send_paper_copy_started(
        self,
        portfolio: PaperCopyPortfolio,
    ) -> dict[str, bool]:
        return await self.send_text(
            "\n".join(
                (
                    "🧪 PAPER COPY запущено",
                    "",
                    f"Трейдер: {portfolio.source_wallet}",
                    f"Стартовий баланс: ${portfolio.initial_balance_usd:,.2f}",
                    f"На одну позицію: ${portfolio.allocation_usd:,.2f}",
                    f"Максимум позицій: {portfolio.max_open_positions}",
                    (
                        "Затримка: моніторинг + "
                        f"{portfolio.reaction_delay_seconds:g} с реакції"
                    ),
                    f"Модель slippage: {portfolio.slippage_bps / 100:.2f}% на сторону",
                    (
                        "Мінімальна ліквідність: "
                        f"${portfolio.minimum_liquidity_usd:,.0f}"
                    ),
                    "Режим: симуляція, реальні кошти не використовуються.",
                )
            )
        )

    async def send_paper_copy_order(
        self,
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
    ) -> dict[str, bool]:
        return await self.send_text(self.format_paper_copy_order(order, portfolio))

    async def send_paper_copy_summary(
        self,
        orders: list[PaperCopyOrder],
        portfolio: PaperCopyPortfolio,
        open_positions: int,
    ) -> dict[str, bool]:
        return await self.send_text(
            self.format_paper_copy_summary(orders, portfolio, open_positions)
        )

    @staticmethod
    def format_paper_copy_summary(
        orders: list[PaperCopyOrder],
        portfolio: PaperCopyPortfolio,
        open_positions: int,
    ) -> str:
        filled = [order for order in orders if order.status == "filled"]
        buys = [order for order in filled if order.side == "buy"]
        sells = [order for order in filled if order.side == "sell"]
        skipped = sum(order.status == "skipped" for order in orders)
        buy_total = sum(float(order.value_usd or 0) for order in buys)
        sell_total = sum(float(order.value_usd or 0) for order in sells)
        realized_pnl = sum(float(order.realized_pnl_usd or 0) for order in sells)
        token_count = len({order.token_address for order in filled})
        pnl_sign = "+" if realized_pnl >= 0 else ""
        lines = [
            "🧪 PAPER COPY — звіт за 30 хв",
            "",
            "Пул: 7 трейдерів A/A",
            f"Входи: {len(buys)} на ${buy_total:,.2f}",
            f"Виходи: {len(sells)} на ${sell_total:,.2f}",
            f"Монет у звіті: {token_count}",
            f"Реалізований PnL: {pnl_sign}${realized_pnl:,.2f}",
            f"Пропущено сигналів: {skipped}",
            f"Відкритих позицій: {open_positions}",
            f"Готівка: ${portfolio.cash_balance_usd:,.2f}",
        ]
        source_wallets = sorted({order.source_wallet for order in orders})
        if source_wallets:
            lines.extend(("", "За трейдерами:"))
        for source_wallet in source_wallets:
            source_orders = [
                order for order in orders if order.source_wallet == source_wallet
            ]
            source_buys = [
                order
                for order in source_orders
                if order.status == "filled" and order.side == "buy"
            ]
            source_sells = [
                order
                for order in source_orders
                if order.status == "filled" and order.side == "sell"
            ]
            source_pnl = sum(
                float(order.realized_pnl_usd or 0) for order in source_sells
            )
            source_skipped = sum(order.status == "skipped" for order in source_orders)
            lines.append(
                f"• {TelegramNotifier._short_address(source_wallet)}: "
                f"{len(source_buys)} входів / {len(source_sells)} виходів · "
                f"PnL ${source_pnl:+,.2f} · пропущено {source_skipped}"
            )
        visible = filled[-12:]
        if visible:
            lines.extend(("", "Операції:"))
        for order in visible:
            action = "Вхід" if order.side == "buy" else "Вихід"
            short_token = TelegramNotifier._short_address(order.token_address)
            value = float(order.value_usd or 0)
            source = TelegramNotifier._short_address(order.source_wallet)
            detail = (
                f"{'🟢' if order.side == 'buy' else '🔴'} {action} "
                f"${value:,.2f} — {short_token} · {source}"
            )
            if order.side == "sell":
                detail += f" (PnL ${float(order.realized_pnl_usd or 0):+,.2f})"
            lines.extend(
                (
                    detail,
                    f"Dex: https://dexscreener.com/solana/{order.token_address}",
                    f"Tx: https://solscan.io/tx/{order.source_signature}",
                )
            )
        hidden = len(filled) - len(visible)
        if hidden > 0:
            lines.append(f"Ще операцій без деталізації: {hidden}")
        return "\n".join(lines)

    async def send_paper_copy_report(
        self,
        report: PaperCopyReport,
    ) -> dict[str, bool]:
        pnl_sign = "+" if report.total_pnl_usd >= 0 else ""
        realized_sign = "+" if report.realized_pnl_usd >= 0 else ""
        open_sign = "+" if report.open_pnl_usd >= 0 else ""
        lines = [
            "🌅 PAPER COPY — ранковий звіт",
            "",
            f"Трейдер: {self._short_address(report.source_wallet)}",
            f"Старт: ${report.initial_balance_usd:,.2f}",
            f"Поточний баланс: ${report.total_equity_usd:,.2f}",
            f"Загальний PnL: {pnl_sign}${report.total_pnl_usd:,.2f}",
            f"Реалізовано за продажами: {realized_sign}${report.realized_pnl_usd:,.2f}",
            f"Відкриті позиції: {open_sign}${report.open_pnl_usd:,.2f}",
            "",
            f"Готівка: ${report.cash_balance_usd:,.2f}",
            f"Купівлі/продажі: {report.filled_buys}/{report.filled_sells}",
            f"Відкритих позицій: {report.open_positions}",
            f"Пропущених сигналів: {report.skipped_orders}",
        ]
        if report.stale_quotes:
            lines.append(
                f"⚠️ Без live-ціни: {report.stale_quotes} позицій; використано останню відому."
            )
        lines.append("Розрахунок включає 1% sell-slippage для відкритих позицій.")
        return await self.send_text("\n".join(lines))

    @staticmethod
    def format_paper_copy_order(
        order: PaperCopyOrder,
        portfolio: PaperCopyPortfolio,
    ) -> str:
        side = "КУПІВЛЯ" if order.side == "buy" else "ПРОДАЖ"
        if order.status == "skipped":
            side = f"{side} ПРОПУЩЕНА"
        icon = "🟢" if order.side == "buy" else "🔴"
        if order.status == "skipped":
            icon = "⚪"
        total_delay = 0.0
        if order.executed_at is not None:
            source_at = order.source_transaction_at
            if source_at.tzinfo is None:
                source_at = source_at.replace(tzinfo=order.executed_at.tzinfo)
            total_delay = max(
                0.0,
                (order.executed_at - source_at).total_seconds(),
            )
        lines = [
            f"{icon} PAPER COPY — {side}",
            "",
            f"Трейдер: {TelegramNotifier._short_address(order.source_wallet)}",
            f"Токен: {order.token_address}",
            f"Загальна затримка: {total_delay:.0f} с",
        ]
        if order.status == "filled":
            lines.extend(
                (
                    f"Ціна виконання: ${float(order.execution_price_usd or 0):.10g}",
                    f"Сума: ${float(order.value_usd or 0):,.2f}",
                    f"Кількість: {float(order.quantity or 0):,.6f}",
                )
            )
            if order.side == "sell":
                pnl = float(order.realized_pnl_usd or 0)
                lines.append(f"Результат позиції: ${pnl:+,.2f}")
            liquidity = float(order.liquidity_usd or 0)
            lines.append(
                f"Ліквідність: ${liquidity:,.0f}"
                if liquidity > 0
                else "Ліквідність: н/д (Pump.fun bonding curve)"
            )
        else:
            lines.append(f"Причина: {order.reason or 'невідомо'}")
        lines.extend(
            (
                "",
                f"Готівка: ${float(order.cash_balance_after_usd or 0):,.2f}",
                f"Paper-баланс: ${float(order.equity_after_usd or 0):,.2f}",
                (
                    "Відкриті позиції: "
                    f"{int(order.open_positions_after or 0)}/{portfolio.max_open_positions}"
                ),
                f"Dexscreener: https://dexscreener.com/solana/{order.token_address}",
                f"Транзакція трейдера: https://solscan.io/tx/{order.source_signature}",
            )
        )
        return "\n".join(lines)

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
        results = (
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
            if self.worker_summary_enabled
            else {}
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
            f"{event.sol_amount:.6f} SOL" if event.sol_amount > 0 else "not detected"
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
                (
                    "Trader entry price: "
                    f"{TelegramNotifier._format_token_usd(event.trader_entry_price_usd)} / "
                    f"{event.trader_entry_price_sol:.12g} SOL per token"
                    if event.trader_entry_price_sol is not None
                    and event.trader_entry_price_usd is not None
                    else "Trader entry price: unavailable"
                ),
                (
                    f"Trader buy value: {sol_size} / "
                    f"~${event.trader_buy_value_usd:,.2f}"
                    if event.trader_buy_value_usd is not None
                    else f"Trader buy value: {sol_size} / USD unavailable"
                ),
                (
                    f"Current price: {TelegramNotifier._format_token_usd(quote.price_usd)} "
                    f"({event.market_price_vs_entry:.2f}x vs trader entry)"
                    if quote is not None and event.market_price_vs_entry is not None
                    else "Current price: unavailable"
                ),
                f"Current position value: {usd_size}",
                (
                    "Market: "
                    f"{TelegramNotifier._format_usd_amount(quote.liquidity_usd)} "
                    "liquidity / "
                    f"{TelegramNotifier._format_usd_amount(quote.volume_5m_usd)} "
                    "5m volume"
                )
                if quote is not None
                else "Market: unavailable",
                (f"5m transactions: {quote.buys_5m} buys / {quote.sells_5m} sells")
                if quote is not None
                else "5m transactions: unavailable",
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
    def _format_token_usd(value: float | None) -> str:
        if value is None:
            return "unavailable"
        return f"${value:,.8f}" if value < 1 else f"${value:,.4f}"

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

        progress: list[str] = []
        completed_names: list[str] = []
        unique_traders: dict[str, tuple[float, float]] = {}
        for pair in pairs:
            symbol = str(pair.get("symbol") or "").strip()
            token = str(pair.get("token_address") or "").strip()
            name = symbol or TelegramNotifier._short_address(token)
            started = TelegramNotifier._safe_int(pair.get("started_traders"))
            total = TelegramNotifier._safe_int(pair.get("total_traders"))
            progress.append(f"{name} {started}/{total}")
            if bool(pair.get("complete")):
                completed_names.append(name)

            raw_traders = pair.get("traders")
            traders = raw_traders if isinstance(raw_traders, list) else []
            for trader in traders:
                if not isinstance(trader, dict) or not bool(trader.get("started")):
                    continue
                wallet = str(trader.get("wallet") or "").strip()
                main_score = TelegramNotifier._optional_score(trader.get("score"))
                copy_score = TelegramNotifier._optional_score(trader.get("copy_score"))
                if wallet and main_score is not None and copy_score is not None:
                    unique_traders[wallet] = (main_score, copy_score)

        aa_count = sum(
            main >= 80 and copy >= 75 for main, copy in unique_traders.values()
        )
        ba_count = sum(
            65 <= main < 80 and copy >= 75 for main, copy in unique_traders.values()
        )
        ab_count = sum(
            main >= 80 and 55 <= copy < 75 for main, copy in unique_traders.values()
        )
        bb_count = sum(
            65 <= main < 80 and 55 <= copy < 75
            for main, copy in unique_traders.values()
        )
        completed = ", ".join(completed_names) if completed_names else "немає"
        message = "\n".join(
            (
                "📊 DexScreener — прогрес аудиту",
                (
                    f"Пари: {len(pairs)} розпочато "
                    f"({', '.join(progress)}) · "
                    f"{len(completed_names)} завершено ({completed})"
                ),
                "",
                f"A/A: {aa_count}",
                f"B/A: {ba_count}",
                f"A/B: {ab_count}",
                f"B/B: {bb_count}",
            )
        )
        return (message,)

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
        graded_traders: list[tuple[dict[str, Any], float]] = []
        for trader in traders:
            if not isinstance(trader, dict) or not bool(trader.get("started")):
                continue
            score = TelegramNotifier._optional_score(trader.get("score"))
            if score is not None:
                graded_traders.append((trader, score))
        main_a_count = sum(score >= 80 for _, score in graded_traders)
        main_b_count = sum(65 <= score < 80 for _, score in graded_traders)
        main_c_count = sum(50 <= score < 65 for _, score in graded_traders)
        copy_a_traders = [
            (trader, score)
            for trader, score in graded_traders
            if (TelegramNotifier._optional_score(trader.get("copy_score")) or 0) >= 75
        ]
        aa_traders = [
            (trader, score) for trader, score in copy_a_traders if score >= 80
        ]
        ba_traders = [
            (trader, score) for trader, score in copy_a_traders if 65 <= score < 80
        ]
        if copy_a_traders:
            lines.append("№  Клас  Трейдер             Транзакції  Рейтинг")
        for display_rank, (trader, score) in enumerate(copy_a_traders, start=1):
            wallet = str(trader.get("wallet") or "").strip()
            label = str(trader.get("label") or "").strip()
            identity = label or TelegramNotifier._short_address(wallet)
            if label and wallet:
                identity = f"{label} ({TelegramNotifier._short_address(wallet)})"
            if len(identity) > 24:
                identity = f"{identity[:23]}…"
            transactions = TelegramNotifier._safe_int(trader.get("transactions"))
            maximum = TelegramNotifier._safe_int(trader.get("maximum_transactions"))
            state = str(trader.get("state") or "")
            transaction_status = f"{transactions}/{maximum}"
            if state == "complete":
                transaction_status += " ✓"
            copy_score = TelegramNotifier._optional_score(trader.get("copy_score"))
            copy_mode = {
                "automatic": "авто",
                "manual": "ручний",
                "unsuitable": "не копіювати",
            }.get(str(trader.get("copy_mode") or ""), "")
            rating = f"{score:.2f}"
            if copy_score is not None:
                copy_suffix = f"copy {copy_score:.0f}"
                if copy_mode:
                    copy_suffix += f" · {copy_mode}"
                rating += f" ({copy_suffix})"
            main_grade = "A" if score >= 80 else "B" if score >= 65 else "C"
            lines.append(
                f"{display_rank:<2} {main_grade}/A   {identity:<25} "
                f"{transaction_status:<11} {rating}"
            )
        lines.extend(
            (
                f"A + Copy A: {len(aa_traders)}",
                f"B + Copy A: {len(ba_traders)}",
                f"Copy A: {len(copy_a_traders)}",
                f"Основна A: {main_a_count}",
                f"Основна B: {main_b_count}",
                f"Основна C: {main_c_count}",
            )
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
        score = TelegramNotifier._optional_score(value)
        return f"{score:.2f}" if score is not None else "—"

    @staticmethod
    def _optional_score(value: object) -> float | None:
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

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
