# Wallet score v3

Wallet score v3 is an explainable 0-100 heuristic based only on trades ingested
by Alpha Engine. It is not a complete tax ledger, a prediction, or financial
advice.

## Components

- activity: up to 20 points at 50 observed trades;
- diversification: up to 15 points at 10 observed target tokens;
- exit experience: up to 20 points from the sell-count/buy-count ratio;
- realized performance: up to 35 points composed of 10 points for overall ROI,
  10 for realized token-position win rate, 5 for diversified PnL, and 10 for
  ROI after removing the single best realized token position;
- data quality: up to 10 points, multiplying priced-trade coverage by the
  complement of the unmatched-sell ratio.

## Realized accounting

Positions use weighted-average cost basis. Realized ROI is:

```text
sum(realized PnL in SOL) / sum(cost basis of priced quantities actually sold)
```

Open inventory is excluded from this denominator. A buy without a known SOL
cost and a sell without known SOL proceeds do not create artificial realized
profit or loss. When priced and unpriced inventory are mixed, sold quantity is
allocated proportionally between them.

## Confidence fields

`priced_trade_ratio` is the fraction of trades with a usable economic SOL flow:
a negative SOL change for a buy or a positive SOL change for a sell.
`unmatched_sell_ratio` captures sells that precede the available buy history.
Both reduce `data_quality_score`.

`win_rate` is profitable realized token positions divided by all positions with
a known realized cost basis. `pnl_concentration_ratio` is the largest positive
position PnL divided by gross positive PnL. The fields
`realized_pnl_ex_top_position_sol` and `realized_roi_ex_top_position` expose
whether the wallet remains profitable without its largest winner. These are
token-position metrics, not per-swap win rates.

History may still be incomplete when RPC pagination is capped. Consumers should
consider score components and confidence fields, not only the headline grade.
