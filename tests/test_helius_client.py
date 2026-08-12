import asyncio
from typing import Any

import httpx
import pytest

from app.listeners.helius_client import HeliusClient, HeliusRPCError


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
    assert "filters" not in config
    assert len(page.transactions) == 1
    assert page.pagination_token == "slot:position"


@pytest.mark.asyncio
async def test_get_transactions_for_address_handles_rpc_error_shape() -> None:
    client = StubHeliusClient({"error": {"message": "rate limited"}})

    page = await client.get_transactions_for_address("wallet")

    assert page.transactions == []
    assert page.pagination_token is None


@pytest.mark.asyncio
async def test_count_transactions_for_address_counts_complete_signature_page() -> None:
    client = StubHeliusClient(
        {
            "result": [
                {"signature": "one"},
                {"signature": "two"},
            ]
        }
    )

    total = await client.count_transactions_for_address("wallet")

    assert total == 2
    assert client.method == "getSignaturesForAddress"
    assert client.params == [
        "wallet",
        {"limit": 1_000, "commitment": "finalized"},
    ]


@pytest.mark.asyncio
async def test_standard_history_uses_public_solana_rpc_methods() -> None:
    calls: list[tuple[str, list[Any] | dict[str, Any] | None]] = []

    class StandardClient(HeliusClient):
        async def _request(
            self,
            method: str,
            params: list[Any] | dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            calls.append((method, params))
            if method == "getSignaturesForAddress":
                return {
                    "result": [
                        {"signature": "sig-ok", "err": None},
                        {"signature": "sig-failed", "err": {"code": 1}},
                    ]
                }
            return {
                "result": {
                    "blockTime": 1_700_000_000,
                    "transaction": {"signatures": ["sig-ok"]},
                    "meta": {"err": None},
                }
            }

    client = StandardClient()
    client.transaction_history_mode = "standard"
    page = await client.get_transactions_for_address(
        "wallet",
        limit=2,
        pagination_token="before-signature",
    )

    assert [call[0] for call in calls] == [
        "getSignaturesForAddress",
        "getTransaction",
    ]
    signature_params = calls[0][1]
    assert isinstance(signature_params, list)
    assert signature_params == [
        "wallet",
        {
            "limit": 2,
            "commitment": "finalized",
            "before": "before-signature",
        },
    ]
    assert len(page.transactions) == 1
    assert page.pagination_token == "sig-failed"


@pytest.mark.asyncio
async def test_standard_history_fetches_transaction_details_sequentially() -> None:
    active = 0
    peak = 0

    class StandardClient(HeliusClient):
        async def _request(
            self,
            method: str,
            params: list[Any] | dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            nonlocal active, peak
            if method == "getSignaturesForAddress":
                return {
                    "result": [
                        {"signature": f"sig-{index}", "err": None}
                        for index in range(3)
                    ]
                }
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0)
            active -= 1
            return {"result": {"transaction": {}, "meta": {}}}

    client = StandardClient()
    client.transaction_history_mode = "standard"

    page = await client.get_transactions_for_address("wallet", limit=3)

    assert len(page.transactions) == 3
    assert peak == 1


@pytest.mark.asyncio
async def test_standard_history_skips_helius_only_metadata() -> None:
    client = StubHeliusClient({"result": {"name": "should-not-be-used"}})
    client.transaction_history_mode = "standard"

    assert await client.get_asset("mint") == {"result": None}
    assert client.method == ""


@pytest.mark.asyncio
async def test_request_retries_rate_limit_using_retry_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0.25"},
                request=request,
            )
        return httpx.Response(200, json={"result": "ok"}, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.listeners.helius_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test"
        client.max_retries = 1

        response = await client.get_health()

    assert response == {"result": "ok"}
    assert calls == 2
    assert delays == [0.25]


@pytest.mark.asyncio
async def test_request_redacts_rpc_url_after_final_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test/?api-key=secret"
        client.max_retries = 0

        with pytest.raises(HeliusRPCError, match="^Helius HTTP 429$") as raised:
            await client.get_health()

    assert "secret" not in str(raised.value)


@pytest.mark.asyncio
async def test_request_applies_configured_global_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    delays: list[float] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": "ok"}, request=request)

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr("app.listeners.helius_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test"
        client.request_delay = 0.5

        assert await client.get_health() == {"result": "ok"}

    assert delays == [0.5]


@pytest.mark.asyncio
async def test_request_retries_transient_rpc_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                200,
                json={"error": {"code": -32005, "message": "rate limited"}},
                request=request,
            )
        return httpx.Response(200, json={"result": []}, request=request)

    async def fake_sleep(delay: float) -> None:
        return None

    monkeypatch.setattr("app.listeners.helius_client.asyncio.sleep", fake_sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test"
        client.max_retries = 1

        response = await client.get_signatures("wallet")

    assert response == {"result": []}
    assert calls == 2


@pytest.mark.asyncio
async def test_request_raises_non_retryable_rpc_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"error": {"code": -32602, "message": "invalid params"}},
            request=request,
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test"

        with pytest.raises(HeliusRPCError, match="invalid params"):
            await client.get_health()


@pytest.mark.asyncio
async def test_request_limits_concurrency() -> None:
    active = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json={"result": "ok"}, request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = HeliusClient(http_client=http)
        client.rpc_url = "https://rpc.test"
        client._semaphore = asyncio.Semaphore(2)

        await asyncio.gather(*(client.get_health() for _ in range(6)))

    assert peak == 2
