from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class WorkerActivityStats:
    total_transactions: int
    total_tokens: int
    recent_transactions: int
    recent_tokens: int
    window_minutes: int
