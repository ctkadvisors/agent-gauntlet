"""Run every task in tasks/ against a model endpoint; emit a verdict.

Usage:
  python -m harness.run --endpoint http://localhost:9090 --model coder \
      [--out results/<model>.json] [--tasks fix-bug add-feature]

Each task directory contains:
  task.yaml   {prompt: str, acceptance: str, timeout_s: int, max_turns: int}
  fixture/    files copied into a fresh workspace per run

The acceptance command runs AFTER the agent finishes, in the workspace,
with the fixture's tests restored from the pristine copy first — an agent
that "passes" by editing the tests fails the gate (same lesson as the
tolkien evals: never let the subject grade itself).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from harness.agent import Agent

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT_LIMIT = 400_000


def load_task(path: Path) -> dict:
    # minimal YAML subset: "key: value" lines + "|" block for prompt
    text = (path / "task.yaml").read_text(encoding="utf-8")
    task: dict = {}
    key, block = None, []
    for line in text.splitlines():
        if key is not None:
            if line.startswith("  "):
                block.append(line[2:])
                continue
            task[key] = "\n".join(block)
            key, block = None, []
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        k, _, v = line.partition(":")
        if v.strip() == "|":
            key, block = k.strip(), []
        else:
            task[k.strip()] = v.strip()
    if key is not None:
        task[key] = "\n".join(block)
    task["timeout_s"] = int(task.get("timeout_s", 120))
    task["max_turns"] = int(task.get("max_turns", 25))
    return task


def restore_protected(fixture: Path, workspace: Path, protected: str) -> None:
    for rel in protected.split():
        src, dst = fixture / rel, workspace / rel
        if src.is_dir():
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(src, dst)
        elif src.exists():
            shutil.copy2(src, dst)


def transcript_json(transcript: list[dict]) -> str:
    serialized = json.dumps(transcript, indent=2)
    if len(serialized) <= TRANSCRIPT_LIMIT:
        return serialized

    marker = {"truncated": True, "original_characters": len(serialized),
              "json_prefix": ""}
    low, high = 0, len(serialized)
    while low < high:
        middle = (low + high + 1) // 2
        marker["json_prefix"] = serialized[:middle]
        candidate = json.dumps([marker], indent=2)
        if len(candidate) <= TRANSCRIPT_LIMIT:
            low = middle
        else:
            high = middle - 1
    marker["json_prefix"] = serialized[:low]
    return json.dumps([marker], indent=2)


def run_task(task_dir: Path, endpoint: str, model: str,
             temperature: float = 0.2, max_tokens: int = 2048,
             request_options: dict | None = None,
             provenance: dict | None = None) -> dict:
    task = load_task(task_dir)
    workspace = Path(tempfile.mkdtemp(prefix=f"gauntlet-{task_dir.name}-"))
    shutil.copytree(task_dir / "fixture", workspace, dirs_exist_ok=True)
    request_options = request_options if request_options is not None else {}
    provenance = provenance if provenance is not None else {}
    effective_temperature = request_options.get("temperature", temperature)
    effective_max_tokens = request_options.get("max_tokens", max_tokens)
    agent = None
    stats = {}
    infra_errors = []
    try:
        agent = Agent(endpoint, model, workspace,
                      max_turns=task["max_turns"], timeout_s=task["timeout_s"],
                      temperature=temperature, max_tokens=max_tokens,
                      request_options=request_options)
        stats = agent.run(task["prompt"])
    except Exception as exc:  # endpoint/harness failure is a result, not a crash
        infra_errors.append(f"{type(exc).__name__}: {exc}"[:300])
        stats = {
            "turns": getattr(agent, "turns", 0),
            "seconds": getattr(agent, "seconds", 0.0),
            "tokens_prompt": getattr(agent, "tokens_prompt", 0),
            "tokens_completion": getattr(agent, "tokens_completion", 0),
            "tokens_reasoning": getattr(agent, "tokens_reasoning", None),
            "termination_reason": "infra_error",
            "protocol_error": None,
            "temperature": effective_temperature,
            "max_tokens": effective_max_tokens,
        }

    try:
        restore_protected(task_dir / "fixture", workspace, task.get("protected", ""))
    except Exception as exc:
        infra_errors.append(f"protected-path restoration: {type(exc).__name__}: {exc}"[:300])

    acceptance_status = "error"
    acceptance_error = None
    acceptance_tail = ""
    passed = False
    try:
        proc = subprocess.run(task["acceptance"], shell=True, cwd=workspace,
                              capture_output=True, text=True, timeout=300)
        passed = proc.returncode == 0
        acceptance_status = "passed" if passed else "failed"
        acceptance_tail = (proc.stdout + proc.stderr)[-400:]
    except subprocess.TimeoutExpired as exc:
        acceptance_status = "timeout"
        acceptance_error = f"acceptance timed out after {exc.timeout}s"
    except Exception as exc:
        acceptance_error = f"{type(exc).__name__}: {exc}"[:300]

    try:
        (workspace / "gauntlet-transcript.json").write_text(
            transcript_json(agent.transcript if agent is not None else []),
            encoding="utf-8",
        )
    except Exception as exc:
        infra_errors.append(f"transcript persistence: {type(exc).__name__}: {exc}"[:300])

    return {
        "task": task_dir.name,
        "passed": passed,
        **stats,
        "infra_status": "error" if infra_errors else "ok",
        "infra_error": "; ".join(infra_errors) if infra_errors else None,
        "acceptance_status": acceptance_status,
        "acceptance_error": acceptance_error,
        "acceptance_tail": acceptance_tail,
        "request_options": request_options,
        "provenance": provenance,
        "workspace": str(workspace),
    }


def json_dict(value: str) -> dict:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("value must be a JSON object")
    return parsed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tasks", nargs="*", default=None)
    parser.add_argument("--out", default=None)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--request-options", type=json_dict, default={})
    parser.add_argument("--provenance", type=json_dict, default={})
    args = parser.parse_args()

    task_dirs = sorted(d for d in (ROOT / "tasks").iterdir() if (d / "task.yaml").exists())
    if args.tasks:
        task_dirs = [d for d in task_dirs if d.name in args.tasks]

    results = []
    for d in task_dirs:
        print(f"[gauntlet] {args.model} :: {d.name} ...", flush=True)
        r = run_task(d, args.endpoint, args.model,
                     temperature=args.temperature, max_tokens=args.max_tokens,
                     request_options=args.request_options,
                     provenance=args.provenance)
        print(f"[gauntlet]   {'PASS' if r['passed'] else 'FAIL'} "
              f"turns={r.get('turns', '-')} s={r.get('seconds', '-')} "
              f"tok={r.get('tokens_prompt', 0)}+{r.get('tokens_completion', 0)}"
              + (f" err={r['infra_error']}" if r.get("infra_error") else ""), flush=True)
        results.append(r)

    summary = {
        "schema_version": 1,
        "model": args.model, "endpoint": args.endpoint,
        "temperature": args.request_options.get("temperature", args.temperature),
        "max_tokens": args.request_options.get("max_tokens", args.max_tokens),
        "request_options": args.request_options,
        "provenance": args.provenance,
        "passed": sum(r["passed"] for r in results), "total": len(results),
        "results": results,
    }
    out = Path(args.out or ROOT / "results" / f"{args.model}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"[gauntlet] {summary['passed']}/{summary['total']} -> {out}")


if __name__ == "__main__":
    main()
