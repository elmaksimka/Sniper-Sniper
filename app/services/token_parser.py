from __future__ import annotations

from typing import Any


SOL_MINT = "So11111111111111111111111111111111111111112"


class TokenParser:
    """Extract SPL token mints that participated in a wallet transaction."""

    def extract_tokens(
        self,
        tx: dict[str, Any],
        wallet: str | None = None,
    ) -> list[str]:
        tokens: set[str] = set()

        for transfer in tx.get("tokenTransfers", []):
            if wallet and wallet not in {
                transfer.get("fromUserAccount"),
                transfer.get("toUserAccount"),
            }:
                continue

            self._add_mint(tokens, transfer.get("mint"))

        meta = tx.get("meta", {})
        for field in ("preTokenBalances", "postTokenBalances"):
            for balance in meta.get(field, []):
                if wallet and balance.get("owner") != wallet:
                    continue

                self._add_mint(tokens, balance.get("mint"))

        return sorted(tokens)

    @staticmethod
    def _add_mint(tokens: set[str], mint: Any) -> None:
        if isinstance(mint, str) and mint and mint != SOL_MINT:
            tokens.add(mint)


def extract_tokens(
    tx: dict[str, Any],
    wallet: str | None = None,
) -> list[str]:
    return TokenParser().extract_tokens(tx, wallet)
