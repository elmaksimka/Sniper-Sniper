from __future__ import annotations

from typing import Any


IGNORED_TOKENS = {
    "So11111111111111111111111111111111111111112",  # Wrapped SOL
    "EPjFWdd5AufqSSqeM2q7E2bJdJvZ3vM9Qy5k4GvYzQ",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD7Y3Y3Y3Y3Y3Y3Y3Y3Y3",  # USDT placeholder
}


class TokenDetector:
    """
    Detects interesting token mints from Solana transactions.
    """

    def detect(
        self,
        transaction: dict[str, Any],
    ) -> list[str]:
        """
        Extract token mint addresses.

        Filters common base tokens.
        """

        result: list[str] = []

        meta = transaction.get(
            "meta",
            {},
        )

        balances = meta.get(
            "postTokenBalances",
            [],
        )

        for balance in balances:
            mint = balance.get(
                "mint",
            )

            if not mint:
                continue

            if mint in IGNORED_TOKENS:
                continue

            if mint not in result:
                result.append(
                    mint
                )

        return result