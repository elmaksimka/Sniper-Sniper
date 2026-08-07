BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_VALUES = {character: index for index, character in enumerate(BASE58_ALPHABET)}


def is_solana_address(value: str) -> bool:
    """Return whether a base58 string decodes to a 32-byte Solana public key."""
    if not 32 <= len(value) <= 44:
        return False

    number = 0
    for character in value:
        digit = BASE58_VALUES.get(character)
        if digit is None:
            return False
        number = number * 58 + digit

    leading_zero_bytes = len(value) - len(value.lstrip("1"))
    encoded_bytes = (number.bit_length() + 7) // 8
    return leading_zero_bytes + encoded_bytes == 32


def validate_solana_address(value: str) -> str:
    if not is_solana_address(value):
        raise ValueError("Invalid Solana address")
    return value
