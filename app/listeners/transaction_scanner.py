from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.analyzer import TokenAnalyzer
from app.listeners.helius_client import HeliusClient
from app.services.token_parser import TokenParser


@dataclass(frozen=True, slots=True)
class TransactionScanPage:
    transactions: list[dict[str, Any]]
    pagination_token: str | None


class TransactionScanner:
    """Fetch and normalize paginated Helius wallet transactions."""

    def __init__(
        self,
        helius: HeliusClient,
        parser: TokenParser,
        analyzer: TokenAnalyzer,
    ) -> None:
        self.helius = helius
        self.parser = parser
        self.analyzer = analyzer

    async def scan_page(
        self,
        wallet: str,
        limit: int = 100,
        pagination_token: str | None = None,
    ) -> TransactionScanPage:
        page = await self.helius.get_transactions_for_address(
            wallet=wallet,
            limit=limit,
            pagination_token=pagination_token,
            sort_order="desc",
        )
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()

        for transaction in page.transactions:
            signature = self._signature(transaction)
            if signature is None or signature in seen:
                continue
            seen.add(signature)
            normalized.append(self._normalize(transaction, wallet, signature))

        return TransactionScanPage(normalized, page.pagination_token)

    async def scan_address(
        self,
        wallet: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []

        transactions: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        pagination_token: str | None = None
        seen_tokens: set[str] = set()

        while len(transactions) < limit:
            remaining = limit - len(transactions)
            page = await self.scan_page(
                wallet,
                limit=min(remaining, 100),
                pagination_token=pagination_token,
            )

            for transaction in page.transactions:
                signature = transaction["signature"]
                if signature in seen_signatures:
                    continue
                seen_signatures.add(signature)
                transactions.append(transaction)
                if len(transactions) == limit:
                    break

            next_token = page.pagination_token
            if not next_token or next_token in seen_tokens:
                break
            seen_tokens.add(next_token)
            pagination_token = next_token

        return transactions

    def _normalize(
        self,
        transaction: dict[str, Any],
        wallet: str,
        signature: str,
    ) -> dict[str, Any]:
        return {
            "signature": signature,
            "timestamp": transaction.get("blockTime"),
            "tokens": self.parser.extract_tokens(transaction, wallet),
            "trades": self.analyzer.analyze_transaction(transaction, wallet),
        }

    @staticmethod
    def _signature(transaction: dict[str, Any]) -> str | None:
        direct = transaction.get("signature")
        if isinstance(direct, str) and direct:
            return direct

        signatures = transaction.get("transaction", {}).get("signatures", [])
        if signatures and isinstance(signatures[0], str):
            return signatures[0]
        return None
