from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.helius_client import HeliusClient


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Detects new tokens and extracts creator wallet.
    """

    def __init__(
        self,
        event_bus: EventBus,
        client: HeliusClient,
    ):
        self.event_bus = event_bus
        self.client = client

    async def start(self) -> None:
        """
        Start listening.
        """

        print(
            "Starting token detection..."
        )

        signatures_response = await self.client.get_signatures(
            address="11111111111111111111111111111111",
            limit=10,
        )

        signatures = (
            signatures_response
            .get("result", [])
        )

        for item in signatures:

            signature = item.get(
                "signature"
            )

            if not signature:
                continue

            transaction = await self.client.get_transaction(
                signature
            )

            result = transaction.get(
                "result"
            )

            if not result:
                continue

            tokens = self.extract_tokens(
                result
            )

            for token_address in tokens:

                metadata = await self.get_metadata(
                    token_address
                )

                symbol = metadata.get(
                    "symbol"
                )

                name = metadata.get(
                    "name"
                )

                creator = self.extract_creator(
                    result
                )

                print(
                    "New token detected:",
                    token_address,
                    symbol,
                    name,
                    "creator:",
                    creator,
                )

                await self.event_bus.publish(
                    TokenCreated(
                        token_address=token_address,
                        creator=creator,
                        symbol=symbol,
                        name=name,
                    )
                )

    async def get_metadata(
        self,
        address: str,
    ) -> dict:

        response = await self.client.get_asset(
            address
        )

        result = response.get(
            "result",
            {},
        )

        metadata = (
            result
            .get("content", {})
            .get("metadata", {})
        )

        return {
            "symbol": metadata.get(
                "symbol"
            ),
            "name": metadata.get(
                "name"
            ),
        }

    def extract_tokens(
        self,
        transaction: dict,
    ) -> list[str]:
        """
        Extract token mint addresses
        from transaction.
        """

        tokens = set()

        meta = transaction.get(
            "meta",
            {},
        )

        pre = meta.get(
            "preTokenBalances",
            []
        )

        post = meta.get(
            "postTokenBalances",
            []
        )

        for balance in pre + post:

            mint = balance.get(
                "mint"
            )

            if mint:
                tokens.add(
                    mint
                )

        return list(tokens)

    def extract_creator(
        self,
        transaction: dict,
    ) -> str:
        """
        Extract first signer wallet.
        """

        message = (
            transaction
            .get("transaction", {})
            .get("message", {})
        )

        accounts = message.get(
            "accountKeys",
            []
        )

        for account in accounts:

            if isinstance(account, dict):

                if account.get(
                    "signer"
                ):
                    return account.get(
                        "pubkey"
                    )

            elif isinstance(account, str):

                return account

        return "unknown"