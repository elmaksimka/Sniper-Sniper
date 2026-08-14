from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6


@dataclass(frozen=True, slots=True)
class SwapRouteQuote:
    input_mint: str
    output_mint: str
    input_amount: float
    output_amount: float
    price_impact_pct: float
    fee_bps: int
    router: str
    route: str


class JupiterQuoteClient:
    """Fetch executable-size paper quotes from Jupiter's swap router."""

    ORDER_URL = "https://api.jup.ag/swap/v2/order"

    def __init__(
        self,
        http_client: httpx.AsyncClient | None = None,
        *,
        api_key: str = "",
        timeout_seconds: float = 10,
    ) -> None:
        self._client = http_client
        self._api_key = api_key.strip()
        self._timeout_seconds = timeout_seconds

    async def get_buy_quote(
        self,
        token_address: str,
        usd_amount: float,
        token_decimals: int,
    ) -> SwapRouteQuote | None:
        raw_amount = self._raw_amount(usd_amount, USDC_DECIMALS)
        return await self._quote(
            input_mint=USDC_MINT,
            output_mint=token_address,
            raw_amount=raw_amount,
            input_decimals=USDC_DECIMALS,
            output_decimals=token_decimals,
        )

    async def get_sell_quote(
        self,
        token_address: str,
        token_amount: float,
        token_decimals: int,
    ) -> SwapRouteQuote | None:
        raw_amount = self._raw_amount(token_amount, token_decimals)
        return await self._quote(
            input_mint=token_address,
            output_mint=USDC_MINT,
            raw_amount=raw_amount,
            input_decimals=token_decimals,
            output_decimals=USDC_DECIMALS,
        )

    async def _quote(
        self,
        *,
        input_mint: str,
        output_mint: str,
        raw_amount: int,
        input_decimals: int,
        output_decimals: int,
    ) -> SwapRouteQuote | None:
        if raw_amount <= 0:
            return None
        payload = await self._get_json(
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(raw_amount),
            }
        )
        if not isinstance(payload, dict):
            return None
        try:
            in_amount = int(str(payload["inAmount"]))
            out_amount = int(str(payload["outAmount"]))
        except (KeyError, TypeError, ValueError):
            return None
        if in_amount <= 0 or out_amount <= 0:
            return None

        route_labels: list[str] = []
        route_plan = payload.get("routePlan")
        if isinstance(route_plan, list):
            for leg in route_plan:
                if not isinstance(leg, dict):
                    continue
                swap_info = leg.get("swapInfo")
                label = swap_info.get("label") if isinstance(swap_info, dict) else None
                if isinstance(label, str) and label and label not in route_labels:
                    route_labels.append(label)

        return SwapRouteQuote(
            input_mint=input_mint,
            output_mint=output_mint,
            input_amount=in_amount / 10**input_decimals,
            output_amount=out_amount / 10**output_decimals,
            price_impact_pct=self._price_impact_pct(payload),
            fee_bps=self._nonnegative_int(payload.get("feeBps")),
            router=str(payload.get("router") or ""),
            route=" -> ".join(route_labels),
        )

    async def _get_json(self, *, params: dict[str, str]) -> Any:
        headers = {"x-api-key": self._api_key} if self._api_key else {}
        if self._client is not None:
            response = await self._client.get(
                self.ORDER_URL,
                params=params,
                headers=headers,
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.get(
                    self.ORDER_URL,
                    params=params,
                    headers=headers,
                )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _raw_amount(amount: float, decimals: int) -> int:
        return max(0, int(amount * 10**decimals))

    @staticmethod
    def _price_impact_pct(payload: dict[str, Any]) -> float:
        direct = JupiterQuoteClient._nonnegative_float(payload.get("priceImpact"))
        if direct is not None:
            return direct
        fraction = JupiterQuoteClient._nonnegative_float(
            payload.get("priceImpactPct")
        )
        return (fraction or 0.0) * 100

    @staticmethod
    def _nonnegative_float(value: Any) -> float | None:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    @staticmethod
    def _nonnegative_int(value: Any) -> int:
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0
