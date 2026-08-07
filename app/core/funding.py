from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NativeTransfer:
    source: str
    destination: str
    amount_sol: float
    instruction_index: str
