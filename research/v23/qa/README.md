# V23 synthetic quote-side execution QA

Research-only. `v23_barrier_core.py` is an intentionally **partial** deterministic prototype, not the V23-PREREG-1.0 full strategy, MT5 fill simulator, or live-trading code. It does not train models, access future data, or place orders.

Run locally with Python 3.11+:
```bash
cd research/v23/qa
python -m unittest -v test_v23_barrier_core.py
```

The prototype uses executable-side Bid/Ask prices, modeled entry delay, stop/target trigger delay and gap fills, censoring on stale/missing quotes, a simple planned-risk cap, and commission/swap deductions. Its synthetic tests are fixtures only. It **does not** implement V23 event sampling, volatility-derived stop size, true broker stop registration, freeze/stop levels, broker fills, margin/stopout, full costs, mark-to-market DD, training, purged CV, or prospective validation. A triggered target is modeled as an adverse next-quote fill rather than a guaranteed limit fill. Do not use it to claim any after-cost edge.

This branch is a development control branch; frozen prereg and V22 results are unchanged. Source committed for independent review; passing a local test is not evidence that GitHub Actions ran. No GitHub Actions workflow is added.
