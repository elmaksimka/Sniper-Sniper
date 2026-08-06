class TokenStore:

    def __init__(self) -> None:
        self._tokens: set[str] = set()

    def exists(
        self,
        mint: str,
    ) -> bool:
        return mint in self._tokens

    def add(
        self,
        mint: str,
    ) -> None:
        self._tokens.add(mint)
