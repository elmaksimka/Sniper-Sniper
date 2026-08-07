# Top-trader token-buy signals

Alpha Engine sends a Telegram alpha signal only after a normalized `buy` trade
meets all of these conditions:

- the transaction has a signature;
- the observed purchase is no older than `ALPHA_SIGNAL_MAX_AGE_SECONDS`;
- the wallet score is at least `ALPHA_WALLET_SCORE_THRESHOLD`;
- the early-token score is at least `ALPHA_EARLY_TOKEN_SCORE_THRESHOLD`;
- the wallet has grade A or B;
- the token has at least `ALPHA_EARLY_TOKEN_MIN_TRADES` observed trades and
  `ALPHA_EARLY_TOKEN_MIN_WALLETS` independent observed wallets;
- the highest-liquidity Dexscreener pair has at least
  `ALPHA_MARKET_MIN_LIQUIDITY_USD` liquidity,
  `ALPHA_MARKET_MIN_VOLUME_5M_USD` five-minute volume, and
  `ALPHA_MARKET_MIN_TRANSACTIONS_5M` five-minute transactions;
- an alert with the same transaction, wallet, and token has not already been
  stored.

The wallet threshold defaults to 65 and the early-token threshold to 45. The
local evidence minimums default to ten trades and five wallets. Market defaults
are $15,000 liquidity, $5,000 five-minute volume, and ten five-minute
transactions. Scores are calculated after the trade is persisted, so the signal
uses the latest available data. Tokens below these thresholds remain stored and
scored as watchlist candidates but do not produce Telegram noise. The
Telegram message includes both scores and grades, the evidence counts, observed
SOL and token amounts, current market evidence, a direct Dexscreener chart link,
and Solscan links for the token and transaction.
If at least two currently qualifying A/B wallets have observed buys in the same
token, the Telegram heading changes to `STRONG CONSENSUS` and the message shows
the top-trader count. A single qualifying top trader can still produce the
standard confirmed signal.

Before an alert is created, the collector asks the free Dexscreener token
endpoint for the highest-liquidity pair where the detected mint is the base
token and applies the market thresholds. The notifier reuses that response and multiplies
the observed token amount by that pair's current USD price and labels the result
as an estimate. This is not the historical execution price. When no indexed
pair or positive USD price is available, the message says the estimate is
unavailable instead of displaying `$0`.

This is a decision-support signal, not an automatic order or financial advice.
Public Solana RPC data can be delayed or incomplete, and the score covers only
activity observed by Alpha Engine. See
[`EARLY_TOKEN_SCORING.md`](EARLY_TOKEN_SCORING.md) for the methodology.
Historical candidate-wallet enrichment contributes to scores but cannot emit a
stale signal; the default signal freshness window is five minutes.

## Telegram configuration

Set these values only in the ignored `.env.local` file:

```dotenv
TELEGRAM_BOT_TOKEN=<bot token from BotFather>
TELEGRAM_CHAT_IDS=<first chat id>,<second chat id>
```

Recipients must have started a private chat with the bot before the bot can
message them. Restart the stack after changing the environment file.

Test delivery without generating a fake trading alert:

```powershell
docker compose --env-file .env.local -f docker-compose.local.yml run --rm worker python -m app.telegram_test
```

The command sends a connection confirmation only. `/start` messages are not
handled by Alpha Engine and do not trigger briefings.

The worker also sends operational messages to the same recipients:

- confirmation immediately after the active worker starts;
- a status heartbeat every `TELEGRAM_STATUS_INTERVAL_SECONDS` (30 minutes by
  default in local mode), including all-time database totals and unique
  transaction/token activity during `TELEGRAM_STATUS_WINDOW_MINUTES`;
- a warning when DEX discovery enters RPC backoff;
- a recovery message when the normal discovery schedule resumes;
- a message during a graceful worker shutdown.

Operational messages never represent a trading signal. Alpha signals retain
the `ALPHA SIGNAL — TOP TRADER BUY` heading.

## Monitored traders

Only wallets registered through `POST /api/v1/monitors` are scanned. An empty
monitor list produces no signals. Add reviewed trader addresses through the
local OpenAPI UI at `http://127.0.0.1:8000/docs`, then leave the worker running
for the desired observation window.
