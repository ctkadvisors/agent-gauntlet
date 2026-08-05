import pathlib, subprocess, sys

files = ["app/core.py", "app/cli.py", "app/report.py"]
blob = {f: pathlib.Path(f).read_text() for f in files}
assert not any("do_it" in b for b in blob.values()), "old name still present"
assert all("generate_report" in b for b in blob.values()), "new name missing somewhere"
out = subprocess.run([sys.executable, "-m", "app.cli"], capture_output=True, text=True)
assert out.returncode == 0 and "'count': 2" in out.stdout and "'total': 7" in out.stdout, out.stdout + out.stderr
sys.path.insert(0, ".")
from app.report import weekly
assert weekly([{"amount": 1}]) == "1 rows, total 1"
print("OK")
