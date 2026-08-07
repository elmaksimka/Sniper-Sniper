# Observed token holders

Alpha Engine derives observed token positions from normalized trades ingested
for monitored wallets. This is not a complete on-chain holder snapshot: wallets
outside the monitored history are not represented.

`GET /api/v1/analytics/tokens/{address}/holders` returns positions ordered by
observed quantity. Buys add quantity and sells remove it. Quantity is clamped at
zero when the observed history begins with sells; the excess is exposed as
`unmatched_sell_quantity` and `has_incomplete_history=true`.

Trades are applied in `(timestamp, id)` order. An unmatched early sell does not
consume a later buy, matching the conservative wallet position accounting.

Closed and incomplete zero-quantity positions are hidden by default. Set
`include_closed=true` to include them. Pagination is performed in PostgreSQL.
