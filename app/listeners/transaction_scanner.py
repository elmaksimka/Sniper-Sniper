from __future__ import annotations

from typing import Any

from app.analyzer import TokenAnalyzer
from app.listeners.helius_client import HeliusClient
from app.services.token_parser import TokenParser


class TransactionScanner:
    """Fetch and normalize recent Helius transactions for a wallet."""

    def __init__(
        self,
        helius: HeliusClient,
        parser: TokenParser,
        analyzer: TokenAnalyzer,
    ) -> None:
        self.helius = helius
        self.parser = parser
        self.analyzer = analyzer

    async def scan_address(
        self,
        wallet: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        transactions = await self.helius.get_transactions(wallet, limit)
        result: list[dict[str, Any]] = []

        for transaction in transactions:
            result.append(
                {
                    "signature": transaction.get("signature"),
                    "timestamp": transaction.get(
                        "timestamp",
                        transaction.get("blockTime"),
                    ),
                    "tokens": self.parser.extract_tokens(transaction, wallet),
                    "trades": self.analyzer.analyze_transaction(
                        transaction,
                        wallet,
                    ),
                }
            )

        return result
