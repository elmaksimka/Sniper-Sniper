# Token score v1

`GET /api/v1/scores/tokens/{address}` returns an explainable observed-data
heuristic from 0 to 100. It is not a price forecast or financial advice.

## Components

- activity (20): reaches its cap at 50 normalized trades
- participation (15): reaches its cap at 20 unique observed wallets
- holder distribution (25): combines active-holder breadth with lower
  top-holder concentration
- flow balance (15): rewards two-sided observed buy/sell token flow
- creator history (15): combines launch breadth with the share of launches that
  have observed trading
- data quality (10): combines creator attribution with complete wallet histories

The response includes the component values, methodology version,
`top_holder_share`, and `incomplete_holder_ratio`.

## Materialized scores

Each persisted trade emits a token update and atomically upserts the latest
`token_score_snapshots` row. `GET /api/v1/scores/tokens` returns the materialized
leaderboard and accepts the same `grade` values as the wallet leaderboard.

After deploying the snapshot migration, populate existing tokens and wallets:

```powershell
poetry run python -m app.backfill_scores
```

Scores at or above `TOKEN_SCORE_ALERT_THRESHOLD` with grade A or B emit
deduplicated token alerts. Token and wallet alert keys are namespaced separately.

## Limitations

The score uses only data ingested by Alpha Engine. Observed holder concentration
is not a complete on-chain distribution. Token-to-token trades without a
reliable SOL valuation still contribute token flow but not a market price or
market-cap signal.
