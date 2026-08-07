import pytest

from app.core.solana import is_solana_address, validate_solana_address


@pytest.mark.parametrize(
    "address",
    [
        "11111111111111111111111111111111",
        "AUaPMKd13d633cXRRrPRfTeL5XRN64ngDWLEfH5zfBML",
    ],
)
def test_accepts_32_byte_base58_public_keys(address: str) -> None:
    assert is_solana_address(address) is True
    assert validate_solana_address(address) == address


@pytest.mark.parametrize(
    "address",
    [
        "staging-probe",
        "0OIl" * 10,
        "1" * 31,
        "1" * 33,
        "",
    ],
)
def test_rejects_invalid_solana_addresses(address: str) -> None:
    assert is_solana_address(address) is False
    with pytest.raises(ValueError, match="Invalid Solana address"):
        validate_solana_address(address)
