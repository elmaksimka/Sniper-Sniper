# Wallet Transaction Ingestion

Alpha Engine retrieves wallet history with the Helius
`getTransactionsForAddress` RPC method.

## Request contract

- full transaction details
- finalized commitment
- successful transactions only
- associated token accounts whose balances changed
- up to 100 transactions per page
- newest transactions first

`TransactionScanner.scan_page()` exposes the pagination token for checkpointed
workers. `scan_address()` performs bounded pagination, deduplicates signatures
across pages, and stops if an upstream pagination token repeats.

## Remaining production work

- persist wallet pagination/checkpoint state
- add retry and rate-limit handling
- continuously schedule monitored wallets
- add integration tests against a real PostgreSQL instance and recorded RPC
  responses
