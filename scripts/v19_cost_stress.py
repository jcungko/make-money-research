#!/usr/bin/env python3
"""V19 verification: replay the three selected portfolios at wider slippage."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import v19_strategy_screen as v19

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path("data/v19_energies"))
    ap.add_argument("--out", type=Path, default=Path("data/v19_strategy_screen"))
    args = ap.parse_args()
    selected = json.loads((args.out / "expanded_portfolio_examples.json").read_text())
    assert len(selected) == 3 and all(r["positive_months"] == 22 for r in selected)
    identities = {name for r in selected for name in r["legs"]}
    result = {
        "test": "out-of-search cost sensitivity for the three 22-month-positive portfolios",
        "slippage_bp_per_side": [1, 2, 3],
        "method": "replay exact preselected strategy identities, no reoptimization",
        "not_included": "overnight financing, brokerage commissions, margin/liquidations and intrabar SL/TP",
        "portfolios": []
    }
    for slip_bp in result["slippage_bp_per_side"]:
        v19.SLIPPAGE = slip_bp / 10000.0
        strategies = {r["id"]: r for r in v19.screen(args.root, "USOIL") if r["id"] in identities}
        if strategies.keys() != identities:
            raise RuntimeError(f"Missing identities at slip {slip_bp}: {identities - strategies.keys()}")
        for index, portfolio in enumerate(selected):
            mat = np.array([strategies[leg]["monthly_bp"] for leg in portfolio["legs"]])
            monthly = mat.mean(axis=0)
            positive = int((monthly > 0).sum())
            record = {
                "portfolio": f"V19-{chr(65+index)}",
                "slippage_bp_per_side": slip_bp,
                "positive_months": positive,
                "profit_2025_bp": round(float(monthly[:12].sum()), 4),
                "profit_2026_bp": round(float(monthly[12:].sum()), 4),
                "min_month_bp": round(float(monthly.min()), 4),
                "negative_months": [v19.MONTHS[i] for i, p in enumerate(monthly) if p <= 0],
                "monthly_bp": np.round(monthly, 4).tolist(),
                "legs": portfolio["legs"]
            }
            result["portfolios"].append(record)
            print("V19_COST_STRESS", json.dumps({k:v for k,v in record.items() if k not in ("legs","monthly_bp")}), flush=True)
    path = args.out / "V19_portfolio_cost_sensitivity.json"
    path.write_text(json.dumps(result, indent=2))
    print("V19_STRESS_DONE", str(path), flush=True)

if __name__ == "__main__":
    main()
