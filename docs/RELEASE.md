# v0.1.0-rc.1 release checklist

## Required inputs

- Immutable Git revision and image tag
- Production PostgreSQL URL and credentials
- Helius API key or RPC URL
- Random `ADMIN_API_KEY` of at least 32 characters
- Public API hostname in `ALLOWED_HOSTS`
- Trusted reverse-proxy address or CIDR in `FORWARDED_ALLOW_IPS`
- Durable `BACKUP_DIR` plus encrypted off-host retention
- DNS and TLS termination

## Pre-deploy

1. Confirm the CI workflow passes for the release revision.
2. Copy `.env.production.example` to the platform secret store and replace
   every placeholder.
3. Set `APP_VERSION=0.1.0`, `GIT_SHA` to the release commit, and `IMAGE_TAG` to
   an immutable identifier.
4. Validate configuration:

   ```powershell
   docker compose -f docker-compose.prod.yml --profile operations config --quiet
   ```

5. Create and export a verified backup of any existing database.

## Deploy

```powershell
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs migrate
```

The migration job must exit successfully before the worker and API are
considered deployable.

## Post-deploy acceptance

1. `GET /health/live` returns `200`.
2. `GET /health/ready` returns `200` with database, Helius, and worker all `ok`.
3. `GET /version` reports `0.1.0`, the expected release SHA, and `production`.
4. Production documentation endpoints return `404`.
5. An admin mutation without `X-API-Key` returns `401`.
6. A malformed monitored wallet address returns `422`.
7. A controlled worker restart exits cleanly and a leader heartbeat reappears.
8. The first scheduled backup succeeds and its archive index verifies.

## Rollback boundary

Do not automatically downgrade Alembic migrations. Restore the previous image
only when its schema contract is compatible with the deployed head. Otherwise
enter maintenance mode and restore a verified pre-deploy backup into a separate
database before controlled cutover.
