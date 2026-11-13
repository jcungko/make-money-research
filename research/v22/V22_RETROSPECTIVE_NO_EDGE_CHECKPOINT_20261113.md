# V22 — empirical retrospective checkpoint, 2026-11-13 (READ ONLY)

**Preregistered before model outcomes:** `research/v22/V22_PREREG_1_0.md`, commit `f002cea95896d61883fdcf878358df5f6f4d5bfc` and full JSON SHA256 `f2dd2f22b86ca031f8e9694d3dad0c192d2ca5235de07ff7134bfed49b88eeb5`.

**V21 remains CLOSED_NO_EDGE and unchanged**, see `research/v21/V21_SEALED_MANIFEST_20261113.json`. Historical archive 2025-01 through 2026-10 was previously inspected; no clean OOS may be claimed. Original archived EURUSDm Bid/Ask ZIP aggregate SHA256: `fdc4cf05b437a93a6276abb9a0c91c2592eb77fe9606fa5cbb1a77ff84c858d7`.

## Finding 1 — V21 cost attribution
- All 2565 source trades across base/stress execution were matched to original Bid/Ask entry/exit quotes; reconstructed trade PnL exact (max abs difference USD 0).
- Baseline V21 directional midpoint PnL / spread cost / adverse slippage cost: Tick Momentum -$9.495/-$63.495/-$14.14; Quote Reversal -$6.855/-$7.565/-$1.74; Volatility Compression -$2.88/-$51.54/-$11.78. **All three already have negative directional return before costs**.

## Finding 2 — 6 horizons, disjoint samples
- 36,126 UTC calendar grid slots every 600s, 7,074 past-only feature-valid anchors, 5,948 60s-outcome eligible. 2025/2026 pre-inspected, STRICTLY exploratory.
- Mean independent quote-side 0.01-lot long/short USD net after 1pt per side adverse slip: 5s -0.10104/-0.10999; 10s -0.10014/-0.11090; 30s -0.10150/-0.10968; 60s -0.10288/-0.10822; 120s -0.09846/-0.11255; 300s -0.08956/-0.12130. Independent action diagnostics, not a continuously financed strategy and NO broker stops.

## Finding 3 — frozen model comparison, expanding train / purged 2026 historical walk-forward
- Baseline: multinomial Logistic Regression selected only **1 trade**, +$0.33 PnL / $0.33 observed average, DD $0.26. Profit Factor **undefined** because this is one winning trade, NOT evidence of positive expectancy.
- AI LightGBM selected **5 trades**, -$1.10 PnL, -$0.22/trade, PF=0, quote-equity DD $1.43.
- 2026 Jan–Oct account equity kept across all folds, $100 initial balance, 0.01 lot, simulated broker-registered SL20pt TP34pt, 100ms latency with 1pt adverse slip/side and actual Bid/Ask. 300ms+3pt slip and 1.5x/2x spread chronological stop replays completed. No 2ms fill claim.
- Both are **NOT QUALIFIED**, primarily lack of independent validation and sample sizes, with LightGBM also net negative. No high-win-rate/accuracy shortcut and NO trade deployment.

## Reproducibility and prospective collection
- Full local source/QA/results package SHA256 `61d3578eaaf45ee812528ae781a8ba2be0996147c2b733d8bf73bc4feb595a5f`, filename `V22_AI_MICROSTRUCTURE_RESEARCH_20261113.zip`, made available as a ChatGPT conversation artifact; 19/19 source/collector test PASS. GitHub does NOT yet store this package or full source.
- The downloadable research package includes `scripts/v22_prospective_collect.py` and `.github/workflows/v22-prospective-exness-daily.yml`. **Those are ready-to-install only, not active in main.** They collect closed daily raw ZIPs from 2026-11-14 UTC onward, preserve SHA and archive without training/evaluating future labels.
- Fixed prospective acceptance gate: >=200 trades, >=20 days, >=2 complete months, PF>=1.2, positive expectancy and day-cluster lower CI>0, DD<=20% of $100, robust positive under latency/slippage/spread stress, MT5 actual stop/margin/fills calibrated. None met or even independently measurable yet. No backcom. NO_EDGE until genuinely future untouched evidence.
