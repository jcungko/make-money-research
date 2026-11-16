# USDJPY AI Research Autopilot R1 (RESEARCH ONLY)

No live trading, no MT5 connectivity, no Telegram token in GitHub, no paid API, no changes to existing EAs. Research-only Telegram notices are delivered through an OIDC-authenticated Cloudflare Worker.

## Operation
- Workflow: `.github/workflows/usdjpy-research-autopilot.yml` on `main`, UTC hourly minute 17.
- Workflow checks out *isolated* `research/usdjpy-autopilot-20261116` branch.
- Source datasets: `data/v17_exness_2025/USDJPY_2025_UTC_7TF.zip` and `data/v17_exness_2026/USDJPY_2026_UTC_7TF.zip` with manifest provenance, M5 Bid/Ask.
- Registers a finite deterministic search space of 96 configurations, maximum 2 new experiments per hourly run. Each entry uses the *following* bar's executable bid/ask opening quote, with hard modeled SL and TP; intrabar ambiguity is stop-first.
- Each run hashes source ZIP files and saves unique per-experiment JSON with per-trade ledger, cost-stress results and limitations.
- Every cycle restores the newest successful GitHub Actions checkpoint. V2 verifies SHA256 of state, index, journal and last run's per-trade evidence, and fails closed on missing or corrupted checkpoint.
- State and a bounded SHA256 proof index are stored as small `usdjpy-checkpoint-<run_id>` artifacts; per-trade evidence is separately stored as `usdjpy-evidence-<run_id>` artifacts, retained for 90 days. GitHub Actions runs read-only and never commits results. Historical experiments before the v2 migration are explicitly marked `legacy_unindexed`.
- On candidate, error, exhaustion or workflow smoke test, GitHub Actions sends a short research-only Telegram notice to the existing Cloudflare Worker using signed GitHub OIDC. BTC alerts remain unchanged. No Telegram credentials are passed to GitHub.
- A `BLOCKED` run records the error and exits nonzero. Cursor only advances after experiment evidence is saved. Resume from stored cursor on next schedule.
- After 96 registered configurations, report `EXHAUSTED`; never blindly mine unbounded combinations.
- Research candidates are NOT approved for real trading, NOT independently forward verified. Historical years have already been investigated many times.

## Controls and limitations
- This is a deterministic research generator, not a paid LLM. It exercises pre-registered mechanical hypotheses. Creative new AI ideas require a separate approved protocol.
- PnL is indicative USD conversion of USDJPY quoted Bid/Ask under 1000 USD notional, modeled baseline 0.3 pip per side and stress 1.2 pip per side + 0.10 USD round-trip commission.
- Actual Exness account commission, swap, fill latency, stop restrictions and raw tick-level SL/TP ordering NOT verified. Never claim fully costed PnL or forward verification.
- Recorded bar open and quote series are historical, not live broker fills. Partial intrabar and gap uncertainty remain.
- The dataset is historically exposed, NOT clean holdout. This phase produces **RESEARCH_CANDIDATE** and **REJECTED** only.
- Later phases require broker-calibrated raw tick replay, walk-forward, multiple-testing correction, independent prospective protocol and explicit live approval.
- Schedule is best effort, can skip/delay. Verify current Actions runs and checkpoint artifacts to confirm progress. Since this R1 search is finite, no new hypothesis families are generated automatically after 96 registered configurations.

## Proof of real experiments
Inspect GitHub Actions run job steps, `usdjpy-checkpoint-<run_id>` (`state.json`, `index.json`, `manifest.json`, `run_*.json`) and `usdjpy-evidence-<run_id>` (`UJ-R1-xxx.json` with trades). Compare cursor, SHA256 hashes and experiment IDs. A green workflow without validated proof is NOT sufficient proof.
