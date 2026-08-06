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

The shared Helius client keeps a reusable HTTP connection pool, limits
concurrent requests, and retries transport failures, HTTP `408`/`429` and
selected `5xx` responses with bounded exponential backoff. `Retry-After` is
honored when Helius provides it. Transient JSON-RPC rate-limit and availability
errors use the same retry policy; permanent RPC errors are surfaced to the
worker and recorded on the affected monitor.

## Remaining production work

- add integration tests against a real PostgreSQL instance and recorded RPC
  responses
- add worker leader election before running multiple replicas
