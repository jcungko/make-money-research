# V20 frozen audit closure — 2026-11-13

V20-FROZEN-1.0 is **closed NO_EDGE**, not an approved trading strategy. Existing 24 strategy configurations stay unchanged.

* Frozen rules SHA256: `61b8ec773a1370dec62d3467d4bd19ffd63643ccf21f608035b10abcaadeae60`
* Research result ZIP SHA256: `11bd1dbf1f621d25d080d6a4c03d6c178bb056b2596450b7f25e1a468ae7b9fb`
* Source data: 22 original month ZIPs; 26,928,588 tick rows reported by V20 before 47,758 deduplications; 26,880,830 processed.
* Source SHA256 checks and ZIP CRC: 22/22 PASS as independently rechecked on local copies of GitHub artifacts.
* Recovered raw archive: `V20_FULL_22_MONTHS_RAW_TICKS_VERIFIED.zip`, SHA256 `fdc4cf05b437a93a6276abb9a0c91c2592eb77fe9606fa5cbb1a77ff84c858d7`, 174,417,836 bytes, created as conversation download, **NOT permanently stored in this repository**.
* Source and result code snapshot: `V20_AUDIT_SOURCE_RESULTS_FROZEN.zip`, SHA256 `72e3c56e59d3d7263d58d2d9a65cf4eb13189f2a3c3b6007d54a141a0c21827f`.
* GitHub source/run: https://github.com/jcungko/make-money-research/actions/runs/43361899089 and https://github.com/jcungko/make-money-research/pull/1 (draft, not merged).

**Methodology limitations:** Bid/Ask archive quotes are *indicative prices*, not broker deal/fill logs; simulated 2ms is **not** a measured MT5 execution time. The modeling assumptions for $100 equity, 0.01 lot, leverage 1:200, Standard zero commission, adverse slippage, same-day swap zero and server-side stop behavior are not certified as full historical broker costs. V20's 96 NO_TRADE walk-forward selections demonstrate a failed training gate, not observed profitable OOS trades. All pre-Nov-14-2026 history previously inspected by V12/V17/V20 is not clean OOS for V21.

**URGENT preservation:** GitHub source artifacts expire around 2026-12-13. Download both combined ZIPs and keep a second immutable copy outside GitHub Actions. This commit preserves the full metadata index (below) but *not* the raw 174MB payload.

See `research/v20/ARTIFACT_PRESERVATION_INDEX_2026-11-13.json`.
