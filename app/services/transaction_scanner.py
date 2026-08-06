from __future__ import annotations

from app.listeners.helius_client import HeliusClient


class TransactionScanner:
    """
    Scans Solana addresses for recent transactions.
    """

    def __init__(
        self,
        client: HeliusClient,
    ):
        self.client = client

    async def scan(
        self,
        address: str,
        limit: int = 10,
    ) -> list[str]:
        """
        Returns recent transaction signatures.
        """

        response = await self.client.get_signatures(
            address=address,
            limit=limit,
        )

        if "error" in response:
            print(
                "Transaction scan error:",
                response["error"],
            )
            return []

        result = response.get(
            "result",
            [],
        )

        return [
            item["signature"]
            for item in result
            if "signature" in item
        ]