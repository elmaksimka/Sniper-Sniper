# Changelog

All notable changes to Alpha Engine are documented here.

## [0.1.0-rc.1] - 2026-08-07

First backend MVP release candidate.

### Added

- Event-driven Solana ingestion through Helius with bounded retries,
  concurrency, pagination, and transaction normalization.
- Persistent PostgreSQL models and a linear Alembic migration chain.
- Token, wallet, trade, funding, observed-holder, creator, and position
  analytics exposed through a paginated FastAPI read API.
- Explainable wallet and token scoring, materialized leaderboards, and
  deduplicated typed score alerts.
- Continuously monitored wallets with checkpoints, PostgreSQL advisory-lock
  leader election, heartbeats, and graceful `SIGTERM`/`SIGINT` shutdown.
- Liveness/readiness probes, release build identity, request correlation,
  defensive HTTP headers, trusted-host enforcement, and production admin-key
  authentication.
- Non-root production image, migration-first Compose deployment, verified
  PostgreSQL backups, restore drill documentation, and a complete CI gate.

### Verified

- Full isolated production-like rehearsal from a clean PostgreSQL volume.
- Alembic upgrade to head, Helius health, worker heartbeat, API readiness,
  release identity, admin authorization, and graceful container shutdown.
- Verified dump and restore into a separate disposable database.
- 122 automated tests plus Ruff and MyPy checks.

### Known limitations

- Holder analytics describe only wallets observed in ingested trade history;
  they are not a complete on-chain holder snapshot.
- Scores are explainable heuristics, not price forecasts or financial advice.
- Dashboard and ML modules are outside this backend MVP release candidate.
- External staging still requires environment-specific DNS/TLS, production
  PostgreSQL, secret injection, and off-host backup scheduling.
