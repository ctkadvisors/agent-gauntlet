# agent-gauntlet

Gate discipline applied to agent models: before any new model gets adopted
into a serving or delegation harness,
it runs the gauntlet and gets a machine verdict — the same
never-adopt-on-vibes rule as tolkien-llm's phase3 gate.

## What it measures

A deliberately minimal tool-loop (two tools: `bash`, `write_file`, OpenAI
tool-calling, capped turns) drives the model through real micro-tasks with
executable acceptance checks: fix a bug without touching tests, implement
from a docstring, make a coordinated cross-file change. Scored on pass/fail
plus turns, wall-clock, and tokens. Protected paths are restored from the
pristine fixture before acceptance runs — the subject never grades itself.

The harness is intentionally thin: it evaluates the model, not a scaffold.
A model that can't explore/edit/iterate here won't be saved by fancier
tooling.

## Usage

    python3 -m harness.run --endpoint http://127.0.0.1:9090 --model coder
    python3 -m harness.run --endpoint http://127.0.0.1:9090 --model ornith

Results land in `results/<model>.json` (committed — they're the evidence).
Compare candidates against the incumbent before swapping any serving slot.

## Security note

`harness/agent.py` executes model-authored shell in a throwaway tempdir by
design. Run only against models you're willing to give a shell on that box.

## Adding a task

`tasks/<name>/task.yaml` (prompt, acceptance, protected, timeout_s,
max_turns) + `tasks/<name>/fixture/` files. Keep acceptance executable and
binary — anything a human must judge doesn't belong here.
