import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.analyzer import TokenAnalyzer
from app.listeners.helius_client import HeliusClient
from app.listeners.transaction_scanner import TransactionScanner
from app.services.token_parser import TokenParser


FIXTURES = Path(__file__).parent / "fixtures" / "helius"


def load_fixture(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        value: dict[str, Any] = json.load(fixture)
        return value


@pytest.mark.asyncio
async def test_recorded_rpc_pages_flow_through_client_and_scanner() -> None:
    requested_tokens: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        config = payload["params"][1]
        token = config.get("paginationToken")
        requested_tokens.append(token)
        fixture = (
            "transactions_page_2.json"
            if token == "page-2"
            else "transactions_page_1.json"
        )
        return httpx.Response(200, json=load_fixture(fixture), request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test"
        scanner = TransactionScanner(client, TokenParser(), TokenAnalyzer())

        batch = await scanner.scan_since(
            "wallet",
            checkpoint_signature="sig-1",
            page_size=2,
            max_pages=2,
        )

    assert requested_tokens == [None, "page-2"]
    assert batch.complete is True
    assert batch.newest_signature == "sig-3"
    assert [transaction["signature"] for transaction in batch.transactions] == [
        "sig-2",
        "sig-3",
    ]
    assert batch.transactions[0]["trades"][0].side == "sell"
    assert batch.transactions[1]["trades"][0].side == "buy"
