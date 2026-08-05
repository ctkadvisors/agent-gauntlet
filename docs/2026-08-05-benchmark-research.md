# Fan-out research: off-the-shelf agent evals vs growing the gauntlet

Three parallel research passes (coding benchmarks, general agent benchmarks,
eval frameworks), 2026-08-05. Full reports in session history; synthesis here.

## Decision

**Hybrid.** No single off-the-shelf suite covers our use cases, but three
adoptions beat building everything ourselves:

1. **Inspect AI becomes the gauntlet's chassis** (UK AISI, MIT, weekly
   releases). Docker sandboxing with scorers that execute *inside* the
   sandbox (our executable-acceptance model ports nearly verbatim),
   first-class local OpenAI-compatible endpoints (`VLLM_BASE_URL`), and an
   Agent Bridge so our existing thin tool-loop runs unchanged during
   migration. `inspect-mlflow` (pin it — Alpha, single maintainer) reports
   into the MLflow we already run.
2. **Public benches for calibration, in this order:**
   - **BFCL v4** (tool-calling correctness; pure python, AST-graded, hours)
   - **mini-swe-agent → SWE-bench Verified subset** (bash-only loop, no
     function-calling requirement, numbers comparable to the public
     leaderboard; use Epoch AI's ARM64 images — stock images are x86-only
     and everything we own is ARM)
   - **tau2-bench** (policy-constrained multi-turn dialogue; MIT; needs a
     separate user-simulator model — never the model under test)
   - **AppWorld** (execution-verified multi-step ops; judge-free)
   - Stretch: MCP-Atlas 20-no-key-server subset (tool *discovery* among
     distractors — the kagent failure mode).
3. **Custom tasks stay, and grow** — the research's clearest finding is
   that nothing public covers our deployment shape: our MCP servers and
   kagent tool schemas, messaging-channel agents (Telegram/WhatsApp
   semantics), n8n-triggered automation, ops against our own cluster, and
   scope discipline (the ornith fix-bug failure: rewrote the class instead
   of fixing the bug). Pattern to follow: tau2's domain format for
   conversational agents; AppWorld's final-state verification for ops.

## Skip list (with reasons)

RepoBench (dead, contaminated), Commit0 (floors out below frontier),
LiveCodeBench (no agent loop), OpenHands suite (scaffold dominates small
models), AgentBench (unmaintained), ToolBench (rotting APIs), WebArena/
OSWorld (browser/VM weight), GAIA (measures the scaffold), HELM
(maintenance mode 2026-06), lm-eval-harness (single-turn only), promptfoo
(post-OpenAI-acquisition; red-team layer at most). Toolathlon/AIOpsLab are
the only credible k8s-ops benches but frontier models score 20-40% —
9B-35B models measure noise; revisit when candidates clear floors.

## Methodology invariants (from the research)

- Judge/user-sim models must never be the model under test or share its
  GPU (contention wrecks wall-clock; judge-error cascades wreck validity).
- Custom-task acceptance stays executable and binary; protected paths
  restored before scoring — the subject never grades itself.
- Every result lands in MLflow with model, quant, endpoint, and commit.

## Phases

- **P1**: Port the three seed tasks to Inspect (bridge our loop), wire
  inspect-mlflow, run BFCL v4 against coder + ornith.
- **P2**: mini-swe-agent on a Verified subset (ARM images); tau2-mini;
  AppWorld test-normal. Establish incumbent baselines for each.
- **P3**: Custom domains — scope-discipline suite, k8s-ops-in-kind,
  MCP-discovery against our own servers, Telegram-agent tau2 domain.
