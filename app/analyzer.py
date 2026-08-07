from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.core.assets import is_target_mint


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
    """Normalize wallet balance changes into conservatively priced trades."""

    def analyze_transaction(
        self,
        tx: dict[str, Any],
        wallet: str,
    ) -> list[TokenTrade]:
        transaction = self._unwrap_rpc_result(tx)
        token_changes = self._enhanced_token_changes(transaction, wallet)

        if not token_changes:
            token_changes = self._raw_token_changes(
                self._meta(transaction),
                wallet,
            )
        token_changes = {
            mint: change
            for mint, change in token_changes.items()
            if is_target_mint(mint)
        }

        economic_sol_change = self._economic_sol_change(transaction, wallet)
        fee = self._network_fee(transaction, wallet)
        sol_by_mint = self._allocate_sol(
            token_changes,
            economic_sol_change,
            fee,
        )

        return [
            TokenTrade(
                mint=mint,
                wallet=wallet,
                sol_change=sol_by_mint[mint],
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

    def _economic_sol_change(self, tx: dict[str, Any], wallet: str) -> float:
        swap_change = self._swap_native_change(tx, wallet)
        if swap_change is not None:
            return swap_change

        transfer_change = self._native_transfer_change(tx, wallet)
        if transfer_change is not None:
            return transfer_change

        balance_change = self._native_balance_change(tx, wallet)
        if balance_change == 0:
            return 0.0

        # Account balance changes include the network fee. Remove it here;
        # allocation adds it back exactly once to an unambiguous trade.
        return balance_change + self._network_fee(tx, wallet)

    def _swap_native_change(
        self,
        tx: dict[str, Any],
        wallet: str,
    ) -> float | None:
        swap = tx.get("events", {}).get("swap")
        if not isinstance(swap, dict):
            return None

        native_input = swap.get("nativeInput") or {}
        native_output = swap.get("nativeOutput") or {}
        spent = (
            self._lamports(native_input.get("amount"))
            if native_input.get("account") == wallet
            else 0.0
        )
        received = (
            self._lamports(native_output.get("amount"))
            if native_output.get("account") == wallet
            else 0.0
        )
        return received - spent

    def _native_transfer_change(
        self,
        tx: dict[str, Any],
        wallet: str,
    ) -> float | None:
        transfers = tx.get("nativeTransfers")
        if not isinstance(transfers, list) or not transfers:
            return None

        change = 0.0
        involved = False
        for transfer in transfers:
            amount = self._lamports(transfer.get("amount"))
            if transfer.get("fromUserAccount") == wallet:
                change -= amount
                involved = True
            if transfer.get("toUserAccount") == wallet:
                change += amount
                involved = True
        return change if involved else None

    def _native_balance_change(self, tx: dict[str, Any], wallet: str) -> float:
        for account in tx.get("accountData", []):
            if account.get("account") == wallet:
                return self._lamports(account.get("nativeBalanceChange"))

        meta = self._meta(tx)
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

        return self._lamports(float(after) - float(before))

    def _network_fee(self, tx: dict[str, Any], wallet: str) -> float:
        fee_payer = tx.get("feePayer") or self._raw_fee_payer(tx)
        if fee_payer != wallet:
            return 0.0

        fee = tx.get("fee")
        if fee is None:
            fee = self._meta(tx).get("fee", 0)
        return self._lamports(fee)

    @staticmethod
    def _raw_fee_payer(tx: dict[str, Any]) -> str | None:
        account_keys = (
            tx.get("transaction", {})
            .get("message", {})
            .get("accountKeys", [])
        )
        if not account_keys:
            return None

        first = account_keys[0]
        if isinstance(first, dict):
            pubkey = first.get("pubkey")
            return pubkey if isinstance(pubkey, str) else None
        return first if isinstance(first, str) else None

    @staticmethod
    def _allocate_sol(
        token_changes: dict[str, float],
        economic_sol_change: float,
        network_fee: float,
    ) -> dict[str, float]:
        allocated = {mint: 0.0 for mint in token_changes}
        if economic_sol_change == 0:
            return allocated

        candidates = [
            mint
            for mint, token_change in token_changes.items()
            if (
                economic_sol_change < 0 < token_change
                or economic_sol_change > 0 > token_change
            )
        ]
        if len(candidates) == 1:
            allocated[candidates[0]] = economic_sol_change - network_fee
        return allocated

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

    @staticmethod
    def _lamports(value: Any) -> float:
        return float(value or 0) / LAMPORTS_PER_SOL
