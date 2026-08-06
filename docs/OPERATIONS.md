# Operations

## Health endpoints

- `GET /health` and `GET /health/live` are process liveness probes. They do not
  call external dependencies.
- `GET /health/ready` returns `200` only when PostgreSQL responds, Helius reports
  healthy, and the elected monitor worker has a fresh database heartbeat.
- Readiness returns `503` with per-component status when any required component
  is unavailable or the worker heartbeat is stale.

The leader worker writes heartbeats on an independent interval, including while
a long wallet catch-up is running. Standby replicas do not overwrite the leader
heartbeat. Configure the interval and stale boundary with
`WORKER_HEARTBEAT_INTERVAL_SECONDS` and `WORKER_HEARTBEAT_STALE_SECONDS`; the
stale boundary should remain several times larger than the interval.
Each dependency check is bounded by `READINESS_CHECK_TIMEOUT_SECONDS`, so a
stalled dependency cannot leave the HTTP probe hanging indefinitely.

## Deployment order

1. Apply migrations with `poetry run alembic upgrade head`.
2. Start one or more `python -m app.worker` replicas.
3. Start the API and wait for `/health/ready` before routing traffic.

The heartbeat table is created by migration `c4d2b8e71a63`. Until that migration
is applied and a leader worker writes its first heartbeat, readiness intentionally
returns `503`.
