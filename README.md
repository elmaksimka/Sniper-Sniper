# Alpha Engine

> Intelligent on-chain analytics platform for Solana.

## Vision

Alpha Engine is not another meme coin scanner.

It is an intelligence platform that analyzes wallets, creators, funding relationships, token launches, and on-chain behavior to identify high-potential opportunities before they become obvious.

---

## Core Principles

- Event-driven architecture
- Domain-first design
- Modular services
- Testable components
- Chain-agnostic architecture
- Production-ready from day one

---

## Modules

- Event Listener
- Token Engine
- Wallet Engine
- Funding Engine
- Holder Engine
- Wallet Genome
- Alpha Scoring
- Alert Engine
- Dashboard
- ML Engine (future)

---

## Running locally

The simplest fully free option runs the whole system on demand in Docker, uses
the public Solana RPC, and preserves its local database between runs. See
[`docs/LOCAL_FREE.md`](docs/LOCAL_FREE.md).

Start PostgreSQL and apply migrations:

```powershell
docker compose up -d postgres
poetry run alembic upgrade head
poetry run python -m app.backfill_scores
```

Run the wallet scanner:

```powershell
poetry run python -m app.main
```

The score backfill command updates both wallet and token snapshots.

Run the continuous monitored-wallet worker:

```powershell
poetry run python -m app.worker
```

Helius timeout, retry backoff, and maximum concurrency are configurable through
the `HELIUS_*` variables listed in `.env.example`.
Wallet and token score alert thresholds are independently configurable with
`WALLET_SCORE_ALERT_THRESHOLD` and `TOKEN_SCORE_ALERT_THRESHOLD`.
In production, monitor mutations and alert acknowledgement require the
`X-API-Key` header configured by `ADMIN_API_KEY`.
Production also requires an explicit `ALLOWED_HOSTS` list and disables the
interactive API documentation endpoints.
The production Compose file includes an opt-in verified PostgreSQL backup job;
see [`docs/OPERATIONS.md`](docs/OPERATIONS.md) for backup and restore drills.
Multiple worker replicas are safe: PostgreSQL advisory-lock leader election
keeps exactly one replica active while the others wait for failover.

Run the read API:

```powershell
poetry run uvicorn app.api.app:app --reload
```

The OpenAPI UI is available at `http://127.0.0.1:8000/docs`.

Run the default test suite:

```powershell
poetry run pytest -q
```

The GitHub Actions quality gate runs Ruff, MyPy, migrations against a clean
PostgreSQL 17 service, the full test suite, and a production Docker build on
every push and pull request.

PostgreSQL integration tests require an explicit test URL. They create and drop
only a randomly named `alpha_test_*` schema:

```powershell
$env:TEST_DATABASE_URL="postgresql+asyncpg://alpha:alpha@localhost:5432/alpha_engine"
poetry run pytest tests/integration -q
```

Read endpoints:

- `GET /health`
- `GET /health/live`
- `GET /health/ready`
- `GET /version`
- `GET /api/v1/tokens`
- `GET /api/v1/tokens/{address}`
- `GET /api/v1/wallets`
- `GET /api/v1/wallets/{address}`
- `GET /api/v1/trades`
- `GET /api/v1/funding/transfers`
- `GET /api/v1/funding/wallets/{address}`
- `GET /api/v1/analytics/wallets/{address}`
- `GET /api/v1/analytics/wallets/{address}/positions`
- `GET /api/v1/analytics/tokens/{address}`
- `GET /api/v1/analytics/tokens/{address}/holders`
- `GET /api/v1/analytics/creators/{address}`
- `GET /api/v1/scores/wallets/{address}`
- `GET /api/v1/scores/tokens/{address}`
- `GET /api/v1/scores/tokens`
- `GET /api/v1/scores/wallets`
- `GET /api/v1/alerts`
- `POST /api/v1/alerts/{alert_id}/acknowledge`
- `GET /api/v1/monitors`
- `POST /api/v1/monitors`
- `POST /api/v1/monitors/{address}/enable`
- `DELETE /api/v1/monitors/{address}`

### Wallet score v1

The wallet score is an explainable 0-100 heuristic composed of:

- activity: 20 points
- token diversification: 15 points
- exit experience: 20 points
- realized performance: 35 points
- data quality: 10 points

The API returns every component, the methodology version, realized ROI, and
the unmatched-sell ratio. It is an analytics heuristic, not a prediction or
financial advice.

### Token score v1

The observed token score is an explainable 0-100 heuristic composed of:

- activity: 20 points
- wallet participation: 15 points
- observed holder distribution: 25 points
- buy/sell flow balance: 15 points
- creator launch history: 15 points
- data quality: 10 points

It uses only ingested trades, observed holders, and stored creator metadata. It
is not a complete on-chain holder snapshot, price forecast, or financial advice.

Transaction normalization and conservative SOL allocation are documented in
[`docs/ACCOUNTING.md`](docs/ACCOUNTING.md).
Native SOL funding extraction is documented in
[`docs/FUNDING.md`](docs/FUNDING.md).
Observed holder analytics is documented in
[`docs/HOLDERS.md`](docs/HOLDERS.md).
Creator-level launch analytics is documented in
[`docs/CREATORS.md`](docs/CREATORS.md).
The observed token scoring methodology is documented in
[`docs/TOKEN_SCORING.md`](docs/TOKEN_SCORING.md).
Wallet history pagination is documented in
[`docs/INGESTION.md`](docs/INGESTION.md).
Production probes and startup ordering are documented in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).
Container image and production Compose deployment are documented in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
Release acceptance is documented in
[`docs/RELEASE.md`](docs/RELEASE.md), with changes listed in
[`CHANGELOG.md`](CHANGELOG.md).
Fully free on-demand local operation is documented in
[`docs/LOCAL_FREE.md`](docs/LOCAL_FREE.md). Zero-cost eligible OCI staging is
documented in [`docs/OCI_FREE.md`](docs/OCI_FREE.md), while optional paid
managed staging on Render is covered by [`docs/RENDER.md`](docs/RENDER.md).

## Status

Backend MVP `v0.1.0-rc.1`. The application, migrations, CI gate, production
containers, health checks, access controls, graceful shutdown, verified backup
workflow, and zero-cost OCI deployment overlay are complete. Remaining work is
provisioning the external staging account and applying real secrets and DNS.
