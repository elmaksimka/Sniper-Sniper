# Oracle Cloud Always Free staging

This is the zero-hosting-cost staging path for Alpha Engine. It runs PostgreSQL,
the migration job, worker, API, and Caddy on one Oracle Cloud Always Free
Ampere A1 VM. Caddy terminates HTTPS and the API remains bound to the VM's
loopback interface.

Always Free capacity is subject to regional availability. Oracle may reclaim
idle compute instances, so this path is suitable for staging rather than a
production system with a contractual uptime target. A domain is optional: a
free DNS hostname that resolves to the VM can be used instead.

## Provision the VM

1. Create an Always Free eligible Ampere A1 Compute instance using Ubuntu
   24.04, with 2 OCPUs and 12 GB RAM. Keep all attached resources marked
   Always Free eligible before confirming them.
2. Reserve its public IPv4 address so DNS does not change after a reboot.
3. In the OCI subnet security list or network security group, allow inbound
   TCP 80 and 443 from the internet. Restrict TCP 22 to the administrator's IP.
   Do not expose ports 5432 or 8000.
4. Point a DNS A record at the reserved address. For a no-cost staging hostname,
   a public wildcard DNS service can map an IP-derived hostname to that address.

OCI account verification can require a payment card, but an Always Free
eligible configuration does not create a recurring compute charge. Review the
Oracle cost estimator before creating the instance; do not accept paid shape,
storage, or support upgrades.

## Install and configure

Install Git and Docker Engine from their official Ubuntu repositories, then
clone the repository. Copy the environment template:

```bash
cp .env.production.example .env
chmod 600 .env
```

Replace every placeholder. At minimum:

- set `GIT_SHA` to `git rev-parse HEAD`;
- generate independent random values for `POSTGRES_PASSWORD` and
  `ADMIN_API_KEY`;
- set `HELIUS_API_KEY`;
- set `API_DOMAIN` to the public DNS hostname;
- set `ALLOWED_HOSTS` to that hostname plus `localhost,127.0.0.1`;
- keep `API_BIND_ADDRESS=127.0.0.1` so port 8000 is never internet-facing;
- set `FORWARDED_ALLOW_IPS` to the Docker network used by Caddy, or leave the
  default when client-IP forwarding is not required.

Start the complete stack:

```bash
docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.oci.yml \
  up -d --build
docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.oci.yml \
  ps
```

Caddy obtains and renews the TLS certificate automatically after public DNS and
ports 80/443 are reachable. Confirm that only SSH, HTTP, and HTTPS are exposed
from the VM.

## Acceptance and operations

Run the release checks in [`RELEASE.md`](RELEASE.md) against
`https://<API_DOMAIN>`. Inspect startup logs with:

```bash
docker compose \
  -f docker-compose.prod.yml \
  -f docker-compose.oci.yml \
  logs migrate api worker caddy
```

Run the verified database backup job on a schedule and copy its output off the
VM. A backup stored only on the same boot volume is not disaster recovery. The
commands and restore drill are in [`OPERATIONS.md`](OPERATIONS.md).

For an update, fetch the reviewed revision, set its exact `GIT_SHA`, rebuild,
and run the same `up -d` command. The migration container must complete before
the API and worker start.
