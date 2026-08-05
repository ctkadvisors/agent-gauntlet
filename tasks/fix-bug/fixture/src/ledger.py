"""Tiny double-entry ledger."""


class Ledger:
    def __init__(self):
        self.entries = []

    def post(self, account: str, amount: int) -> None:
        self.entries.append((account, amount))

    def balance(self, account: str) -> int:
        return sum(amt for acct, amt in self.entries if acct == account)

    def trial_balance(self) -> int:
        """Sum of all postings; zero when books are balanced."""
        return sum(amt for _, amt in self.entries)

    def transfer(self, src: str, dst: str, amount: int) -> None:
        self.post(src, -amount)
        self.post(dst, -amount)
