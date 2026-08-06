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

## Status

🚧 In development.
