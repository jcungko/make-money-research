# MAKE MONEY — Independent Futures Research

Automated, **research-only** backtests of public Binance USDⓈ-M perpetual-futures historical data.

- **No live orders or API trading keys.** No Telegram or Cloudflare access.
- Research runs are bounded by GitHub Actions compute budgets; each scheduled job resumes from a recorded state cursor.
- Candidate profits are **exploratory simulations**, not evidence of guaranteed or live trading returns. Funding, fees, fill assumptions, and out-of-sample stability must be reviewed.
- Do not store tokens, exchange secrets, or personal data in this repository.
- This repository is currently public. For proprietary research, change its visibility to **Private** in GitHub Settings > General > Danger Zone.

See `.github/workflows/research.yml`, `research.py`, and `results/state.json` for workflow and results.
