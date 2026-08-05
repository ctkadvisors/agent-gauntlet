"""Gauntlet tasks on the Inspect AI chassis (P1 of the benchmark plan).

Same contract as the bare-python harness: fixture files land in a Docker
sandbox, an agent works with bash + editor tools, protected paths are
restored from the pristine fixture, and the executable acceptance command
decides — inside the sandbox — with no model grading.

Run (against any OpenAI-compatible endpoint):
  export LOCAL_BASE_URL=http://127.0.0.1:9090/v1 LOCAL_API_KEY=none
  inspect eval inspect/gauntlet_inspect.py --model openai-api/local/coder
MLflow reporting: pip install inspect-mlflow; export
  MLFLOW_TRACKING_URI=<your tracking server> MLFLOW_INSPECT_TRACING=true
"""

from __future__ import annotations

from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import CORRECT, INCORRECT, Score, accuracy, scorer
from inspect_ai.tool import bash, text_editor
from inspect_ai.util import sandbox

try:  # agent API moved across 2025-2026 releases
    from inspect_ai.agent import react as _agent_loop
except ImportError:  # pragma: no cover
    from inspect_ai.solver import basic_agent as _agent_loop  # type: ignore

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = str(Path(__file__).parent / "compose.yaml")


def _fixture_files(name: str) -> dict[str, str]:
    fixture = ROOT / "tasks" / name / "fixture"
    return {
        str(f.relative_to(fixture)): f.read_text(encoding="utf-8")
        for f in sorted(fixture.rglob("*")) if f.is_file()
    }


def _load_meta(name: str) -> dict:
    import sys
    sys.path.insert(0, str(ROOT))
    from harness.run import load_task
    return load_task(ROOT / "tasks" / name)


def _gauntlet_scorer(name: str):
    meta = _load_meta(name)
    files = _fixture_files(name)
    protected = meta.get("protected", "").split()

    @scorer(metrics=[accuracy()])
    def acceptance():
        async def score(state, target) -> Score:
            # Restore protected paths from the pristine fixture: the agent
            # never grades itself (same invariant as the bare harness).
            for rel, content in files.items():
                if any(rel == p or rel.startswith(p + "/") for p in protected):
                    await sandbox().write_file(rel, content)
            result = await sandbox().exec(
                ["bash", "-lc", meta["acceptance"]], timeout=300
            )
            return Score(
                value=CORRECT if result.returncode == 0 else INCORRECT,
                explanation=(result.stdout + result.stderr)[-500:],
            )
        return score

    return acceptance()


def _make_task(name: str) -> Task:
    meta = _load_meta(name)
    return Task(
        name=name,
        dataset=[Sample(input=meta["prompt"], files=_fixture_files(name))],
        solver=_agent_loop(tools=[bash(timeout=int(meta["timeout_s"])), text_editor()]),
        scorer=_gauntlet_scorer(name),
        message_limit=3 * int(meta["max_turns"]),
        sandbox=("docker", COMPOSE),
    )


@task
def fix_bug() -> Task:
    return _make_task("fix-bug")


@task
def add_feature() -> Task:
    return _make_task("add-feature")


@task
def cross_file_rename() -> Task:
    return _make_task("cross-file-rename")
