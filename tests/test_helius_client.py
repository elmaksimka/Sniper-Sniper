from typing import Any

import pytest

from app.listeners.helius_client import HeliusClient


class StubHeliusClient(HeliusClient):
    def __init__(self, response: dict[str, Any]) -> None:
        super().__init__()
        self.response = response
        self.method = ""
        self.params: list[Any] | dict[str, Any] | None = None

    async def _request(
        self,
        method: str,
        params: list[Any] | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.method = method
        self.params = params
        return self.response


@pytest.mark.asyncio
async def test_get_transactions_for_address_builds_current_rpc_request() -> None:
    client = StubHeliusClient(
        {
            "result": {
                "data": [{"slot": 1, "transaction": {}, "meta": {}}],
                "paginationToken": "slot:position",
            }
        }
    )

    page = await client.get_transactions_for_address(
        "wallet",
        limit=500,
        pagination_token="previous",
    )

    assert client.method == "getTransactionsForAddress"
    assert isinstance(client.params, list)
    assert client.params[0] == "wallet"
    config = client.params[1]
    assert config["transactionDetails"] == "full"
    assert config["limit"] == 100
    assert config["paginationToken"] == "previous"
    assert config["filters"] == {
        "status": "succeeded",
        "tokenAccounts": "balanceChanged",
    }
    assert len(page.transactions) == 1
    assert page.pagination_token == "slot:position"


@pytest.mark.asyncio
async def test_get_transactions_for_address_handles_rpc_error_shape() -> None:
    client = StubHeliusClient({"error": {"message": "rate limited"}})

    page = await client.get_transactions_for_address("wallet")

    assert page.transactions == []
    assert page.pagination_token is None
