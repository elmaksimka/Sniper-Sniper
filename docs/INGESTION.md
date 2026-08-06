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

The continuous monitor worker stores a high-water transaction signature per
wallet. Each poll walks newest-first pages until it finds that signature, then
processes the new batch oldest-first. An incomplete catch-up never advances the
checkpoint.

## Remaining production work

- add retry and rate-limit handling
- add integration tests against a real PostgreSQL instance and recorded RPC
  responses
