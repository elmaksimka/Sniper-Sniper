# Alpha Engine Architecture

## Philosophy

The project is built around **events**, not API calls.

Everything that happens on-chain becomes an internal event.

The rest of the system reacts to those events.

---

# Layers

Datasource

↓

Normalizer

↓

Event Bus

↓

Domain Services

↓

Storage

↓

Scoring

↓

Alerts

↓

API / Dashboard

---

## Datasources

Examples:

- Solana RPC
- Helius
- Yellowstone
- Future blockchains

A datasource should NEVER contain business logic.

Its only responsibility is receiving external data.

---

## Normalizer

Every datasource has its own format.

The normalizer converts external messages into internal events.

Example:

Helius transaction

↓

TradeObserved

---

## Event Bus

The Event Bus distributes events.

It never analyzes data.

It never writes to the database.

It only delivers events.

---

## Domain Services

Examples:

Wallet Service

Funding Service

Creator Service

Token Service

Holder Service

Cluster Service

Each service owns its own logic.

---

## Storage

Storage is an implementation detail.

Today PostgreSQL.

Tomorrow ClickHouse.

Nothing above this layer should care.

---

## Scoring

Consumes domain data.

Produces intelligence.

Examples:

Wallet Score

Token Score

Funding Score

Alpha Score

---

## Alerts

Consumes scores.

Produces notifications.

Telegram

Discord

REST API

WebSocket

---

## Important Rule

Dependencies always point downward.

Never upward.