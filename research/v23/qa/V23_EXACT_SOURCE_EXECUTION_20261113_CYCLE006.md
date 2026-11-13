# V23 committed-source exact QA — cycle 006 (2026-11-13T13:15Z)

**PASS: 19/19 synthetic tests in local Python 3 runtime; NOT an Exness backtest, not GitHub Actions, not broker certification, not a profitable strategy.**

Source obtained from GitHub connector and reconstructed byte-for-byte in local isolated runtime. Verified Git blob SHA-1 before execution:
- `research/v23/qa/v23_barrier_core.py`: `7c87d05ec07f83f3ba06a15047771e1d65d34ee4`; local SHA-256 `0cdd178ba5830950bb530285a2e27accffa242453f720db3525f4f541102c1ec`.
- `research/v23/qa/test_v23_barrier_core.py`: `0a4f072fa89512cebcd3727d71d08177522ac8ae`; local SHA-256 `796f340d89e509af60868ed94c21ca1495693a10aaab0ceb9e65e64d067b069e`.
- Newly added `research/v23/qa/test_v23_adversarial.py`: `e74e299e0133bbbff1d4082da8b161cf037e39d7`, matching local blob SHA.

Command: `python -m unittest discover -v` in isolated directory with exactly these three Python files. Result: `Ran 19 tests in 0.001s; OK`. Full local stdout/stderr log SHA-256: `98a27279767674294a7d1a09d50151893382b232a60180926f0ee88fea794148`. Tests: 13 original plus 6 adversarial (missing triggered stop fill; timeout gap inside/outside quote tolerance; same-millisecond ordering; widened spread; negative swap input diagnostic).

**Risk finding:** missing stop fill and large timeout gap beyond 2s return CENSORED with `pnl_usd=None`. This is not a realized zero and cannot be dropped as if no position existed. Full V23 PnL and DD require explicit unresolved-position accounting and invalidation gate. The prototype accepts negative swap input; actual broker credits/charges must be validated, not assumed. No broker execution/MT5 stops or prospective data were evaluated.

Reproduction on GitHub checkout: `cd research/v23/qa && python -m unittest discover -v`. This run was LOCAL with GitHub blob identity checks, not an Actions run; no workflow dispatch was made.

GitHub Actions / prospective: latest listed Actions run at 2026-11-13T07:02:32Z was an unrelated main workflow. No V23 QA Actions run or prospective capture observed. `/actions/artifacts` endpoint remains disallowed by connector. Prospective day 2026-11-14 UTC cannot be downloaded before 2026-11-15T02:43Z. Main HEAD unchanged `793df3a248b77d086b3471c24b75df6f773c5862`.

No V23 model trained or weights sealed; V20–V22 NO_EDGE. No live trade, no merge, no main/workflow/trading/Telegram/Cloudflare edits, no paid AI service.
