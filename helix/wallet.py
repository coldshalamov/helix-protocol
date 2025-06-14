class Wallet:
    """Simple HLX wallet for tests."""

    def __init__(self, balance: int = 0) -> None:
        if balance < 0:
            raise ValueError("balance must be non-negative")
        self._balance = balance

    @property
    def balance(self) -> int:
        return self._balance

    def deposit(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        self._balance += amount

    def withdraw(self, amount: int) -> None:
        if amount < 0:
            raise ValueError("amount must be non-negative")
        if amount > self._balance:
            raise ValueError("insufficient funds")
        self._balance -= amount

__all__ = ["Wallet"]

