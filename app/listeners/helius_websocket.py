from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
import json
from typing import Any

from websockets.asyncio.client import connect

from app.core.logging import get_logger


TransactionHandler = Callable[[dict[str, Any], tuple[str, ...]], Awaitable[None]]
TransactionFetcher = Callable[[str], Awaitable[dict[str, Any] | None]]


class HeliusTransactionSubscriber:
    """Stream full transactions involving known wallets over one connection."""

    def __init__(
        self,
        websocket_url: str,
        addresses: tuple[str, ...],
        handler: TransactionHandler,
        transaction_fetcher: TransactionFetcher | None = None,
        *,
        reconnect_initial_seconds: float = 1,
        reconnect_max_seconds: float = 30,
        connector: Any = connect,
    ) -> None:
        self.websocket_url = websocket_url
        self.addresses = tuple(dict.fromkeys(addresses))
        self.address_set = set(self.addresses)
        self.handler = handler
        self.transaction_fetcher = transaction_fetcher
        self.reconnect_initial_seconds = reconnect_initial_seconds
        self.reconnect_max_seconds = reconnect_max_seconds
        self.connector = connector
        self.logger = get_logger("helius-transaction-websocket")
        self._seen: set[str] = set()
        self._seen_order: deque[str] = deque()

    async def run(self, stop_event: asyncio.Event) -> None:
        if not self.websocket_url or not self.addresses:
            self.logger.warning(
                "helius_websocket_disabled",
                url_configured=bool(self.websocket_url),
                address_count=len(self.addresses),
            )
            return

        delay = self.reconnect_initial_seconds
        use_log_subscriptions = False
        while not stop_event.is_set():
            try:
                async with self.connector(
                    self.websocket_url,
                    ping_interval=30,
                    ping_timeout=20,
                    close_timeout=5,
                    max_size=16 * 1024 * 1024,
                ) as socket:
                    if not use_log_subscriptions:
                        use_log_subscriptions = not await self._subscribe_transactions(
                            socket
                        )
                    subscription_wallets: dict[int, str] = {}
                    if use_log_subscriptions:
                        if self.transaction_fetcher is None:
                            raise RuntimeError(
                                "A transaction fetcher is required for logsSubscribe"
                            )
                        subscription_wallets = await self._subscribe_logs(socket)
                    delay = self.reconnect_initial_seconds

                    while not stop_event.is_set():
                        message = self._decode(await socket.recv())
                        parsed = (
                            await self.parse_log_notification(
                                message,
                                subscription_wallets,
                            )
                            if use_log_subscriptions
                            else self.parse_notification(message)
                        )
                        if parsed is None:
                            continue
                        transaction, matched, signature = parsed
                        if signature in self._seen:
                            continue
                        self._remember(signature)
                        await self.handler(transaction, matched)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.logger.warning(
                    "helius_websocket_reconnecting",
                    error=str(error),
                    retry_seconds=delay,
                )
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(delay * 2, self.reconnect_max_seconds)

    async def _subscribe_transactions(self, socket: Any) -> bool:
        await socket.send(json.dumps(self.subscription_request()))
        acknowledgement = self._decode(await asyncio.wait_for(socket.recv(), 30))
        error = acknowledgement.get("error")
        if error is not None:
            if "not available" in str(error).lower():
                self.logger.info(
                    "helius_transaction_subscription_unavailable_using_logs",
                    address_count=len(self.addresses),
                )
                return False
            raise RuntimeError(f"Helius subscription rejected: {error}")
        if not isinstance(acknowledgement.get("result"), int):
            raise RuntimeError("Helius returned an invalid subscription id")
        self.logger.info(
            "helius_websocket_subscribed",
            mode="transactions",
            address_count=len(self.addresses),
        )
        return True

    async def _subscribe_logs(self, socket: Any) -> dict[int, str]:
        requested: dict[str, str] = {}
        for index, address in enumerate(self.addresses):
            request_id = f"paper-copy-log-{index}"
            requested[request_id] = address
            await socket.send(json.dumps(self.log_subscription_request(request_id, address)))

        subscriptions: dict[int, str] = {}
        while len(subscriptions) < len(requested):
            acknowledgement = self._decode(await asyncio.wait_for(socket.recv(), 30))
            response_id = acknowledgement.get("id")
            if not isinstance(response_id, str) or response_id not in requested:
                continue
            error = acknowledgement.get("error")
            if error is not None:
                raise RuntimeError(f"Helius logs subscription rejected: {error}")
            subscription_id = acknowledgement.get("result")
            if not isinstance(subscription_id, int):
                raise RuntimeError("Helius returned an invalid logs subscription id")
            subscriptions[subscription_id] = requested[response_id]
        self.logger.info(
            "helius_websocket_subscribed",
            mode="logs",
            address_count=len(subscriptions),
        )
        return subscriptions

    def subscription_request(self) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": "paper-copy-stream",
            "method": "transactionSubscribe",
            "params": [
                {
                    "vote": False,
                    "failed": False,
                    "accountInclude": list(self.addresses),
                },
                {
                    "commitment": "confirmed",
                    "encoding": "jsonParsed",
                    "transactionDetails": "full",
                    "showRewards": False,
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        }

    @staticmethod
    def log_subscription_request(request_id: str, address: str) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [address]},
                {"commitment": "confirmed"},
            ],
        }

    async def parse_log_notification(
        self,
        message: dict[str, Any],
        subscription_wallets: dict[int, str],
    ) -> tuple[dict[str, Any], tuple[str, ...], str] | None:
        if message.get("method") != "logsNotification":
            return None
        params = message.get("params")
        if not isinstance(params, dict):
            return None
        subscription_id = params.get("subscription")
        if not isinstance(subscription_id, int):
            return None
        wallet = subscription_wallets.get(subscription_id)
        result = params.get("result")
        value = result.get("value") if isinstance(result, dict) else None
        signature = value.get("signature") if isinstance(value, dict) else None
        if not wallet or not isinstance(signature, str) or not signature:
            return None
        if self.transaction_fetcher is None:
            return None
        transaction = await self.transaction_fetcher(signature)
        if transaction is None:
            self.logger.warning(
                "helius_websocket_transaction_unavailable",
                signature=signature,
            )
            return None
        transaction["signature"] = signature
        matched = tuple(sorted(self.address_set.intersection(self._account_keys(transaction))))
        return transaction, matched or (wallet,), signature

    def parse_notification(
        self,
        message: dict[str, Any],
    ) -> tuple[dict[str, Any], tuple[str, ...], str] | None:
        if message.get("method") != "transactionNotification":
            return None
        params = message.get("params")
        result = params.get("result") if isinstance(params, dict) else None
        if not isinstance(result, dict):
            return None

        payload = result.get("transaction")
        if not isinstance(payload, dict):
            return None
        if isinstance(payload.get("transaction"), dict):
            transaction = dict(payload)
        else:
            transaction = {
                "transaction": payload,
                "meta": result.get("meta"),
            }
        if transaction.get("meta") is None and result.get("meta") is not None:
            transaction["meta"] = result["meta"]
        if transaction.get("blockTime") is None and result.get("blockTime") is not None:
            transaction["blockTime"] = result["blockTime"]
        if transaction.get("slot") is None and result.get("slot") is not None:
            transaction["slot"] = result["slot"]

        signature = self._signature(result, transaction)
        if signature is None:
            return None
        transaction["signature"] = signature
        matched = tuple(sorted(self.address_set.intersection(self._account_keys(transaction))))
        if not matched:
            return None
        return transaction, matched, signature

    @staticmethod
    def _decode(raw: str | bytes) -> dict[str, Any]:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise RuntimeError("Helius WebSocket returned a non-object message")
        return payload

    @staticmethod
    def _signature(
        result: dict[str, Any],
        transaction: dict[str, Any],
    ) -> str | None:
        direct = result.get("signature")
        if isinstance(direct, str) and direct:
            return direct
        signatures = transaction.get("transaction", {}).get("signatures", [])
        if signatures and isinstance(signatures[0], str):
            return signatures[0]
        return None

    @staticmethod
    def _account_keys(transaction: dict[str, Any]) -> set[str]:
        message = transaction.get("transaction", {}).get("message", {})
        keys: set[str] = set()
        for item in message.get("accountKeys", []):
            if isinstance(item, str):
                keys.add(item)
            elif isinstance(item, dict) and isinstance(item.get("pubkey"), str):
                keys.add(item["pubkey"])
        loaded = transaction.get("meta", {}).get("loadedAddresses", {}) or {}
        for kind in ("writable", "readonly"):
            for item in loaded.get(kind, []):
                if isinstance(item, str):
                    keys.add(item)
        return keys

    def _remember(self, signature: str) -> None:
        self._seen.add(signature)
        self._seen_order.append(signature)
        while len(self._seen_order) > 10_000:
            self._seen.discard(self._seen_order.popleft())
