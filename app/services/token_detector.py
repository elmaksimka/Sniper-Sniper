from __future__ import annotations

from typing import Any


class TokenDetector:
    """
    Detects token creation events from Solana transactions.
    """

    def detect(
        self,
        transaction: dict[str, Any],
    ) -> str | None:
        """
        Returns token address if transaction created a token.
        """

        result = transaction.get(
            "result"
        )

        if not result:
            return None

        meta = result.get(
            "meta",
            {},
        )

        post_token_balances = meta.get(
            "postTokenBalances",
            [],
        )

        for balance in post_token_balances:
            mint = balance.get(
                "mint"
            )

            if mint:
                return mint

        return None