# BFCL v4 non_live — coder (Qwen3-Coder-Next-GB10, NVFP4/Marlin, vLLM)

2026-08-05, handler Qwen/Qwen3-30B-A3B-Instruct-2507-FC via llama-swap
alias, --num-threads 4 (endpoint 429s at BFCL's default concurrency),
zero inference errors.

| category | accuracy |
|---|---|
| simple_python | 96.0% |
| multiple | 93.5% |
| parallel_multiple | 92.0% |
| parallel | 90.5% |
| irrelevance | 86.7% |
| simple_java | 64.0% |
| simple_javascript | 56.0% |
