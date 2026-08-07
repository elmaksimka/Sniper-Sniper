# Render staging deployment

The staging target is Render in the Frankfurt region. `render.yaml` provisions:

- a paid Starter Docker web service for the API;
- a paid Starter Docker background worker;
- a private PostgreSQL 17 `basic-256mb` database.

The API runs Alembic migrations as its pre-deploy command and becomes healthy
only after PostgreSQL, Helius, and the worker heartbeat are all ready. Deploys
wait for GitHub checks, and both services receive up to 60 seconds for graceful
shutdown.

## Create the Blueprint

1. Sign in to Render and connect the private GitHub repository
   `elmaksimka/Sniper-Sniper`.
2. Create a new Blueprint from `render.yaml` on branch `main`.
3. Enter `HELIUS_API_KEY` when Render prompts for the `sync: false` secret.
4. Review the three paid resources before confirming creation.

Render generates `ADMIN_API_KEY`, injects the private PostgreSQL connection,
maps the public `onrender.com` hostname into `ALLOWED_HOSTS`, and maps the exact
`RENDER_GIT_COMMIT` into the image's `GIT_SHA`. Database public access is
disabled.

## Acceptance

After the first deploy, follow `docs/RELEASE.md`. In particular, verify
`/health/ready`, `/version`, admin authentication, worker heartbeat, and a
controlled worker restart. Paid Render Postgres instances include managed
recovery backups; keep the repository's verified logical dump workflow as an
additional portable backup layer when moving to production.
