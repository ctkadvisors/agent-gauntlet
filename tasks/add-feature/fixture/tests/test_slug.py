import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from slug import slugify


def test_basic():
    assert slugify("Hello, World!") == "hello-world"

def test_runs_collapse():
    assert slugify("a  --  b") == "a-b"

def test_edges():
    assert slugify("--Trim Me--") == "trim-me"
    assert slugify("") == "untitled"
    assert slugify("!!!") == "untitled"
