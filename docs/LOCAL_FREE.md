# Fully free on-demand mode

This mode runs the complete backend only on the local computer. It has no cloud
hosting, domain, TLS certificate, managed database, or paid Helius requirement.
Docker stores PostgreSQL data in a named local volume, so stopping the stack
does not erase collected data.

The worker uses the rate-limited public Solana Mainnet RPC and standard
`getSignaturesForAddress` plus `getTransaction` calls. Helius DAS metadata is
not available in this mode, so newly discovered tokens can have `Unknown`
metadata. Analytics derived from transactions continue to work.

## First start

Install Docker Desktop, then run from the repository root:

```powershell
.\scripts\start-local.ps1
```

Open `http://127.0.0.1:8000/docs`. Add monitored wallets through the API. The
conservative defaults scan at most three 20-transaction pages every five
minutes to stay friendly to the shared public endpoint.

## Stop and resume

Stop all computation when it is not needed:

```powershell
.\scripts\stop-local.ps1
```

Resume later without rebuilding and without losing PostgreSQL data:

```powershell
.\scripts\start-local.ps1
```

View activity or shut down cleanly:

```powershell
docker compose --env-file .env.local -f docker-compose.local.yml logs -f worker api
docker compose --env-file .env.local -f docker-compose.local.yml down
```

Do not add `--volumes` to `down`: that option deletes the local database. The
public Solana endpoint is intended for development and can return `429` or be
temporarily unavailable. The client applies bounded retries; simply resume the
stack later if the shared service remains busy.

## Cost boundary

There is no subscription or automatic paid overage in this configuration. It
uses only the local computer, internet connection, Docker, PostgreSQL, and the
public Solana RPC. Normal electricity and internet costs still apply. Keep
`TRANSACTION_HISTORY_MODE=standard` and leave both `HELIUS_*` values empty to
preserve this boundary.
