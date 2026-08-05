# BFCL v4 non_live — ornith (Ornith-1.0-35B Q8 GGUF, llama-server)

2026-08-05, direct llama-server endpoint (model's own chat template via
--jinja), Qwen3-30B handler for scoring format, 0 inference errors.
Caveat: cross-model handler — treat small deltas as noise.

| category | coder | ornith |
|---|---|---|
| simple_python | 96.0% | 91.3% |
| multiple | 93.5% | 94.5% |
| parallel | 90.5% | 88.5% |
| parallel_multiple | 92.0% | 90.0% |
| irrelevance | 86.7% | 84.2% |
| simple_java | 64.0% | 60.0% |
| simple_javascript | 56.0% | 60.0% |

Read: tool-calling parity with the incumbent — the gauntlet's fix-bug
scope failure, not schema competence, is what separates them.
