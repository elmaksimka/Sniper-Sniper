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

Run the read API:

```powershell
poetry run uvicorn app.api.app:app --reload
```

The OpenAPI UI is available at `http://127.0.0.1:8000/docs`.

Read endpoints:

- `GET /health`
- `GET /api/v1/tokens`
- `GET /api/v1/tokens/{address}`
- `GET /api/v1/wallets`
- `GET /api/v1/wallets/{address}`
- `GET /api/v1/trades`
- `GET /api/v1/analytics/wallets/{address}`
- `GET /api/v1/analytics/wallets/{address}/positions`
- `GET /api/v1/analytics/tokens/{address}`
- `GET /api/v1/scores/wallets/{address}`
- `GET /api/v1/scores/wallets`
- `GET /api/v1/alerts`
- `POST /api/v1/alerts/{alert_id}/acknowledge`

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
Wallet history pagination is documented in
[`docs/INGESTION.md`](docs/INGESTION.md).

## Status

🚧 In development.
