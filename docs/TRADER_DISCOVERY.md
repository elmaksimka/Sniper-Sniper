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

The defaults inspect ten transactions per program and one page per worker cycle.
This is deliberately a sample: the public Solana endpoint is rate-limited and
is not a full market indexer. When the saved cursor falls outside the bounded
window, the worker records a warning, ingests the latest sample, and advances
the cursor instead of becoming permanently stuck on an unfillable gap.

## Configuration

```dotenv
DISCOVERY_ENABLED=true
DISCOVERY_PROGRAM_IDS=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P,pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA
DISCOVERY_PAGE_SIZE=10
DISCOVERY_MAX_PAGES=1
AUTO_PROMOTE_WALLET_SCORE=65
AUTO_PROMOTE_MAX_MONITORS=100
```

Increasing the page count or size consumes more public RPC capacity and can
produce HTTP `429` responses. Keep the conservative defaults in the fully free
mode. A dedicated RPC or streaming indexer would be required for comprehensive,
low-latency market coverage.

Promotion is evidence-based rather than immediate: a newly observed wallet
usually needs multiple buys and sells before its performance, exit experience,
and data quality can reach grade A or B. Once promoted, its own history is
polled independently of the sampled DEX stream.
