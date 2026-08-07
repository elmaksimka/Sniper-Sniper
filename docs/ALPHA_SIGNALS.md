# Top-trader token-buy signals

Alpha Engine sends a Telegram alpha signal only after a normalized `buy` trade
meets all of these conditions:

- the transaction has a signature;
- the wallet score is at least `ALPHA_WALLET_SCORE_THRESHOLD`;
- the early-token score is at least `ALPHA_EARLY_TOKEN_SCORE_THRESHOLD`;
- the wallet has grade A or B;
- the token has at least `ALPHA_EARLY_TOKEN_MIN_TRADES` observed trades and
  `ALPHA_EARLY_TOKEN_MIN_WALLETS` independent observed wallets;
- an alert with the same transaction, wallet, and token has not already been
  stored.

The wallet threshold defaults to 65 and the early-token threshold to 45. The
evidence minimums default to three trades and two wallets. Scores are calculated
after the trade is persisted, so the signal uses the latest available data. The
Telegram message includes both scores and grades, the evidence counts, observed
SOL and token amounts, and Solscan links for the token and transaction.

This is a decision-support signal, not an automatic order or financial advice.
Public Solana RPC data can be delayed or incomplete, and the score covers only
activity observed by Alpha Engine. See
[`EARLY_TOKEN_SCORING.md`](EARLY_TOKEN_SCORING.md) for the methodology.

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
  default in local mode);
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
