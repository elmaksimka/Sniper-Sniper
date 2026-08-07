from __future__ import annotations

from typing import Any

from app.core.assets import NON_TARGET_MINTS, WRAPPED_SOL_MINT

SOL_MINT = WRAPPED_SOL_MINT


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
        if isinstance(mint, str) and mint and mint not in NON_TARGET_MINTS:
            tokens.add(mint)


def extract_tokens(
    tx: dict[str, Any],
    wallet: str | None = None,
) -> list[str]:
    return TokenParser().extract_tokens(tx, wallet)
