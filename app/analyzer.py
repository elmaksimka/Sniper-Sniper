from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any


LAMPORTS_PER_SOL = 1_000_000_000


@dataclass(frozen=True, slots=True)
class TokenTrade:
    mint: str
    wallet: str
    sol_change: float
    token_change: float

    @property
    def side(self) -> str:
        return "buy" if self.token_change > 0 else "sell"


class TokenAnalyzer:
    """Normalize wallet balance changes into token trades."""

    def analyze_transaction(
        self,
        tx: dict[str, Any],
        wallet: str,
    ) -> list[TokenTrade]:
        transaction = self._unwrap_rpc_result(tx)
        enhanced_changes = self._enhanced_token_changes(transaction, wallet)

        if enhanced_changes:
            token_changes = enhanced_changes
            sol_change = self._enhanced_sol_change(transaction, wallet)
        else:
            meta = self._meta(transaction)
            token_changes = self._raw_token_changes(meta, wallet)
            sol_change = self._raw_sol_change(transaction, meta, wallet)

        return [
            TokenTrade(
                mint=mint,
                wallet=wallet,
                sol_change=sol_change,
                token_change=change,
            )
            for mint, change in sorted(token_changes.items())
            if change != 0
        ]

    @staticmethod
    def _unwrap_rpc_result(tx: dict[str, Any]) -> dict[str, Any]:
        result = tx.get("result")
        return result if isinstance(result, dict) else tx

    @staticmethod
    def _meta(tx: dict[str, Any]) -> dict[str, Any]:
        meta = tx.get("meta")
        if isinstance(meta, dict):
            return meta

        transaction_meta = tx.get("transaction", {}).get("meta")
        return transaction_meta if isinstance(transaction_meta, dict) else {}

    def _enhanced_token_changes(
        self,
        tx: dict[str, Any],
        wallet: str,
    ) -> dict[str, float]:
        changes: dict[str, float] = defaultdict(float)

        for account in tx.get("accountData", []):
            for balance_change in account.get("tokenBalanceChanges", []):
                if balance_change.get("userAccount") != wallet:
                    continue

                mint = balance_change.get("mint")
                if not isinstance(mint, str) or not mint:
                    continue

                raw_amount = balance_change.get("rawTokenAmount", {})
                changes[mint] += self._raw_ui_amount(raw_amount)

        return dict(changes)

    @staticmethod
    def _enhanced_sol_change(tx: dict[str, Any], wallet: str) -> float:
        for account in tx.get("accountData", []):
            if account.get("account") == wallet:
                lamports = account.get("nativeBalanceChange") or 0
                return float(lamports) / LAMPORTS_PER_SOL

        return 0.0

    def _raw_token_changes(
        self,
        meta: dict[str, Any],
        wallet: str,
    ) -> dict[str, float]:
        balances: dict[tuple[str, str], dict[str, float]] = defaultdict(
            lambda: {"before": 0.0, "after": 0.0}
        )

        for state, field in (
            ("before", "preTokenBalances"),
            ("after", "postTokenBalances"),
        ):
            for balance in meta.get(field, []):
                owner = balance.get("owner")
                mint = balance.get("mint")
                if owner != wallet or not isinstance(mint, str) or not mint:
                    continue

                amount = self._ui_amount(balance.get("uiTokenAmount", {}))
                balances[(owner, mint)][state] += amount

        return {
            mint: amounts["after"] - amounts["before"]
            for (_, mint), amounts in balances.items()
        }

    def _raw_sol_change(
        self,
        tx: dict[str, Any],
        meta: dict[str, Any],
        wallet: str,
    ) -> float:
        account_keys = (
            tx.get("transaction", {})
            .get("message", {})
            .get("accountKeys", [])
        )
        normalized_keys = [
            key.get("pubkey") if isinstance(key, dict) else key
            for key in account_keys
        ]

        try:
            wallet_index = normalized_keys.index(wallet)
            before = meta.get("preBalances", [])[wallet_index]
            after = meta.get("postBalances", [])[wallet_index]
        except (IndexError, ValueError, TypeError):
            return 0.0

        return (float(after) - float(before)) / LAMPORTS_PER_SOL

    def _ui_amount(self, amount: dict[str, Any]) -> float:
        ui_amount = amount.get("uiAmount")
        if ui_amount is not None:
            return float(ui_amount)

        ui_amount_string = amount.get("uiAmountString")
        if ui_amount_string is not None:
            return float(ui_amount_string)

        return self._raw_ui_amount(amount)

    @staticmethod
    def _raw_ui_amount(amount: dict[str, Any]) -> float:
        raw_value = amount.get("tokenAmount", amount.get("amount", 0))
        decimals = int(amount.get("decimals", 0))
        return float(raw_value or 0) / (10**decimals)
