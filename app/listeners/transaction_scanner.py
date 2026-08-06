from __future__ import annotations

from app.listeners.helius_client import HeliusClient


class TransactionScanner:
    """
    Scans Solana transactions using Helius RPC.
    """

    def __init__(
        self,
        client: HeliusClient,
    ):
        self.client = client

    async def scan_address(
        self,
        address: str,
        limit: int = 5,
    ) -> list[dict]:
        """
        Get recent transactions for address.
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
                "signature"
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
                "result"
            )

            if transaction:
                transactions.append(
                    {
                        "signature": signature,
                        "transaction": transaction,
                    }
                )

        return transactions