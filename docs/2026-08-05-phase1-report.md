# Phase 1 report — chassis validated, first calibration numbers

Done today:
- **Inspect AI chassis**: three seed tasks ported (docker sandbox,
  in-sandbox acceptance scorer, protected-path restore). coder scores
  1.000/1.000/1.000 — identical to the bare harness. Teething: openai
  dep, sandbox keep-alive command, MLflow hooks 403ing on raw-IP host
  (future runs log via hostname).
- **BFCL v4 non_live**: coder and ornith both clean (0 inference errors)
  after throttling to 4 threads (llama-swap 429s at default concurrency).
  Result: near-parity on tool-calling; see results/bfcl/.
- **Verdict unchanged**: coder keeps the delegation slot. Ornith's
  weakness is scope discipline (gauntlet fix-bug), not schemas.

Registry: tolkien-27b v2 in MLflow now carries the actual weights
(43G in MinIO) — the publish pipeline survived an 8-attempt debugging
saga (Traefik reloads, DNS-rebinding guard, gunicorn red herring,
2Gi OOMKill, client-side multipart flag, presigned URLs needing a
LAN-reachable MinIO). All fixes in GitOps; future publishes are boring.

Next (P2): mini-swe-agent on a SWE-bench Verified subset with Epoch ARM
images; tau2-mini; AppWorld test-normal. Then P3 custom domains.
