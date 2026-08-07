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

Run the continuous monitored-wallet worker:

```powershell
poetry run python -m app.worker
```

Helius timeout, retry backoff, and maximum concurrency are configurable through
the `HELIUS_*` variables listed in `.env.example`.
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
- `GET /api/v1/scores/wallets/{address}`
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

Transaction normalization and conservative SOL allocation are documented in
[`docs/ACCOUNTING.md`](docs/ACCOUNTING.md).
Native SOL funding extraction is documented in
[`docs/FUNDING.md`](docs/FUNDING.md).
Wallet history pagination is documented in
[`docs/INGESTION.md`](docs/INGESTION.md).
Production probes and startup ordering are documented in
[`docs/OPERATIONS.md`](docs/OPERATIONS.md).
Container image and production Compose deployment are documented in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

## Status

🚧 In development.
