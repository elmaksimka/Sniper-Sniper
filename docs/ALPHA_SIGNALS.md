# Top-trader token-buy signals

Alpha Engine sends a Telegram alpha signal only after a normalized `buy` trade
meets all of these conditions:

- the transaction has a signature;
- the wallet score is at least `ALPHA_WALLET_SCORE_THRESHOLD`;
- the token score is at least `ALPHA_TOKEN_SCORE_THRESHOLD`;
- both the wallet and token have grade A or B;
- an alert with the same transaction, wallet, and token has not already been
  stored.

Both thresholds default to 65. Scores are recalculated after the trade is
persisted, so the signal uses the latest available wallet and token snapshots.
The Telegram message includes both scores and grades, the observed SOL and token
amounts, and Solscan links for the token and transaction.

This is a decision-support signal, not an automatic order or financial advice.
Public Solana RPC data can be delayed or incomplete, and the token score covers
only activity observed by Alpha Engine.

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

## Monitored traders

Only wallets registered through `POST /api/v1/monitors` are scanned. An empty
monitor list produces no signals. Add reviewed trader addresses through the
local OpenAPI UI at `http://127.0.0.1:8000/docs`, then leave the worker running
for the desired observation window.
