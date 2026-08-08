import pytest

from app.services.birdeye_client import TokenTopTrader
from app.services.dexscreener_client import TrendingToken
from app.services.top_trader_candidate_source import TopTraderCandidateSource


class FakeDexScreener:
    async def get_solana_trending_h24(self) -> list[TrendingToken]:
        return [
            TrendingToken("pair-strong", "strong"),
            TrendingToken("pair-weak", "weak"),
        ]


class FakeBirdeye:
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def get_top_traders(
        self,
        token: str,
        *,
        limit: int,
    ) -> list[TokenTopTrader]:
        self.tokens.append(token)
        return [
            TokenTopTrader(
                wallet="profitable",
                token_address=token,
                realized_pnl_usd=5_000,
                total_pnl_usd=5_000,
                buy_volume_usd=1_000,
                sell_volume_usd=6_000,
                tags=("smart_trader",),
            ),
            TokenTopTrader(
                wallet="risky",
                token_address=token,
                realized_pnl_usd=10_000,
                total_pnl_usd=10_000,
                buy_volume_usd=1_000,
                sell_volume_usd=11_000,
                tags=("dev", "bundler"),
            ),
        ]


@pytest.mark.asyncio
async def test_source_ranks_dex_tokens_and_prioritizes_safe_wallets() -> None:
    birdeye = FakeBirdeye()
    source = TopTraderCandidateSource(
        FakeDexScreener(),  # type: ignore[arg-type]
        birdeye,  # type: ignore[arg-type]
        token_limit=1,
    )

    result = await source.discover()

    assert birdeye.tokens == ["strong"]
    assert result.token_count == 1
    assert result.token_addresses == ("strong",)
    assert [item.address for item in result.candidates] == [
        "profitable",
        "risky",
    ]
    assert result.candidates[1].risk_tags == ("bundler", "dev")


@pytest.mark.asyncio
async def test_source_skips_tokens_already_processed_by_the_cursor() -> None:
    birdeye = FakeBirdeye()
    source = TopTraderCandidateSource(
        FakeDexScreener(),  # type: ignore[arg-type]
        birdeye,  # type: ignore[arg-type]
        token_limit=1,
        excluded_token_addresses=("strong",),
    )

    result = await source.discover()

    assert birdeye.tokens == ["weak"]
    assert result.token_addresses == ("weak",)
