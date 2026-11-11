# V10.0 — Select 3 complementary methods for deployed #3 and #6 (USDJPY)

Research date: 2026-11-11. Dataset: Exness-labelled tick-derived M15, H1 and H4 bar data January 2026–November 9, 2026. No source data beyond Nov 9. #3 and #6 retain live parameter choices: **#3 M15 SMA8 SL60/TP150 at 06:00 UTC hold 8h**; **#6 H1 acceleration12 SL60/TP200 at 00:00 UTC hold 6h**. Exclude #2 and #5 as explicitly discarded by user.

## Method
- Candidate universe: remaining **16** of 20 original methods, all originally profitable in each month May–partial Nov 2026 and opening one trade per eligible weekday.
- Enumerated **C(16,3)=560** candidate triples; combine each with #3 and #6.
- Daily P/L = Bid/Ask OHLC M15 fill approximation, 0.5 pip extra per position; SL first if same candle simultaneously touches SL and TP. Individual results retain fixed original SL/TP, except #3 and #6 use newly validated stops noted above. Monthly profits and joint losses are IN SAMPLE and optimized on historical data.
- Joint loss definition: number of days with at least **5**, at least **4**, at least **3**, or at least **2** of the five methods returning negative net pips on the same calendar UTC trading date. This is NOT a claim that positions overlap in clock time.
- Primary ranking for May–Nov9 is lexicographic: minimize >=5, then >=4, then >=3, then >=2.
- Full-year cross-check: 220 common eligible weekdays Jan6–Nov9, 2026. May–Nov9: 137 common trading dates.

## Top choices

| Trio added to #3 #6 | May–Nov9 >=5 | >=4 | >=3 | >=2 | Five-strategy arithmetic net pips | Jan–Nov9 >=5 | >=4 | >=3 | >=2 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **#16 #17 #20** (recent severe-loss ranking winner) | **0** | **10** | 56 | 102 | 3546.7 | 3 | 28 | 105 | 173 |
| **#1 #4 #20** (stronger full-year loss clustering) | **0** | 11 | **47** | **93** | 4417.4 | **1** | **25** | **91** | **163** |
| #1 #9 #20 | 0 | 11 | 50 | 94 | 4242.8 | 1 | 25 | 94 | 165 |
| #1 #12 #20 | 0 | 12 | 45 | 102 | 4128.8 | 1 | 27 | 88 | 168 |

**Interpretation:** #16 #17 #20 ranks first by recent strict severe-loss (5,4,3,2) priority; #1 #4 #20 is a stronger overall compromise across all available 2026, with 1 more >=4 loser day in May–Nov, but 9 fewer >=3 days and 9 fewer >=2 days, plus better earlier-year robustness. Neither set should be automatically deployed just on these statistics: the same data were used for design and ranking.

## Parameters for recent-ranking winner

| Strategy | Signal | Entry UTC | Close latest UTC | SL/TP | May–Nov net pips |
|---|---|---:|---:|---|---:|
| #16 | Previous full trading day's H1 close minus opening Bid price, reversed | 12:00 | 14:00 | 25/50 | +243.9 |
| #17 | H1 12h momentum acceleration, reversed | 18:00 | 02:00 next UTC day | 30/30 | +520.5 |
| #20 | H1 6h momentum acceleration, forward | 06:00 | 08:00 | **NO SL/TP in original backtest** | +420.0 |

Recent winner 5-way pairwise same-day loss counts among the 137 dates:
#3/#6 28; #3/#16 23; #3/#17 19; #3/#20 24; #6/#16 26; #6/#17 27; #6/#20 30; #16/#17 19; #16/#20 26; #17/#20 22.

Monthly arithmetic pips for all five (not executable jointly as currently configured): May +421.5, June +94.9, July +702.6, Aug +562.4, Sep +1342.2, Oct +276.5, Nov9 +146.6. Earlier months Jan–Apr all negative in this modeled five-strategy sum (-202.3, -550.2, -215.2, -163.6).

## CRITICAL: no execution compatibility with current one-symbol guard

Actual files `V10_USDJPY_03_SMA8_Backtest.mq5` and `V10_USDJPY_06_H1_Accel12_Backtest.mq5` BOTH implement `HasAnyOpenPositionOnSymbol()`; they refuse new USDJPY entries when **ANY** current USDJPY position exists (regardless of Magic). Thus 5 independent daily P/L streams cannot be realized simultaneously on one MT5 account without modifying account/EA architecture and retesting.

With exact original schedules:
- #3 enters **06:00 UTC / 13:00 Vietnam**, holds up to 8 hours (14:00 UTC / 21:00 VN).
- #6 enters **00:00 UTC / 07:00 VN**, holds up to 6 hours (06:00 UTC / 13:00 VN).
- #16 enters **12:00 UTC / 19:00 VN**, while #3 can be open.
- #17 enters **18:00 UTC / 01:00 VN**, can last to 02:00 UTC / 09:00 VN and overlap #6's 00:00 entry on the following calendar day.
- #20 enters **06:00 UTC / 13:00 VN**, exactly the same entry as #3 and would be skipped under current symbol guard if #3 already entered.
- Alternative #1 and #4 both enter 14:00 UTC / 21:00 VN and therefore conflict with each other; #20 conflicts with #3.

**Do not add these 3 candidates to the current live VPS as independent bots without dedicated combined-portfolio / conflict backtesting.** #20 has no fixed stop loss and needs a tested emergency SL for production. #1 also lacks SL.

Original complete 20-strategy, daily execution and pip streams: [CSV](V10_all20_daily_signals_pnl_2026.csv).

## Interpretation caveats
- The five-strategy arithmetic sum assumes all five independent strategies open on each eligible day and trade the same USDJPY; capital and margin capacity, overlapping positions, swaps, slippage, re-optimizing parameter selection, future performance not validated.
- The full-year cross-check reuses same year of model development; it is not true untouched out-of-sample data.
- November 2026 is incomplete through November 9.
