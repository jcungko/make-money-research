# Make Money — AI Research Autopilot control plane

This directory is a **research-only audit trail**, not an execution or live-trading authorization.

`state.json` is the current machine-readable checkpoint. Each cycle should create a uniquely named immutable file in `journal/`, and update state via SHA-safe write. On an access or execution failure, record `BLOCKED` rather than pretending an experiment ran. The scheduled chat task is an hourly **coordinator**, not proof that GitHub Actions experiments ran.

Authoritative frozen sources: V22 `research/v22/V22_AUDIT_LOCK_ADDENDUM_20261113.md` and `V22_PREREG_1_0.json`, V23 `research/v23/V23_PREREG_1_0.json`, on their respective research branches. The scheduled prospective raw capture workflow is installed separately on `main`, `.github/workflows/v22-prospective-exness-isolated.yml` (02:43 UTC); initial run and actual raw capture must be verified in Actions and artifacts.

Safeguards: never touch live trade/Telegram/Cloudflare flows, do not merge control or model code into `main` automatically, do not use paid API/services, no live MT5 trades, do not claim VPS ping equals fill time, exclude Backcom from Trading PnL, and do not tune frozen history to manufacture profitability. Future-data verification requires pre-registered protocol, sealed code/weights, after-cost profitability, adequate sample, calibrated broker execution, and risk checks.
