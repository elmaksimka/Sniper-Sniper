# Early token score v1

`GET /api/v1/scores/tokens/{address}/early` calculates an on-demand 0-100
heuristic for sparse, newly observed token activity. It is separate from the
mature token score and is used only to qualify top-trader buy signals.

The components are:

- early activity: 15 points, reaching full weight at 10 trades;
- independent wallet participation: 20 points, full weight at 5 wallets;
- buy pressure: 30 points, weighted by up to 5 trades so one buy cannot receive
  the full component;
- observed holder distribution: 20 points;
- observed-history quality: 15 points.

Grades are A at 75, B at 60, C at 45, D at 30, and E below 30. A Telegram
signal additionally requires the configured score threshold, at least three
observed trades, at least two independent wallets, and an A/B wallet score.

The score is not persisted because it must reflect the newest trade at signal
time. It uses only transactions ingested by Alpha Engine. Observed holders are
not a complete on-chain holder snapshot, and the score is not a price forecast
or financial advice.
