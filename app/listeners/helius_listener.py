from app.core.event_bus import EventBus
from app.core.events import TokenCreated
from app.listeners.helius_client import HeliusClient


class HeliusListener:
    """
    Listens for Solana blockchain events.

    Detects token candidates and extracts metadata.
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

            transaction_response = await self.client.get_transaction(
                signature
            )

            transaction = transaction_response.get(
                "result"
            )

            if not transaction:
                continue

            tokens = self.extract_tokens(
                transaction
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
                    transaction
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
        """
        Fetch token metadata.
        """

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
        Extract token mint addresses.
        """

        meta = transaction.get(
            "meta",
            {},
        )

        pre = set()

        for item in meta.get(
            "preTokenBalances",
            [],
        ):
            mint = item.get(
                "mint"
            )

            if mint:
                pre.add(
                    mint
                )

        post = set()

        for item in meta.get(
            "postTokenBalances",
            [],
        ):
            mint = item.get(
                "mint"
            )

            if mint:
                post.add(
                    mint
                )

        return list(
            post - pre
        )

    def extract_creator(
        self,
        transaction: dict,
    ) -> str:
        """
        Extract creator wallet from transaction.
        """

        message = (
            transaction
            .get("transaction", {})
            .get("message", {})
        )

        account_keys = (
            message
            .get("accountKeys", [])
        )

        print(
            "ACCOUNT KEYS:",
            account_keys[:5],
        )

        for account in account_keys:

            if isinstance(
                account,
                dict,
            ):

                pubkey = account.get(
                    "pubkey"
                )

                if account.get(
                    "signer"
                ):
                    return pubkey or "unknown"

            elif isinstance(
                account,
                str,
            ):
                return account

        loaded_addresses = (
            transaction
            .get("meta", {})
            .get("loadedAddresses", {})
        )

        writable = loaded_addresses.get(
            "writable",
            [],
        )

        if writable:
            return writable[0]

        readonly = loaded_addresses.get(
            "readonly",
            [],
        )

        if readonly:
            return readonly[0]

        return "unknown"
