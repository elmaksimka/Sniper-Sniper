from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.analyzer import TokenAnalyzer
from app.listeners.helius_client import HeliusClient
from app.services.token_parser import TokenParser
from app.services.funding_parser import FundingParser


@dataclass(frozen=True, slots=True)
class TransactionScanPage:
    transactions: list[dict[str, Any]]
    pagination_token: str | None


@dataclass(frozen=True, slots=True)
class TransactionCatchUp:
    transactions: list[dict[str, Any]]
    newest_signature: str | None
    complete: bool


class TransactionScanner:
    """Fetch and normalize paginated Helius wallet transactions."""

    def __init__(
        self,
        helius: HeliusClient,
        parser: TokenParser,
        analyzer: TokenAnalyzer,
        funding_parser: FundingParser | None = None,
    ) -> None:
        self.helius = helius
        self.parser = parser
        self.analyzer = analyzer
        self.funding_parser = funding_parser or FundingParser()

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

    async def scan_since(
        self,
        wallet: str,
        checkpoint_signature: str | None,
        page_size: int = 100,
        max_pages: int = 10,
    ) -> TransactionCatchUp:
        collected: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        seen_tokens: set[str] = set()
        pagination_token: str | None = None
        newest_signature: str | None = None

        for _ in range(max_pages):
            page = await self.scan_page(
                wallet,
                limit=page_size,
                pagination_token=pagination_token,
            )

            for transaction in page.transactions:
                signature = transaction["signature"]
                if newest_signature is None:
                    newest_signature = signature
                if signature == checkpoint_signature:
                    return TransactionCatchUp(
                        list(reversed(collected)),
                        newest_signature,
                        True,
                    )
                if signature not in seen_signatures:
                    seen_signatures.add(signature)
                    collected.append(transaction)

            # The first scan intentionally establishes a bounded high-water mark.
            if checkpoint_signature is None:
                return TransactionCatchUp(
                    list(reversed(collected)),
                    newest_signature,
                    True,
                )

            next_token = page.pagination_token
            if not next_token:
                return TransactionCatchUp(
                    list(reversed(collected)),
                    newest_signature,
                    True,
                )
            if next_token in seen_tokens:
                return TransactionCatchUp([], newest_signature, False)
            seen_tokens.add(next_token)
            pagination_token = next_token

        return TransactionCatchUp([], newest_signature, False)

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
            "native_transfers": self.funding_parser.extract_transfers(transaction),
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
