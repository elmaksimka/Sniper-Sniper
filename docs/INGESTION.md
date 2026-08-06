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

Multiple worker replicas coordinate through a session-level PostgreSQL advisory
lock. One replica holds a dedicated lock connection and performs ingestion;
standby replicas poll for leadership and take over after the leader releases or
loses its database connection. The leader verifies the connection before every
poll so a stale process cannot continue ingesting after losing the lock.

## Verification

The test suite includes saved Helius JSON-RPC page fixtures that exercise the
HTTP client and pagination scanner together. PostgreSQL integration tests run
inside a randomly named schema and verify monitor persistence plus advisory-lock
failover without modifying application tables.
