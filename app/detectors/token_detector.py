from __future__ import annotations

from collections import defaultdict
from typing import Any


class TokenDetector:
    """Calculate token balance changes for one wallet."""

    def detect(
        self,
        meta: dict[str, Any],
        wallet: str,
    ) -> list[dict[str, float | str]]:
        changes: dict[str, dict[str, float]] = defaultdict(
            lambda: {"before": 0.0, "after": 0.0}
        )

        for state, field in (
            ("before", "preTokenBalances"),
            ("after", "postTokenBalances"),
        ):
            for token in meta.get(field, []):
                if token.get("owner") != wallet:
                    continue

                mint = token.get("mint")
                if not mint:
                    continue

                amount = token.get("uiTokenAmount", {}).get("uiAmount")
                changes[mint][state] += float(amount or 0)

        detected: list[dict[str, float | str]] = []

        for mint, amounts in changes.items():
            difference = amounts["after"] - amounts["before"]
            if difference == 0:
                continue

            detected.append(
                {
                    "mint": mint,
                    "before": amounts["before"],
                    "after": amounts["after"],
                    "change": difference,
                }
            )

        return detected
