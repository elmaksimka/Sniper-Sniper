# Container deployment

`Dockerfile` produces one non-root runtime image used by the migration job, API,
and worker. `docker-compose.prod.yml` starts PostgreSQL, applies Alembic
migrations once, then starts the worker and API. The API becomes healthy only
after its full readiness probe passes.

## Release gate

The CI workflow must pass before deployment. It validates formatting and types,
upgrades a clean PostgreSQL database to Alembic head, checks model/migration
parity, runs the full suite with integration tests enabled, and builds the same
runtime image used by production.

## Start

Create the production environment file and replace every placeholder secret:

```powershell
Copy-Item .env.production.example .env
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
```

Set `GIT_SHA` to the exact 7-40 character hexadecimal revision being deployed.
The build stores `APP_VERSION` and `GIT_SHA` in OCI image labels and runtime
environment variables. Verify them after deployment with `GET /version`.

`DATABASE_URL` must use the Compose hostname `postgres`, not `localhost`. Keep
`.env` out of version control. In a managed deployment, inject the same variables
from the platform secret store instead of copying a file.
Compose passes required database, Helius, admin-key, and host-allowlist values
explicitly to every application container; missing required values fail during
configuration instead of silently falling back to an incomplete environment.

Set `ADMIN_API_KEY` to at least 32 random characters. Production startup fails
fast when the database URL, Helius configuration, or admin key is missing. Send
the key in the `X-API-Key` header when acknowledging alerts or changing wallet
monitors. Read-only analytics endpoints do not require this key.

Set `ALLOWED_HOSTS` to the public API hostname plus internal probe hostnames
(`localhost` and `127.0.0.1` for the provided Compose healthcheck). Wildcard
hosts are rejected in production. OpenAPI and ReDoc are disabled in production.

`FORWARDED_ALLOW_IPS` defaults to loopback. When a trusted reverse proxy sits in
front of the API, set it to that proxy's address or CIDR; do not use `*` on a
publicly reachable service.

Inspect migration and service logs:

```powershell
docker compose -f docker-compose.prod.yml logs migrate
docker compose -f docker-compose.prod.yml logs api worker
```

Deploy restarts send `SIGTERM` to the worker and allow the configured
`WORKER_STOP_GRACE_PERIOD` for the active poll and resource cleanup to finish.

The deploy must stop if `migrate` exits unsuccessfully. The API and worker both
depend on successful migration completion, so an incompatible schema is never
served automatically.

Configure `BACKUP_DIR` on durable storage and run the verified backup job on an
external schedule. Backup and non-destructive restore-drill commands are
documented in [`OPERATIONS.md`](OPERATIONS.md).

## Release images

Set `IMAGE_TAG` to an immutable release or commit identifier. Build and deploy
that tag; rollback by restoring the previous tag and applying only a migration
strategy known to be backward-compatible with that release.
