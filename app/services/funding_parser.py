from __future__ import annotations

from typing import Any

from app.core.funding import NativeTransfer


LAMPORTS_PER_SOL = 1_000_000_000


class FundingParser:
    """Extract explicit native SOL transfers from parsed transactions."""

    def extract_transfers(self, tx: dict[str, Any]) -> list[NativeTransfer]:
        transfers: list[NativeTransfer] = []

        instructions = (
            tx.get("transaction", {}).get("message", {}).get("instructions", [])
        )
        self._extract_instruction_group(instructions, "outer", transfers)

        for group in tx.get("meta", {}).get("innerInstructions", []):
            if not isinstance(group, dict):
                continue
            parent_index = group.get("index")
            self._extract_instruction_group(
                group.get("instructions", []),
                f"inner:{parent_index}",
                transfers,
            )

        # Enhanced Transaction payloads expose the same information directly.
        for index, transfer in enumerate(tx.get("nativeTransfers", [])):
            if not isinstance(transfer, dict):
                continue
            parsed = self._build_transfer(
                transfer.get("fromUserAccount"),
                transfer.get("toUserAccount"),
                transfer.get("amount"),
                f"native:{index}",
            )
            if parsed is not None and parsed not in transfers:
                transfers.append(parsed)

        return transfers

    def _extract_instruction_group(
        self,
        instructions: object,
        prefix: str,
        transfers: list[NativeTransfer],
    ) -> None:
        if not isinstance(instructions, list):
            return

        for index, instruction in enumerate(instructions):
            if not isinstance(instruction, dict):
                continue
            if instruction.get("program") != "system":
                continue
            parsed = instruction.get("parsed")
            if not isinstance(parsed, dict) or parsed.get("type") not in {
                "transfer",
                "transferWithSeed",
            }:
                continue
            info = parsed.get("info")
            if not isinstance(info, dict):
                continue
            transfer = self._build_transfer(
                info.get("source"),
                info.get("destination"),
                info.get("lamports"),
                f"{prefix}:{index}",
            )
            if transfer is not None:
                transfers.append(transfer)

    @staticmethod
    def _build_transfer(
        source: object,
        destination: object,
        lamports: object,
        instruction_index: str,
    ) -> NativeTransfer | None:
        if (
            not isinstance(source, str)
            or not source
            or not isinstance(destination, str)
            or not destination
            or source == destination
            or isinstance(lamports, bool)
            or not isinstance(lamports, int | float)
            or lamports <= 0
        ):
            return None
        return NativeTransfer(
            source=source,
            destination=destination,
            amount_sol=float(lamports) / LAMPORTS_PER_SOL,
            instruction_index=instruction_index,
        )
