from __future__ import annotations

from app.detectors.token_detector import TokenDetector
from app.listeners.helius_client import HeliusClient


class TransactionScanner:
    """
    Scans Solana transactions using Helius RPC.
    """

    def __init__(
        self,
        client: HeliusClient,
        detector: TokenDetector,
    ):
        self.client = client
        self.detector = detector

    async def scan_address(
        self,
        address: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Scan address transactions and detect tokens.
        """

        signatures_response = await self.client.get_signatures(
            address,
            limit,
        )

        if "error" in signatures_response:
            print(
                "Signature scan error:",
                signatures_response["error"],
            )
            return []

        signatures = signatures_response.get(
            "result",
            [],
        )

        transactions = []

        for item in signatures:
            signature = item.get(
                "signature",
            )

            if not signature:
                continue

            transaction_response = await self.client.get_transaction(
                signature,
            )

            if "error" in transaction_response:
                print(
                    "Transaction error:",
                    transaction_response["error"],
                )
                continue

            transaction = transaction_response.get(
                "result",
            )

            if not transaction:
                continue

            detected_tokens = self.detector.detect(
                transaction,
            )

            transactions.append(
                {
                    "signature": signature,
                    "tokens": detected_tokens,
                    "transaction": transaction,
                }
            )

        return transactions