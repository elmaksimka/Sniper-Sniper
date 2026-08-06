from __future__ import annotations

from typing import Any


class TokenDetector:
    """
    Detects token mints from Solana transactions.
    """

    def detect(
        self,
        transaction: dict[str, Any],
    ) -> list[str]:
        """
        Extract token mint addresses from transaction.

        Uses postTokenBalances from parsed transaction.
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
                "mint"
            )

            if not mint:
                continue

            if mint not in result:
                result.append(
                    mint
                )

        return result