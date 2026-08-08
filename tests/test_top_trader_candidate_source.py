import pytest

from app.services.dexscreener_client import DexScreenerTopTrader, TrendingToken
from app.services.top_trader_candidate_source import TopTraderCandidateSource


class FakeDexScreener:
    def __init__(self) -> None:
        self.pairs: list[str] = []

    async def get_solana_trending_h24(self) -> list[TrendingToken]:
        return [
            TrendingToken("pair-strong", "strong"),
            TrendingToken("pair-weak", "weak"),
        ]

    async def get_pair_top_traders(
        self,
        pair: str,
        *,
        limit: int,
    ) -> list[DexScreenerTopTrader]:
        self.pairs.append(pair)
        return [
            DexScreenerTopTrader(
                wallet="profitable",
                buy_volume_usd=1_000,
                sell_volume_usd=6_000,
                buys=1,
                sells=1,
            ),
            DexScreenerTopTrader(
                wallet="risky",
                buy_volume_usd=1_000,
                sell_volume_usd=11_000,
                buys=1,
                sells=1,
            ),
        ]


@pytest.mark.asyncio
async def test_source_preserves_dex_token_and_trader_order() -> None:
    dexscreener = FakeDexScreener()
    source = TopTraderCandidateSource(
        dexscreener,  # type: ignore[arg-type]
        token_limit=1,
    )

    result = await source.discover()

    assert dexscreener.pairs == ["pair-strong"]
    assert result.token_count == 1
    assert result.token_addresses == ("strong",)
    assert [item.address for item in result.candidates] == [
        "profitable",
        "risky",
    ]
    assert all(not item.risk_tags for item in result.candidates)


@pytest.mark.asyncio
async def test_source_skips_tokens_already_processed_by_the_cursor() -> None:
    dexscreener = FakeDexScreener()
    source = TopTraderCandidateSource(
        dexscreener,  # type: ignore[arg-type]
        token_limit=1,
        excluded_token_addresses=("strong",),
    )

    result = await source.discover()

    assert dexscreener.pairs == ["pair-weak"]
    assert result.token_addresses == ("weak",)
