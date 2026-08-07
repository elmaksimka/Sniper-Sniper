from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.core.events import ScoreUpdated, TradeScored
from app.infrastructure.models import Alert
from app.services.alert_service import AlertService


class CapturingRepository:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    async def create_if_absent(self, values: dict[str, object]) -> Alert:
        self.values = values
        return Alert(
            entity_type=str(values["entity_type"]),
            entity_address=str(values["entity_address"]),
            alert_type=str(values["alert_type"]),
            severity=str(values["severity"]),
            message=str(values["message"]),
            details=cast(dict[str, object], values["details"]),
            dedupe_key=str(values["dedupe_key"]),
        )


@pytest.mark.asyncio
async def test_grade_a_alert_has_stable_key_and_critical_severity() -> None:
    session: Any = None
    service = AlertService(session)
    repository = CapturingRepository()
    service_with_fake: Any = service
    service_with_fake.repository = repository

    alert = await service.create_score_alert(
        ScoreUpdated(
            entity_type="wallet",
            entity="wallet",
            score=88.5,
            grade="A",
            methodology_version="wallet-v1",
        )
    )

    assert alert is not None
    assert repository.values["severity"] == "critical"
    assert repository.values["dedupe_key"] == (
        "wallet-score:wallet:wallet-v1:A"
    )
    assert repository.values["details"] == {
        "score": 88.5,
        "grade": "A",
        "methodology_version": "wallet-v1",
    }


@pytest.mark.asyncio
async def test_token_alert_has_typed_key_and_message() -> None:
    service = AlertService(None)  # type: ignore[arg-type]
    repository = CapturingRepository()
    service_with_fake: Any = service
    service_with_fake.repository = repository

    alert = await service.create_score_alert(
        ScoreUpdated(
            entity_type="token",
            entity="mint",
            score=72,
            grade="B",
            methodology_version="token-v1",
        )
    )

    assert alert is not None
    assert repository.values["entity_type"] == "token"
    assert repository.values["alert_type"] == "token_score_grade"
    assert repository.values["dedupe_key"] == "token-score:mint:token-v1:B"
    assert str(repository.values["message"]).startswith("Token mint reached")


@pytest.mark.asyncio
async def test_alpha_signal_has_transaction_scoped_dedupe_key() -> None:
    service = AlertService(None)  # type: ignore[arg-type]
    repository = CapturingRepository()
    service_with_fake: Any = service
    service_with_fake.repository = repository

    alert = await service.create_alpha_signal(
        TradeScored(
            token_address="mint",
            wallet="wallet",
            side="buy",
            amount=1200,
            sol_change=-3.5,
            signature="signature",
        ),
        SimpleNamespace(score=85, grade="A"),  # type: ignore[arg-type]
        SimpleNamespace(  # type: ignore[arg-type]
            score=82,
            grade="A",
            methodology_version="early-token-v1",
            observed_trade_count=4,
            observed_wallet_count=3,
        ),
    )

    assert alert is not None
    assert repository.values["alert_type"] == "top_trader_token_buy"
    assert repository.values["severity"] == "critical"
    assert repository.values["dedupe_key"] == (
        "alpha-buy:signature:wallet:mint"
    )
    assert repository.values["details"] == {
        "wallet": "wallet",
        "wallet_score": 85,
        "wallet_grade": "A",
        "token_score": 82,
        "token_grade": "A",
        "token_score_methodology": "early-token-v1",
        "observed_trade_count": 4,
        "observed_wallet_count": 3,
        "token_amount": 1200,
        "sol_amount": 3.5,
        "signature": "signature",
        "observed_top_trader_count": 1,
    }
