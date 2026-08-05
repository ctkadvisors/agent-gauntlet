import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from ledger import Ledger


def test_transfer_balances():
    l = Ledger()
    l.transfer("cash", "savings", 100)
    assert l.balance("cash") == -100
    assert l.balance("savings") == 100
    assert l.trial_balance() == 0
