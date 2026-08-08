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
`HELIUS_MAX_CONCURRENCY=1` and spaces standard `getTransaction` calls by 0.3
seconds. Discovery, candidate enrichment, and monitored
wallet polling remain independent tasks, but share this single request slot to
avoid simultaneous bursts against the public endpoint.

Promotion is evidence-based rather than immediate: a newly observed wallet
usually needs multiple buys and sells before its performance, exit experience,
and data quality can reach grade A or B. Once promoted, its own history is
polled independently of the sampled DEX stream.

## Top-token trader funnel

When `BIRDEYE_API_KEY` is configured, the primary candidate source is external:

1. load current Solana token profiles from DexScreener;
2. retain pairs created within the last 24 hours and rank them from their 6-hour
   volume, transactions, liquidity, and positive price change;
3. query Birdeye's token top-trader endpoint, sorted by realized PnL rather
   than unrealized holdings;
4. require at least $1,000 realized PnL and 1x realized ROI on the token;
5. prioritize wallets without `dev`, `bundler`, `sniper`, or `insider` tags;
6. backfill wallet history and promote only wallets whose complete local score
   reaches grade A or B.

DexScreener protects the exact web-only `trendingScoreH6` feed with Cloudflare
and does not publish that ranking through its documented API. The stable API
fallback therefore uses DexScreener's profiled tokens and computes the 6-hour
ordering locally. It preserves the requested DexScreener/profile/24-hour
universe without pretending the proprietary score is publicly available.

To stay inside Birdeye's free compute-unit allowance, only five leading tokens
are queried once every six hours by default. The local candidate funnel below
continues between external refreshes.

```dotenv
BIRDEYE_API_KEY=replace-with-a-private-key
CANDIDATE_EXTERNAL_DISCOVERY_INTERVAL_SECONDS=21600
CANDIDATE_EXTERNAL_TOKEN_LIMIT=5
CANDIDATE_EXTERNAL_MINIMUM_REALIZED_PNL_USD=1000
CANDIDATE_EXTERNAL_MINIMUM_REALIZED_ROI=1
```

The free mode cannot query a market-wide "top traders" index from standard
Solana JSON-RPC. Instead, it builds a rolling launch-winner funnel from the
trades already ingested locally:

1. find tokens observed for at least 30 minutes whose latest observed price is
   at least 3x their first observed price;
2. require a minimum of ten transactions and five distinct wallets so a single
   noisy wallet or a short-lived rug cannot make a token a winner;
3. select buyers who entered during the first 30 minutes and before the
   observed price exceeded 2x the first price;
4. prioritize wallets that appeared early in multiple winner tokens, then use
   wallet score and early-buy evidence as tie breakers;
5. take at most ten candidates from each of the top 25 winner tokens,
   deduplicate wallets, and backfill the highest-priority wallet;
6. fall back to the global score leaderboard when the rolling funnel has no
   ready candidate.

This spends no additional market-data subscription and concentrates scarce
public-RPC calls on wallets with evidence from active tokens. It is still based
on the bounded local sample, not a complete Solana market index. DEX Screener's
free public API can validate token liquidity and volume, but does not provide
wallet-level top-trader lists; standard Solana RPC only exposes address history
and individual transactions.

```dotenv
CANDIDATE_SOURCE_WINDOW_HOURS=24
CANDIDATE_SOURCE_TOKEN_LIMIT=25
CANDIDATE_SOURCE_TRADERS_PER_TOKEN=10
CANDIDATE_SOURCE_MINIMUM_TOKEN_TRADES=10
CANDIDATE_SOURCE_MINIMUM_TOKEN_WALLETS=5
CANDIDATE_SOURCE_MINIMUM_OBSERVED_MINUTES=30
CANDIDATE_SOURCE_MINIMUM_CURRENT_MULTIPLE=3
CANDIDATE_SOURCE_EARLY_ENTRY_MINUTES=30
CANDIDATE_SOURCE_EARLY_ENTRY_MAX_MULTIPLE=2
```

## Candidate history enrichment

The free local mode closes the sparse-history gap without rushing wallet
classification. Its independent background loop selects one candidate, loads
one page of up to 75 transactions, ingests it oldest-first, recalculates the
wallet score, and persists the pagination token. Later cycles resume from that
exact checkpoint until the address history is exhausted or the 1,000
transaction safety cap is reached. Transient errors retain the checkpoint and
are retried after 30 minutes, so an RPC limit does not discard completed work.

Only one candidate is enriched per background cycle by default. This caps the
additional public-RPC load without blocking DEX discovery. Existing A/B
wallets are no longer skipped: an unmonitored high-score trader from a top
24-hour token can receive the same bounded history check as a sparse C/D
candidate. If enrichment confirms an eligible A/B holder at 65 or higher, the
normal promotion collector adds it to continuous monitoring.

```dotenv
CANDIDATE_ENRICHMENT_ENABLED=true
CANDIDATE_ENRICHMENT_MIN_SCORE=35
CANDIDATE_ENRICHMENT_HISTORY_LIMIT=75
CANDIDATE_ENRICHMENT_MAXIMUM_HISTORY_TRANSACTIONS=1000
CANDIDATE_ENRICHMENT_MAX_PER_CYCLE=1
CANDIDATE_ENRICHMENT_RETRY_SECONDS=1800
```

Historical backfill never creates a stale trading alert: alpha signals reject
buys older than `ALPHA_SIGNAL_MAX_AGE_SECONDS` (five minutes by default).
The Telegram health message reports the candidate address, score before/after,
and the configured history limit. `Кандидатів оброблено` is a per-cycle count,
not the cumulative number of wallets examined since startup.

Trader-style side switching is measured inside a rolling ten-minute window,
not across the wallet's entire lifetime. This continues to reject rapid
buy/sell churn while allowing a patient trader to re-enter or trim the same
token over several hours. Multi-token bursts, rapid round trips, minimum
history, and a proven 30-minute hold remain independent requirements.
