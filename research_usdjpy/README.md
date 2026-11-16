# USDJPY AI Research Autopilot R1 (RESEARCH ONLY)

No live trading, no MT5 connectivity, no tokens, no Telegram, no paid API, no changes to existing EAs.

## Operation
- Workflow: `.github/workflows/usdjpy-research-autopilot.yml` on `main`, UTC hourly minute 17.
- Workflow checks out *isolated* `research/usdjpy-autopilot-20261116` branch.
- Source datasets: `data/v17_exness_2025/USDJPY_2025_UTC_7TF.zip` and `data/v17_exness_2026/USDJPY_2026_UTC_7TF.zip` with manifest provenance, M5 Bid/Ask.
- Registers a finite deterministic search space of 96 configurations, maximum 2 new experiments per hourly run. Each entry uses the *following* bar's executable bid/ask opening quote, with hard modeled SL and TP; intrabar ambiguity is stop-first.
- Each run hashes source ZIP files and saves unique per-experiment JSON with per-trade ledger, cost-stress results and limitations.
- The repository's github-actions bot received HTTP 403 on git push. Until separate security approval, every run stores its results and state as a GitHub Actions artifact (`usdjpy-checkpoint-<run_id>`) with 90-day retention. Next run restores the most recent checkpoint state using GitHub's API. Individual experiments remain as evidence in their original run artifacts, rather than being committed to the branch. These artifacts are temporary and NOT durable long-term storage.
- A `BLOCKED` run records the error and exits nonzero. Cursor only advances after experiment evidence is saved. Resume from the previous artifact cursor on next schedule; do not silently reset if previous run exists but checkpoint is unavailable.
- After 96 registered configurations, report `EXHAUSTED`; never blindly mine unbounded combinations.
- Research candidates are NOT approved for real trading, NOT independently forward verified. Historical years have already been investigated many times.

## Controls and limitations
- This is a deterministic research generator, not a paid LLM. It exercises pre-registered mechanical hypotheses. Creative new AI ideas require a separate approved protocol.
- PnL is indicative USD conversion of USDJPY quoted Bid/Ask under 1000 USD notional, modeled baseline 0.3 pip per side and stress 1.2 pip per side + 0.10 USD round-trip commission.
- Actual Exness account commission, swap, fill latency, stop restrictions and raw tick-level SL/TP ordering NOT verified. Never claim fully costed PnL or forward verification.
- Recorded bar open and quote series are historical, not live broker fills. Partial intrabar and gap uncertainty remain.
- The dataset is historically exposed, NOT clean holdout. This phase produces **RESEARCH_CANDIDATE** and **REJECTED** only.
- Later phases require broker-calibrated raw tick replay, walk-forward, multiple-testing correction, independent prospective protocol and explicit live approval.
- Schedule is best effort, can skip/delay. Verify Actions runs, downloadable checkpoint artifacts and the current cursor. No claim that research results have been committed to GitHub git history.

## Proof of real experiments
Inspect GitHub Actions run job steps and the `state.json` `completed` and `cursor` **inside the checkpoint artifact**. Compare the timestamped `run_*.json` report with corresponding `experiments/UJ-R1-xxx.json`, including trades and cost assumptions. A green workflow without evidence is NOT sufficient proof.
