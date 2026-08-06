# Transaction Accounting

Alpha Engine uses conservative SOL allocation for normalized token trades.

## Data priority

1. Helius `events.swap.nativeInput` and `nativeOutput`, when available
2. Helius `nativeTransfers`
3. Wallet native balance changes from `accountData` or raw RPC metadata

Network fees are removed from balance-change fallbacks before matching and are
added back exactly once when a SOL-to-token or token-to-SOL trade has one
unambiguous token candidate.

## Ambiguous transactions

When one SOL flow could match multiple token balance changes, every resulting
trade receives `sol_change = 0`. The system intentionally leaves the value
unpriced instead of duplicating SOL cost across tokens.

Token-to-token swaps also have `sol_change = 0`; their SOL-denominated cost
basis requires a separate historical price source.

## Known limitations

- Unsupported or partially parsed protocols may only expose balance changes.
- Rent changes can be present in native balance fallbacks.
- Token-to-token swaps do not yet contribute SOL cost basis or realized PnL.
- Primary history ingestion uses `getTransactionsForAddress` with full raw
  transactions. Enhanced swap events remain an optional enrichment path.
