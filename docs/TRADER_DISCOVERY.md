# Automatic trader discovery

The free local worker bootstraps its wallet database by sampling recent activity
from configured Solana programs. The default sources are the official Pump
bonding-curve program and PumpSwap AMM program.

For each source the worker:

1. retrieves a bounded page of finalized signatures;
2. fetches the corresponding parsed transactions;
3. identifies the fee payer and derives wallet-owned token/SOL changes;
4. persists normalized trades and recalculates wallet and token scores;
5. stores a source cursor in `service_heartbeats` to avoid replaying the same
   window;
6. promotes an A/B wallet at or above `AUTO_PROMOTE_WALLET_SCORE` into the
   continuous monitor list, subject to `AUTO_PROMOTE_MAX_MONITORS`.

The free local defaults inspect fifty transactions per program every two
minutes. Candidate history enrichment and monitored top-trader wallets run in
separate loops, so slow history loading does not delay discovery. This remains
a bounded sample: the
public Solana endpoint is rate-limited and is not a full market indexer. When
the saved cursor falls outside the bounded window, the worker records a
warning, ingests the latest sample, and advances the cursor instead of becoming
permanently stuck on an unfillable gap.

Failed discovery cycles use bounded exponential backoff: 4, 8, then 15 minutes
maximum with the default configuration. A successful cycle restores the normal
two-minute interval. Failures are isolated per program, so Pump can still be
sampled when PumpSwap fails, or vice versa.

## Configuration

```dotenv
DISCOVERY_ENABLED=true
DISCOVERY_PROGRAM_IDS=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P,pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA
DISCOVERY_PAGE_SIZE=50
DISCOVERY_MAX_PAGES=1
DISCOVERY_POLL_INTERVAL_SECONDS=120
DISCOVERY_RETRY_MAX_SECONDS=900
AUTO_PROMOTE_WALLET_SCORE=65
AUTO_PROMOTE_MAX_MONITORS=100
```

Increasing the page count, size, or frequency consumes more public RPC capacity
and can produce HTTP `429` responses. Keep the adaptive defaults in the fully
free mode. A dedicated RPC or streaming indexer would be required for
comprehensive, low-latency market coverage.

The fully free local profile serializes RPC calls with
`HELIUS_MAX_CONCURRENCY=1`. Discovery, candidate enrichment, and monitored
wallet polling remain independent tasks, but share this single request slot to
avoid simultaneous bursts against the public endpoint.

Promotion is evidence-based rather than immediate: a newly observed wallet
usually needs multiple buys and sells before its performance, exit experience,
and data quality can reach grade A or B. Once promoted, its own history is
polled independently of the sampled DEX stream.

## Candidate history enrichment

The free local mode closes the sparse-history gap without promoting weak
wallets prematurely. Its independent background loop selects the highest-scored
unmonitored wallet at or above 35, loads its latest 75 transactions, ingests
them oldest-first, and recalculates the wallet score. A
persistent `candidate:<wallet>` record prevents repeated backfills. Transient
errors are retried after 30 minutes.

Only one candidate is enriched per background cycle by default. This caps the
additional public-RPC load without blocking DEX discovery. If enrichment lifts
the wallet to A/B and 65 or higher, the normal promotion collector adds it to
continuous monitoring.

```dotenv
CANDIDATE_ENRICHMENT_ENABLED=true
CANDIDATE_ENRICHMENT_MIN_SCORE=35
CANDIDATE_ENRICHMENT_HISTORY_LIMIT=75
CANDIDATE_ENRICHMENT_MAX_PER_CYCLE=1
CANDIDATE_ENRICHMENT_RETRY_SECONDS=1800
```

Historical backfill never creates a stale trading alert: alpha signals reject
buys older than `ALPHA_SIGNAL_MAX_AGE_SECONDS` (five minutes by default).
The Telegram health message reports the candidate address, score before/after,
and the configured history limit. `Кандидатів оброблено` is a per-cycle count,
not the cumulative number of wallets examined since startup.
