# Creator analytics

`GET /api/v1/analytics/creators/{address}` aggregates all tokens attributed to
a creator by stored token metadata. It reports launch count, traded launches,
unique observed traders, SOL-denominated activity, and ranked token results.

Token amounts are not summed across launches because different SPL tokens are
not comparable units. `observed_sol_volume` is the sum of absolute normalized
SOL changes and excludes token-to-token activity that has no reliable SOL
valuation. `net_wallet_sol_change` retains direction from the observed traders'
perspective.

The response is based only on tokens and trades currently ingested by Alpha
Engine. `token_limit` controls the ranked token list without changing aggregate
creator totals.
