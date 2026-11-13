# EURUSD October 2026 intrabar tick replay (M1, M5)

- Exness raw tick rows: **1,039,321**; predeclared configurations: **384**.
- Entry: after 15s/30s in M1; after 60s/120s in M5.
- Exit: TP/SL first or at 55s (M1) / 285s (M5), always within original bar.
- Trading signal uses first tick and last tick **before entry decision**, preventing future leakage.
- Bid/Ask spread included, +0.2 pip per round trip extra execution friction; +0.5 pip stressed.
- Whole-month profit on >=20 trades (exploratory, in-sample selection): **7** configs.
- Selected only on first half of month: **0** configs.
- Selected with positive October: **0**.
- Selected with positive October AND positive second-half holdout: **0**.
- Plus positive full-month stress +0.5 pip: **0**.

## Train-selected candidates (second half was not used to rank)

ID | Frame | Side signal | Entry s | Threshold pip | Spread cap | Session UTC | SL/TP pip | Train pips | Holdout pips | October pips | Stress Oct pips | N
---|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---:

Only a single month was replayed. Do not deploy with real funds based on this screen alone.
The archived quotes are not an MT5 execution record. Extra commission, latency and partial fills can reverse tiny profits.
