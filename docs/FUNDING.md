# Funding transfers

Alpha Engine records explicit native SOL transfers found in parsed Solana System
Program instructions. Both top-level instructions and CPI-generated inner
instructions are processed. Amounts are stored in SOL after conversion from
lamports.

The first version intentionally does not infer transfers from account balance
deltas. Balance changes also contain transaction fees, rent, rewards, and other
effects, so treating every delta as funding would create false relationships.

Each transfer is idempotent on `(signature, instruction_index)`. Replaying a
wallet page therefore does not duplicate funding history.

Use `GET /api/v1/funding/transfers` to browse transfers. Optional filters:

- `wallet_address`: include transfers involving this wallet
- `direction=incoming`: include only transfers received by the wallet
- `direction=outgoing`: include only transfers sent by the wallet

Direction only has meaning together with `wallet_address`; without a wallet the
endpoint returns all transfers.

Use `GET /api/v1/funding/wallets/{address}` for aggregate funding intelligence:
incoming and outgoing volume, net flow, unique funders and destinations, the
earliest observed funder, and the largest directional counterparty
relationships. `counterparty_limit` controls the returned relationship count.
