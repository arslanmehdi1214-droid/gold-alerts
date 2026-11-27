"""v1.15 (27 Nov 2026, his explicit "push Brent v1.15"; source EA BRENT_WED_HOL_v115.mq4 md5 0149f41e75298717227385d9a9cf389c, handoff
Trading/BRENT/BRENT_v115_desk_handoff.md): eight stacked upgrades on top of the live v1.10 rules below (every v1.10 rule, A-F/K+/AW/K2, is
unchanged and every upgrade has its own on/off flag USE_*). MT4 (his run 27 Nov 2026, tester 2017-2026, trades 2018-26): net $143,597,
equity DD $12,228 (1.16%), 1,832 trades, PF 1.65, 55.1% closed in profit; closed-trade net/DD 16.08 vs v1.10's 9.05 (+78%), both eras up.
All times broker clock. A = 20-day average daily range. Every trade closes 21:30 broker unless stated. Each add-on is its OWN position with
its own tag, appended after the conflict-close step like K+/AW/K2 (the EA's OpenM() has no conflict-close and Open() only looks at the main magic).
  U1 A16   rule A fired today -> at 16:00, if (16:00 price - 10:00 price) has A's sign -> 2nd trade in A's direction, stop 1.0 A. Tag A16.
  U2 B12   rule B opened (day after a US holiday) -> at 12:00, if price < B's entry (B's sell is in profit) -> 2nd SELL, stop 1.0 A. Tag B12.
  U3 C14   rule C opened BEFORE 14:00 -> at 14:00, if price is beyond C's entry in C's direction -> 2nd trade, stop 1.0 A. Tag C14.
  U4 A12K  Wednesday: m12 = price(12:00) - price(10:00), every day; SD = std of the last <=60 m12 (>=30 needed). If |m12| > 0.5 SD -> enter at
           12:00 in m12's direction, stop 1.0 A; at 14:00 keep it only if rule A fires the SAME way, else close it at 14:00. Tag A12K.
  U5       rule D UK-holiday BUY at 2x size (row size 2.0 -> autotrade.py's weight() doubles the risk).
  U6       rule D UK-holiday BUY LIMIT entry: target = 11:00 price - 0.05 A; buy as soon as price reaches it before 11:30 (fill = the target price,
           or the bar open if it gapped below), else buy at market at the 11:30 bar open.
  U7       rule E sell at 2x size when the 09:59 close is at or above the 03:00 bar's close.
  U8       mid-range skip: pos = (yesterday's 21:29 close - min of the last 250 daily closes) / (max - min) (window includes yesterday, needs >=120
           closes). If 0.33 <= pos <= 0.67 -> skip rule A today and with it AW, A16 and A12K. (Unavailable closes = no skip, as the EA with <120 days.)
The upgrades apply from broker day V115_FROM on (see below); run_day(v115=False) reproduces the v1.10 engine exactly.
Brent Oil (BRENT) dashboard SIGNAL engine - BRENT v1.07a rules (A-F unchanged + new rule K+ added 9 Nov 2026 on
top of the live v1.06 A-F build, his explicit request - "keep A-F exactly as they are"; rule G and the
conflict-close rule's interaction with it were part of the EA bundle but dropped from this port - his 8 Nov
decision: "drop rule G completely... no changes to autotrade.py"), source of truth EA BRENT_WED_HOL_v106.mq4 for
A-F, BRENT_WED_HOL_v107a.mq4 (K+ block, lines 423-441) for K+.
(MT4 proof for the FULL v1.06 bundle including G, his run 7 Nov 2026: 2018-01-02..2026-10-30, spread 8 (= $0.08/bbl,
RoboForex live spread), 0.30 lot: 949 trades, +$58,856, PF 1.46, max DD $9,529, 55.2% trades closed in profit, trades
on 851 days (~1.9/week). That number is NOT what this A-F-only port will show live - G added real trades/profit to
the MT4 run, so the live A-F-only journal will read somewhat lower than +$58,856. v1.05 same test (also A-F, no G):
911 trades, +$50,198, DD $7,979 - that is the closer like-for-like comparison for this port. Only losing year in
the full-bundle run was 2019 (-$2,245).)
Pure functions, no I/O - used by brent_run.py (desk) only. Copied to the Capital.com DEMO account by autotrade.py
(his 6 Nov go-ahead, given later the same day as his earlier "signals only, EA is backtest only" instruction - the
go-ahead is what stands; see autotrade.py's own docstring and its MARKETS['BRENT'] entry, confirmed live 8 Nov).
Clock: broker = New York + 7h (same convention as every other desk market; Dubai = broker + 2h winter / +1h summer).
Common to every rule: STOP = 1.0 x average daily (high-low) range of the last 20 broker days, EXCEPT rule C (2.0x,
v1.06: was 1.0x, shared with the others). No target. EXIT = 21:30 broker if the stop is not hit first. Several
rules can fire the same day (separate trades, same stop rule unless noted) - but if a new signal is OPPOSITE an
already-open trade from earlier the same day, that open trade is closed at the new signal's price/time and the new
signal is itself skipped (v1.06, new - see apply_conflict_close() below).
RULE A - WEDNESDAY MOMENTUM: move = price(14:00 broker) - price(10:00 broker), computed every broker day. On Wednesday,
  if |move| > 0.5 x the standard deviation of the last 60 days' moves -> trade IN that direction at 14:00. (~29 trades/yr)
RULE B - DAY AFTER A US FEDERAL HOLIDAY: SELL at 11:00 broker, the first trading day after a US federal holiday.
  (v1.06: was 10:00.) (~8/yr)
RULE C - 20-DAY RANGE BREAK: at 09:00 broker price must be inside the prior 20 broker days' high/low (v1.06: watch
  starts 09:00, was 10:00); the first 1-minute CLOSE beyond that range between 09:00 and 19:00 broker -> enter at
  the next minute, in the break's direction; STOP 2.0x the range (v1.06: was 1.0x, shared with the other rules).
  (~36/yr)
RULE D - UK BANK HOLIDAY: BUY at 11:00 broker on a UK bank holiday the market trades (v1.06: was 10:00; Christmas /
  New Year's Day / Good Friday are full market closures, excluded from "a UK bank holiday the market trades");
  SELL at 11:00 on the next trading day (v1.06: was 10:00; skipped when that next day is already a rule-B day, so
  the two rules never double up). (~8/yr)
RULE E - 2ND TRADING DAY AFTER A UK BANK HOLIDAY: SELL at 10:00 broker (v1.06: unchanged - its own entry-time
  setting, untouched by the B/D time change). A separate, later date than rule D's own "next trading day" sell -
  both can exist for the same holiday without colliding (different calendar dates).
RULE F - DAY BEFORE A US FEDERAL OR UK BANK HOLIDAY: BUY at 19:00 broker (pre-holiday drift, unchanged). Same
  stop/exit as every other A/B/D/E rule (1.0x 20-day range, 21:30 broker exit, so this is a ~2.5h hold unless
  stopped first).
CONFLICT-CLOSE (v1.06, new): if a new signal is OPPOSITE an already-open trade from earlier the SAME day, that open
  trade is closed at the new signal's price/time and the new signal is skipped entirely (no trade for it). Applied
  inside run_day() via apply_conflict_close(), mirroring the EA's Open(): it loops every open order and closes any
  opposite one before deciding whether to place the new one.
RULE K+ - OVEREXTENSION FADE (v1.07a, new 9 Nov 2026, added on top of live A-F per his request; EA block lines
  423-441, BRENT_WED_HOL_v107a.mq4; MT4 proof 9 Nov: 285 trades, 0 stop hits, 52% closed in profit, net +$7,716,
  2018-2026 - by year: 2018 -90, 2019 -798, 2020 -657, 2021 +1578, 2022 -1581, 2023 +1971, 2024 +1254, 2025 -1017,
  2026 +7056 - most of the edge is 2026, shown on the card as "new, thin before 2026"): ref1 = price at 09:00
  broker, ref2 = price at 10:00 broker (same bar-open convention as every other rule, ENTRY_LATE tolerance). A =
  the same 20-day average range the other rules use for their 1.0x stops. th = 0.8 x A. Walk every closed 1-minute
  bar from 09:01 to 17:59 broker: once past 09:00, HIGH >= ref1+th -> SELL, LOW <= ref1-th -> BUY (fade back toward
  the reference); once past 10:00, if nothing has fired yet, same test vs ref2. First touch only - at most one K+
  trade/day. Enter at the NEXT bar's open. Stop = 2.0 x A (not the shared 1.0x). Exit 19:00 broker if not stopped
  first (the common 21:30 EXIT_MIN below is the unconditional backstop). Skipped entirely (no K+ today) on
  Wednesday, on any day already in the B/D/E/F calendar lists below, or if rule C has already opened its own trade
  by the moment K+'s signal would fire (a C trade AFTER that moment does not cancel K+). Fully independent of A-F:
  own trade/position (own "KFADE" tag), does NOT take part in conflict-close in either direction - it is appended
  to the day's trades AFTER apply_conflict_close() runs on A-F+C, never passed through it. No day-start-bug
  exposure (the MT4 v1.07->v1.07a class of bug, where a stale bar from an earlier calendar day wrongly looked like
  "already past today's cutoff"): this Python port has no persisted cross-day flag at all - kfade_trade() is a
  pure function of `day`'s OWN closed bars only (brent_run.main() already slices `b` to [day, now) before calling
  run_day()), so there is nothing analogous to mis-handle.
RULES AW + K2 (v1.10, new 9 Nov 2026, added on top of live v1.07a per his request - "keep A-F and K+ exactly as
  they are"; source EA BRENT_WED_HOL_v110.mq4, AW block lines 508-516, K2 block lines 482-488; spec
  BRENT_v110_DASHBOARD_SPEC.txt). MT4 proof 9 Nov, full v1.10 EA: net +$81,158, PF 1.43, max drawdown $10,241, 1,492
  trades (v1.07a baseline: +$67,704, DD $9,199, 1,241 trades, PF 1.43 - net per $1 of drawdown 7.92 vs 7.36, at
  equal drawdown ~+7.7% net; v1.10 technically misses the strict $10,000 max-DD cap by $241 but wins on the
  equal-drawdown rule, his go-ahead 9 Nov 2026). AW+K2 together add 251 trades (AW 210 at full size, K2 41 at half
  size) = +$13,453 - by year: 2018 +1,863, 2019 -860, 2020 +2,999, 2021 +753, 2022 +5,596, 2023 -632, 2024 +1,071,
  2025 -551, 2026 +3,213 - $5,596 of the $13,453 (42%) is 2022, shown on the card as "new, 2022-heavy". Both rules
  open and close the SAME broker day only (exit 21:30, the common EXIT_MIN below, same as A-F) - no day-start-bug
  exposure, same reasoning as K+ above.
  RULE AW - WEDNESDAY RE-ENTRY: arms whenever rule A's OWN signal condition is true today (awdir = rule A's
  direction, from wed_signal() - independent of whether fixed_trade() for 'A' actually returns a trade, same as
  the EA arms off the signal condition itself, not off OrderSend()'s success). Reference = CLOSE of the 14:00
  broker bar. Walk every closed bar from 14:01 to 14:30 broker (AW_WINDOW_MIN): first bar whose close crosses back
  through the reference AGAINST awdir (long: close < ref; short: close > ref) -> open a 2ND trade IN RULE A'S OWN
  DIRECTION (awdir, not the pullback's direction) at the next bar's open. First touch only - at most one AW
  trade/day. Stop = 2.0 x A (AW_STOP_MULT, not the shared 1.0x). Exit EXIT_MIN (21:30) if not stopped first.
  Skipped entirely on any day already in the B/D/E/F calendar lists (own 'AW'/'AW' tag, mirrors kfade_trade()'s
  IsCalendarDay() check exactly - aw_trade() below).
  RULE K2 - K+ ADD-ON FADE AT HALF SIZE: only after a K+ trade opened today (k_trade = kfade_trade()'s own return
  value). Trigger price = the CLOSE of the bar that triggered K+ (carried on the K+ trade dict as 'trig'). From the
  bar AFTER the K+ entry bar until 17:59 broker (the same K_LAST_SIGNAL_MIN cutoff K+ itself uses): if price runs a
  further 0.5 x A (K2_MOVE_MULT) beyond the trigger price IN THE SAME DIRECTION AS THE ORIGINAL STRETCH K+ itself
  faded against -> open a 2nd fade, SAME direction as K+, at the next bar's open. First touch only - at most one
  K2 trade/day. Stop = 2.0 x A (K2_STOP_MULT - same distance as K+'s own stop; the "half size" is in the LOT SIZE
  only, not the stop distance). Exit EXIT_MIN (21:30 - NOT K+'s own 19:00, per spec). Skipped if rule C already
  traded today (unconditional - unlike K+'s own, timing-gated check), on Wednesday, or on any calendar-list day.
  SIZE: carried as tag='K2' on the trade dict; brent_run.row() turns that into size=K2_LOT_X (0.5) so
  autotrade.py's weight()/plan() halves the USD risk and lot size relative to a normal trade - K2_LOT_X is NOT a
  stop-distance multiplier (k2_trade() below).
  Both AW and K2 are fully independent of A-F/K+/each other: own trade/position (own tag), do NOT take part in
  conflict-close in either direction - both are appended to the day's trades AFTER apply_conflict_close() runs on
  A-F+C, same treatment as K+ (run_day() below).
WATCH RULES W1-W4 (v1.12W, new 19 Nov 2026, DEMO / FORWARD TEST ONLY - his instruction "demo only, keep live v1.10 unchanged";
  source EA BRENT_WED_HOL_v112W.mq4 (md5 54564281efc512dbe26015fd353aa326), spec BRENT_v112W_DASHBOARD_SPEC.txt). Four extra
  rules, each its OWN position with its OWN tag, independent of every live rule (no conflict-close in either direction, appended
  after A-F/K+/AW/K2), all same-day (closed 21:30 broker). None has a target - they close on time. MT4 proof 19 Nov (his run,
  BRENT M1 every tick, spread 8, 0.30 lot, 2018-01-02..2026-10-30): full v1.12W EA +$94,121, PF 1.41, max DD $9,527, 1,811 trades;
  v1.10 part unchanged 1,491 trades +$80,891. W1 M4 106 trades +$1,441 (52% closed in profit) | W2 M1 104 +$4,739 (55%) |
  W3 EU 44 +$3,187 (53%) | W4 N150 65 +$3,863 (55%).
  W1 (tag WM4): 4th-last trading day of the month (day list W_M4_DAYS, copied from the EA) -> BUY 15:00 broker, NO stop (as
    tested), close 21:30. The auto-trader cannot place or size an order without a stop, so the ROW carries a far "demo safety
    stop" (WM4_SAFETY_MULT x A) for sizing/placement only - the paper result never uses it (see watch_trade()).
  W2 (tag WM1): first trading day of the month (W_M1_DAYS) -> SELL 15:00, stop 2.0 x A, close 21:30.
  W3 (tag WEU): day in W_EU_DAYS (German/French-only holiday, UK and US open) and not a live calendar day (B/D/E/F lists) ->
    SELL 11:00, stop 1.0 x A, close 21:30.
  W4 (tag WN150): yesterday's 21:29 broker close is ABOVE the highest (or BELOW the lowest) of the 150 daily 21:29 closes before
    it AND the day before that was NOT already beyond in the same direction (first day of the break only); today (not a live
    calendar day) trade that way at 03:20 broker, stop 1.0 x A, close 21:30. The 21:29 closes come from brent_run's own
    docs/brent_close.json (built from the same Capital.com minute feed).
  W5 (tag WLTD4, v1.13W 21 Nov 2026): day in W_LTD4_DAYS (the day before ICE Brent options expiry, copied from the EA) -> BUY
    10:00 broker, stop 1.0 x A, close 21:30; no calendar test, own position, never conflict-closed. MT4: 106 trades +$4,322.
  A = the same 20-day average range as every live rule. Early-close days (US holidays end ~20:28): a still-open trade shows 'open'
  until the next run (same limitation as every other rule here).
US/UK holiday dates (HOL_AFTER / UK_HOL_BUY / UK_HOL_SELL / UK_HOL_SELL2 / PRE_HOL_BUY) are the EXACT baked-in lists
from the proven EA (BRENT_WED_HOL_v106.mq4), copied verbatim - NOT recomputed from a calendar library (unchanged
from v1.05 - only the entry TIMES for B/D/C moved in v1.06, not these lists). A first attempt (back in v1.05) to
recompute Rule D from pandas + the `holidays` package matched Rule B exactly but did NOT match Rule D (e.g. the
EA's UK_HOL_BUY skips a Boxing-Day-observed buy that a plain calendar would have added, and UK_HOL_SELL is not
simply "the day after every UK_HOL_BUY date") - so the real, MT4-tested lists are used as-is rather than re-derived.
These lists run out at 2027.12.28/29 (B), 2028.01.03 (D), 2028.12.28 (E, UK_HOL_SELL2) and 2028.12.22 (F,
PRE_HOL_BUY) - a future extension (new baked dates from the Brent chat) will be needed before then; until extended,
each list simply stops firing past its own last listed date (same limitation already in the live EA). Past journal
days keep whichever rule version produced them (the `rules` tag written per day in docs/journal_brent.json) - the
v1.05->v1.06 bump above changes nothing about how earlier days are scored."""
import numpy as np, pandas as pd

HOL_AFTER = ("2010.01.04,2010.01.19,2010.02.16,2010.06.01,2010.07.06,2010.09.07,2010.10.12,2010.11.12,2010.11.26,2010.12.27,"
    "2011.01.03,2011.01.18,2011.02.22,2011.05.31,2011.07.05,2011.09.06,2011.10.11,2011.11.14,2011.11.25,2011.12.27,"
    "2012.01.03,2012.01.17,2012.02.21,2012.05.29,2012.07.05,2012.09.04,2012.10.09,2012.11.13,2012.11.23,2012.12.26,"
    "2013.01.02,2013.01.22,2013.02.19,2013.05.28,2013.07.05,2013.09.03,2013.10.15,2013.11.12,2013.11.29,2013.12.26,"
    "2014.01.02,2014.01.21,2014.02.18,2014.05.27,2014.07.07,2014.09.02,2014.10.14,2014.11.12,2014.11.28,2014.12.26,"
    "2015.01.02,2015.01.20,2015.02.17,2015.05.26,2015.07.06,2015.09.08,2015.10.13,2015.11.12,2015.11.27,2015.12.28,"
    "2016.01.04,2016.01.19,2016.02.16,2016.05.31,2016.07.05,2016.09.06,2016.10.11,2016.11.14,2016.11.25,2016.12.27,"
    "2017.01.03,2017.01.17,2017.02.21,2017.05.30,2017.07.05,2017.09.05,2017.10.10,2017.11.13,2017.11.24,2017.12.26,"
    "2018.01.02,2018.01.16,2018.02.20,2018.05.29,2018.07.05,2018.09.04,2018.10.09,2018.11.13,2018.11.23,2018.12.26,"
    "2019.01.02,2019.01.22,2019.02.19,2019.05.28,2019.07.05,2019.09.03,2019.10.15,2019.11.12,2019.11.29,2019.12.26,"
    "2020.01.02,2020.01.21,2020.02.18,2020.05.26,2020.07.06,2020.09.08,2020.10.13,2020.11.12,2020.11.27,2020.12.28,"
    "2021.01.04,2021.01.19,2021.02.16,2021.06.01,2021.06.21,2021.07.06,2021.09.07,2021.10.12,2021.11.12,2021.11.26,"
    "2021.12.27,2022.01.03,2022.01.18,2022.02.22,2022.05.31,2022.06.21,2022.07.05,2022.09.06,2022.10.11,2022.11.14,"
    "2022.11.25,2022.12.27,2023.01.03,2023.01.17,2023.02.21,2023.05.30,2023.06.20,2023.07.05,2023.09.05,2023.10.10,"
    "2023.11.13,2023.11.24,2023.12.26,2024.01.02,2024.01.16,2024.02.20,2024.05.28,2024.06.20,2024.07.05,2024.09.03,"
    "2024.10.15,2024.11.12,2024.11.29,2024.12.26,2025.01.02,2025.01.21,2025.02.18,2025.05.27,2025.06.20,2025.07.07,"
    "2025.09.02,2025.10.14,2025.11.12,2025.11.28,2025.12.26,2026.01.02,2026.01.20,2026.02.17,2026.05.26,2026.06.22,"
    "2026.07.06,2026.09.08,2026.10.13,2026.11.12,2026.11.27,2026.12.28,2027.01.04,2027.01.19,2027.02.16,2027.06.01,"
    "2027.06.21,2027.07.06,2027.09.07,2027.10.12,2027.11.12,2027.11.26,2027.12.27,2028.01.03")                           # rule B, EA source
UK_HOL_BUY = ("2010.04.05,2010.05.03,2010.05.31,2010.08.30,2010.12.28,2011.04.25,2011.04.29,2011.05.02,2011.05.30,2011.08.29,"
    "2011.12.26,2012.01.02,2012.04.09,2012.05.07,2012.06.04,2012.06.05,2012.08.27,2013.04.01,2013.05.06,2013.05.27,"
    "2013.08.26,2014.04.21,2014.05.05,2014.05.26,2014.08.25,2015.04.06,2015.05.04,2015.05.25,2015.08.31,2016.03.28,"
    "2016.05.02,2016.05.30,2016.08.29,2016.12.26,2017.01.02,2017.04.17,2017.05.01,2017.05.29,2017.08.28,2018.04.02,"
    "2018.05.07,2018.05.28,2018.08.27,2019.04.22,2019.05.06,2019.05.27,2019.08.26,2020.04.13,2020.05.08,2020.05.25,"
    "2020.08.31,2021.04.05,2021.05.03,2021.05.31,2021.08.30,2021.12.28,2022.04.18,2022.05.02,2022.06.02,2022.06.03,"
    "2022.08.29,2022.09.19,2022.12.26,2023.01.02,2023.04.10,2023.05.01,2023.05.08,2023.05.29,2023.08.28,2024.04.01,"
    "2024.05.06,2024.05.27,2024.08.26,2025.04.21,2025.05.05,2025.05.26,2025.08.25,2026.04.06,2026.05.04,2026.05.25,"
    "2026.08.31,2027.03.29,2027.05.03,2027.05.31,2027.08.30,2027.12.28")                                                  # rule D buy, EA source
UK_HOL_SELL = ("2010.04.06,2010.05.04,2010.08.31,2010.12.29,2011.01.04,2011.04.26,2011.05.03,2011.08.30,2011.12.28,2012.04.10,"
    "2012.05.08,2012.06.06,2012.08.28,2012.12.27,2013.04.02,2013.05.07,2013.08.27,2013.12.27,2014.04.22,2014.05.06,"
    "2014.08.26,2014.12.29,2015.04.07,2015.05.05,2015.09.01,2015.12.29,2016.03.29,2016.05.03,2016.08.30,2016.12.28,"
    "2017.04.18,2017.05.02,2017.08.29,2017.12.27,2018.04.03,2018.05.08,2018.08.28,2018.12.27,2019.04.23,2019.05.07,"
    "2019.08.27,2019.12.27,2020.04.14,2020.05.11,2020.09.01,2020.12.29,2021.04.06,2021.05.04,2021.08.31,2021.12.29,"
    "2022.01.04,2022.04.19,2022.05.03,2022.06.06,2022.08.30,2022.09.20,2022.12.28,2023.04.11,2023.05.02,2023.05.09,"
    "2023.08.29,2023.12.27,2024.04.02,2024.05.07,2024.08.27,2024.12.27,2025.04.22,2025.05.06,2025.08.26,2025.12.29,"
    "2026.04.07,2026.05.05,2026.09.01,2026.12.29,2027.03.30,2027.05.04,2027.08.31,2027.12.29")                           # rule D sell, EA source
UK_HOL_SELL2 = (
    "2011.01.05,2011.04.27,2011.05.04,2011.06.01,2011.08.31,2012.04.11,2012.05.09,2012.06.07,2012.08.29,2012.12.28,"
    "2013.01.03,2013.04.03,2013.05.08,2013.05.29,2013.08.28,2013.12.30,2014.01.03,2014.04.23,2014.05.07,2014.05.28,"
    "2014.08.27,2014.12.30,2015.04.08,2015.05.06,2015.05.27,2015.09.02,2015.12.30,2016.03.30,2016.05.04,2016.06.01,"
    "2016.08.31,2016.12.29,2017.04.19,2017.05.03,2017.05.31,2017.08.30,2017.12.28,2018.04.04,2018.05.09,2018.05.30,"
    "2018.08.29,2018.12.31,2019.04.24,2019.05.08,2019.05.29,2019.08.28,2019.12.30,2020.04.15,2020.05.12,2020.05.27,"
    "2020.09.02,2020.12.30,2021.04.07,2021.05.05,2021.06.02,2021.09.01,2021.12.30,2022.01.05,2022.04.20,2022.05.04,"
    "2022.06.07,2022.08.31,2022.09.21,2022.12.29,2023.04.12,2023.05.03,2023.05.10,2023.05.31,2023.08.30,2023.12.28,"
    "2024.04.03,2024.05.08,2024.05.29,2024.08.28,2024.12.30,2025.04.23,2025.05.28,2025.08.27,2025.12.30,2026.04.09,"
    "2026.05.06,2026.09.02,2026.12.30,2027.03.31,2027.05.05,2027.06.02,2027.09.01,2027.12.30,2028.01.05,2028.04.19,"
    "2028.05.03,2028.05.31,2028.08.30,2028.12.28")                                                                       # rule E sell, EA source
PRE_HOL_BUY = (
    "2011.01.14,2011.02.18,2011.04.21,2011.04.28,2011.05.27,2011.07.01,2011.08.26,2011.09.02,2011.10.07,2012.04.05,"
    "2012.05.04,2012.05.25,2012.06.01,2012.07.03,2012.08.24,2012.08.31,2012.10.05,2012.11.09,2012.11.21,2012.12.24,"
    "2012.12.31,2013.01.18,2013.02.15,2013.03.28,2013.05.03,2013.05.24,2013.07.03,2013.08.23,2013.08.30,2013.10.11,"
    "2013.11.08,2013.11.27,2013.12.24,2013.12.31,2014.01.17,2014.02.14,2014.04.17,2014.05.02,2014.05.23,2014.07.03,"
    "2014.08.22,2014.08.29,2014.10.10,2014.11.10,2014.11.26,2014.12.24,2015.01.16,2015.02.13,2015.04.02,2015.05.01,"
    "2015.05.22,2015.07.02,2015.08.28,2015.09.04,2015.10.09,2015.11.10,2015.11.25,2015.12.24,2016.02.12,2016.03.24,"
    "2016.04.29,2016.05.27,2016.07.01,2016.08.26,2016.09.02,2016.10.07,2016.11.10,2016.11.23,2016.12.23,2017.01.13,"
    "2017.02.17,2017.04.13,2017.04.28,2017.05.26,2017.07.03,2017.08.25,2017.09.01,2017.10.06,2017.11.09,2017.11.22,"
    "2017.12.22,2018.01.12,2018.02.16,2018.03.29,2018.05.04,2018.05.25,2018.07.03,2018.08.24,2018.08.31,2018.10.05,"
    "2018.11.09,2018.11.21,2018.12.24,2019.01.18,2019.02.15,2019.04.18,2019.05.03,2019.05.24,2019.07.03,2019.08.23,"
    "2019.08.30,2019.10.11,2019.11.08,2019.11.27,2019.12.24,2020.01.17,2020.02.14,2020.04.09,2020.05.07,2020.05.22,"
    "2020.07.02,2020.08.28,2020.09.04,2020.10.09,2020.11.10,2020.11.25,2020.12.24,2021.01.15,2021.02.12,2021.04.01,"
    "2021.04.30,2021.05.28,2021.06.17,2021.07.02,2021.08.27,2021.09.03,2021.10.08,2021.11.10,2021.11.24,2021.12.23,"
    "2021.12.24,2021.12.30,2021.12.31,2022.01.14,2022.02.18,2022.04.14,2022.04.29,2022.05.27,2022.06.01,2022.06.17,"
    "2022.07.01,2022.08.26,2022.09.02,2022.09.16,2022.10.07,2022.11.10,2022.11.23,2022.12.23,2023.01.13,2023.02.17,"
    "2023.04.06,2023.04.28,2023.05.05,2023.05.26,2023.06.16,2023.07.03,2023.08.25,2023.09.01,2023.11.09,2023.11.22,"
    "2023.12.22,2024.01.12,2024.02.16,2024.03.28,2024.05.03,2024.05.24,2024.06.18,2024.07.03,2024.08.23,2024.08.30,"
    "2024.10.11,2024.11.08,2024.11.27,2024.12.24,2025.01.17,2025.02.14,2025.04.17,2025.05.23,2025.06.18,2025.07.03,"
    "2025.08.22,2025.08.29,2025.10.10,2025.11.10,2025.11.26,2025.12.24,2026.01.16,2026.02.13,2026.04.02,2026.05.01,"
    "2026.06.18,2026.07.02,2026.08.28,2026.09.04,2026.10.09,2026.11.10,2026.11.25,2026.12.24,2027.01.15,2027.02.12,"
    "2027.03.25,2027.04.30,2027.05.28,2027.06.17,2027.07.02,2027.08.27,2027.09.03,2027.10.08,2027.11.10,2027.11.24,"
    "2027.12.23,2027.12.24,2027.12.30,2027.12.31,2028.04.13,2028.04.28,2028.05.26,2028.08.25,2028.12.22")                # rule F buy, EA source

def _dateset(s): return frozenset(pd.Timestamp(d.replace('.', '-')) for d in s.split(','))
RULE_B_DAYS, RULE_DBUY_DAYS, RULE_DSELL_DAYS = _dateset(HOL_AFTER), _dateset(UK_HOL_BUY), _dateset(UK_HOL_SELL)
RULE_E_DAYS, RULE_F_DAYS = _dateset(UK_HOL_SELL2), _dateset(PRE_HOL_BUY)
LIST_LAST = dict(B=max(RULE_B_DAYS), Dbuy=max(RULE_DBUY_DAYS), Dsell=max(RULE_DSELL_DAYS), E=max(RULE_E_DAYS), F=max(RULE_F_DAYS))

ADR_DAYS = 20                                          # stop size + rule C's channel
MOVE_WIN = 60                                           # days of 10:00->14:00 moves behind rule A's std dev
MOVE_Z = 0.5
SIG_START_MIN, ENTRY_A_MIN = 10 * 60, 14 * 60           # rule A: move measured 10:00->14:00, entry at 14:00 (unchanged)
ENTRY_BD_MIN = 11 * 60                                  # rules B and D entry 11:00 (v1.06: was 10:00)
ENTRY_E_MIN = 10 * 60                                   # rule E entry 10:00 (unchanged - its own setting, untouched by B/D)
ENTRY_F_MIN = 19 * 60                                   # rule F entry 19:00 broker (pre-holiday drift, unchanged)
C_START_MIN, C_END_MIN = 9 * 60, 19 * 60                # rule C watch window for the break (v1.06: start 09:00, was 10:00)
EXIT_MIN = 21 * 60 + 30                                 # common exit, every rule
STOP_MULT = 1.0                                         # rules A,B,D,E,F stop = this x the 20-day range (unchanged)
BREAK_STOP_MULT = 2.0                                   # rule C stop = this x the 20-day range (v1.06: was 1.0, shared with the others)
USE_CONFLICT_CLOSE = True                               # v1.06, new: an opposite signal closes the open trade and skips itself
ENTRY_LATE = 5                                          # a bar up to 5 min late still counts (same tolerance as gbp_engine)

K_REF1_MIN, K_REF2_MIN = 9 * 60, 10 * 60                # v1.07a rule K+: reference prices at 09:00/10:00 broker (EA K_Ref1_HHMM/K_Ref2_HHMM)
K_LAST_SIGNAL_MIN = 18 * 60                             # last bar checked starts < 18:00 broker (EA K_Last_Entry_HHMM=1800)
K_CLOSE_MIN = 19 * 60                                   # K+'s own exit, 19:00 broker (EA K_Close_HHMM) - EXIT_MIN (21:30) below is the unconditional backstop
K_TH_MULT = 0.8                                         # signal threshold = this x A (EA K_Move_x_Range)
K_STOP_MULT = 2.0                                       # K+ stop = this x A (EA K_Stop_x_Range) - NOT the shared 1.0x used by A/B/D/E/F

AW_WINDOW_MIN = 30                                      # v1.10 rule AW: window after the 14:00 bar (EA AW_Window_Min)
AW_STOP_MULT = 2.0                                      # v1.10 rule AW stop = this x A (EA AW_Stop_x_Range) - not the shared 1.0x
K2_MOVE_MULT = 0.5                                      # v1.10 rule K2: extra move beyond the K+ trigger price = this x A (EA K2_Move_x_Range)
K2_STOP_MULT = 2.0                                      # v1.10 rule K2 stop = this x A (EA K2_Stop_x_Range) - same distance as K+'s own stop
K2_LAST_SIGNAL_MIN = K_LAST_SIGNAL_MIN                  # K2's own last-entry cutoff = the SAME 18:00 broker cutoff K+ itself uses
K2_LOT_X = 0.5                                          # v1.10 rule K2 size = this x a normal trade (EA K2_Lot_x) - NOT a stop multiplier;
# consumed by brent_run.row() (size=K2_LOT_X -> autotrade.py's weight()/plan() halves the USD risk and lot size)

# ---- v1.15 upgrades (27 Nov 2026, EA BRENT_WED_HOL_v115.mq4 lines 65-82) ----
V115_FROM = pd.Timestamp('2026-11-30')                  # first broker day the v1.15 upgrades trade (his push 27 Nov, afternoon: nothing applicable was left today)
USE_A16, USE_B12, USE_C14, USE_A12K, USE_D_LOT, USE_D_LIMIT, USE_E_RALLY, USE_MID = (True,) * 8
A16_ENTRY_MIN, A16_STOP_MULT = 16 * 60, 1.0             # U1: EA lines 65-67
UPG_STOP_MULT = 1.0                                     # U2/U3/U4: EA line 82 (Upg_Stop_x_Range)
B12_MIN, C14_MIN, A12_MIN = 12 * 60, 14 * 60, 12 * 60   # U2 / U3 / U4 checkpoint times
A12_Z, A12_NMIN = 0.5, 30                               # U4: EA line 72; needs at least 30 past m12 values, uses the last 60 (SD_Days)
D_BUY_LOT_X, D_LIMIT_X, D_LIMIT_WAIT = 2.0, 0.05, 30    # U5/U6: EA lines 73-76
E_RALLY_LOT_X, E03_MIN = 2.0, 3 * 60                    # U7: EA line 77
MID_LOW, MID_HIGH, MID_DAYS, MID_MIN_CLOSES = 0.33, 0.67, 250, 120   # U8: EA lines 79-81

# ---- v1.12W WATCH rules (new 19 Nov 2026, demo forward test only - independent of every live rule) ----
W_M4_DAYS = (
    "2018.01.26,2018.02.23,2018.03.26,2018.04.25,2018.05.28,2018.06.26,2018.07.26,2018.08.28,2018.09.25,2018.10.26,"
    "2018.11.27,2018.12.26,2019.01.28,2019.02.25,2019.03.26,2019.04.25,2019.05.28,2019.06.25,2019.07.26,2019.08.27,"
    "2019.09.25,2019.10.28,2019.11.26,2019.12.26,2020.01.28,2020.02.25,2020.03.26,2020.04.27,2020.05.26,2020.06.25,"
    "2020.07.28,2020.08.26,2020.09.25,2020.10.27,2020.11.25,2020.12.28,2021.01.26,2021.02.23,2021.03.26,2021.04.27,"
    "2021.05.26,2021.06.25,2021.07.27,2021.08.26,2021.09.27,2021.10.26,2021.11.25,2021.12.28,2022.01.26,2022.02.23,"
    "2022.03.28,2022.04.26,2022.05.26,2022.06.27,2022.07.26,2022.08.26,2022.09.27,2022.10.26,2022.11.25,2022.12.27,"
    "2023.01.26,2023.02.23,2023.03.28,2023.04.25,2023.05.26,2023.06.27,2023.07.26,2023.08.28,2023.09.26,2023.10.26,"
    "2023.11.27,2023.12.26,2024.01.26,2024.02.26,2024.03.25,2024.04.25,2024.05.28,2024.06.25,2024.07.26,2024.08.27,"
    "2024.09.25,2024.10.28,2024.11.26,2024.12.26,2025.01.28,2025.02.25,2025.03.26,2025.04.25,2025.05.27,2025.06.25,"
    "2025.07.28,2025.08.26,2025.09.25,2025.10.28,2025.11.25,2025.12.26,2026.01.27,2026.02.24,2026.03.26,2026.04.27,"
    "2026.05.26,2026.06.25,2026.07.28,2026.08.26,2026.09.25,2026.10.27,2026.11.25,2026.12.28,2027.01.26,2027.02.23,"
    "2027.03.25,2027.04.27,2027.05.26,2027.06.25,2027.07.27,2027.08.26,2027.09.27,2027.10.26,2027.11.25,2027.12.28,"
    "2028.01.26,2028.02.24,2028.03.28,2028.04.25,2028.05.26,2028.06.27,2028.07.26,2028.08.28,2028.09.26,2028.10.26,"
    "2028.11.27,2028.12.26")
W_M1_DAYS = (
    "2018.01.02,2018.02.01,2018.03.01,2018.04.02,2018.05.01,2018.06.01,2018.07.02,2018.08.01,2018.09.03,2018.10.01,"
    "2018.11.01,2018.12.03,2019.01.02,2019.02.01,2019.03.01,2019.04.01,2019.05.01,2019.06.03,2019.07.01,2019.08.01,"
    "2019.09.02,2019.10.01,2019.11.01,2019.12.02,2020.01.02,2020.02.03,2020.03.02,2020.04.01,2020.05.01,2020.06.01,"
    "2020.07.01,2020.08.03,2020.09.01,2020.10.01,2020.11.02,2020.12.01,2021.01.04,2021.02.01,2021.03.01,2021.04.01,"
    "2021.05.03,2021.06.01,2021.07.01,2021.08.02,2021.09.01,2021.10.01,2021.11.01,2021.12.01,2022.01.03,2022.02.01,"
    "2022.03.01,2022.04.01,2022.05.02,2022.06.01,2022.07.01,2022.08.01,2022.09.01,2022.10.03,2022.11.01,2022.12.01,"
    "2023.01.02,2023.02.01,2023.03.01,2023.04.03,2023.05.01,2023.06.01,2023.07.03,2023.08.01,2023.09.01,2023.10.02,"
    "2023.11.01,2023.12.01,2024.01.02,2024.02.01,2024.03.01,2024.04.01,2024.05.01,2024.06.03,2024.07.01,2024.08.01,"
    "2024.09.02,2024.10.01,2024.11.01,2024.12.02,2025.01.02,2025.02.03,2025.03.03,2025.04.01,2025.05.01,2025.06.02,"
    "2025.07.01,2025.08.01,2025.09.01,2025.10.01,2025.11.03,2025.12.01,2026.01.02,2026.02.02,2026.03.02,2026.04.01,"
    "2026.05.01,2026.06.01,2026.07.01,2026.08.03,2026.09.01,2026.10.01,2026.11.02,2026.12.01,2027.01.04,2027.02.01,"
    "2027.03.01,2027.04.01,2027.05.03,2027.06.01,2027.07.01,2027.08.02,2027.09.01,2027.10.01,2027.11.01,2027.12.01,"
    "2028.01.03,2028.02.01,2028.03.01,2028.04.03,2028.05.01,2028.06.01,2028.07.03,2028.08.01,2028.09.01,2028.10.02,"
    "2028.11.01,2028.12.01")
W_EU_DAYS = (
    "2018.05.01,2018.05.10,2018.05.21,2018.08.15,2018.10.03,2018.11.01,2019.05.01,2019.05.30,2019.06.10,2019.08.15,"
    "2019.10.03,2019.11.01,2020.05.01,2020.05.21,2020.06.01,2020.07.14,2021.05.13,2021.05.24,2021.07.14,2021.11.01,"
    "2022.05.26,2022.06.06,2022.07.14,2022.08.15,2022.10.03,2022.11.01,2023.05.18,2023.07.14,2023.08.15,2023.10.03,"
    "2023.11.01,2024.05.01,2024.05.09,2024.05.20,2024.08.15,2024.10.03,2024.11.01,2025.05.01,2025.05.29,2025.06.09,"
    "2025.07.14,2025.08.15,2025.10.03,2026.05.01,2026.05.14,2026.07.14,2027.05.06,2027.05.17,2027.07.14,2027.11.01,"
    "2028.05.25,2028.06.05,2028.07.14,2028.08.15,2028.10.03,2028.11.01")

W_LTD4_DAYS = (
    "2018.01.25,2018.02.22,2018.03.23,2018.04.24,2018.05.24,2018.06.25,2018.07.25,2018.08.24,2018.09.24,2018.10.25,"
    "2018.11.26,2018.12.21,2019.01.25,2019.02.22,2019.03.25,2019.04.24,2019.05.24,2019.06.24,2019.07.25,2019.08.23,"
    "2019.09.24,2019.10.25,2019.11.25,2019.12.23,2020.01.27,2020.02.24,2020.03.25,2020.04.24,2020.05.22,2020.06.24,"
    "2020.07.27,2020.08.24,2020.09.24,2020.10.26,2020.11.24,2020.12.23,2021.01.25,2021.02.22,2021.03.25,2021.04.26,"
    "2021.05.24,2021.06.24,2021.07.26,2021.08.24,2021.09.24,2021.10.25,2021.11.24,2021.12.23,2022.01.25,2022.02.22,"
    "2022.03.25,2022.04.25,2022.05.25,2022.06.24,2022.07.25,2022.08.24,2022.09.26,2022.10.25,2022.11.24,2022.12.22,"
    "2023.01.25,2023.02.22,2023.03.27,2023.04.24,2023.05.24,2023.06.26,2023.07.25,2023.08.24,2023.09.25,2023.10.25,"
    "2023.11.24,2023.12.21,2024.01.25,2024.02.23,2024.03.22,2024.04.24,2024.05.24,2024.06.24,2024.07.25,2024.08.23,"
    "2024.09.24,2024.10.25,2024.11.25,2024.12.23,2025.01.27,2025.02.24,2025.03.25,2025.04.24,2025.05.23,2025.06.24,"
    "2025.07.25,2025.08.22,2025.09.24,2025.10.27,2025.11.24,2025.12.23,2026.01.26,2026.02.23,2026.03.25,2026.04.24,"
    "2026.05.22,2026.06.24,2026.07.27,2026.08.24,2026.09.24,2026.10.26,2026.11.24,2026.12.23,2027.01.25,2027.02.22,"
    "2027.03.23,2027.04.26,2027.05.24,2027.06.24,2027.07.26,2027.08.24,2027.09.24,2027.10.25,2027.11.24,2027.12.23,"
    "2028.01.25,2028.02.23,2028.03.27,2028.04.24,2028.05.24,2028.06.26,2028.07.25,2028.08.24,2028.09.25,2028.10.25,"
    "2028.11.24,2028.12.21")   # v1.13W W5: day before ICE Brent options expiry, copied as-is from the EA (BRENT_WED_HOL_v113W.mq4 md5 775dc705...)

WATCH_M4_DAYS, WATCH_M1_DAYS, WATCH_EU_DAYS = _dateset(W_M4_DAYS), _dateset(W_M1_DAYS), _dateset(W_EU_DAYS)
WATCH_LTD4_DAYS = _dateset(W_LTD4_DAYS)
WATCH_LAST = dict(M4=max(WATCH_M4_DAYS), M1=max(WATCH_M1_DAYS), EU=max(WATCH_EU_DAYS), LTD4=max(WATCH_LTD4_DAYS))
M4_ENTRY_MIN, M1_ENTRY_MIN, EU_ENTRY_MIN, N150_ENTRY_MIN = 15 * 60, 15 * 60, 11 * 60, 3 * 60 + 20    # EA lines 71, 74, 77, 81 (broker clock)
M4_STOP_MULT, M1_STOP_MULT, EU_STOP_MULT, N150_STOP_MULT = 0.0, 2.0, 1.0, 1.0   # EA lines 72, 75, 78, 82 (0 = no stop, as tested)
LTD4_ENTRY_MIN, LTD4_STOP_MULT = 10 * 60, 1.0                  # W5 (v1.13W): BUY 10:00 broker, stop 1.0 x A, close 21:30 (EA lines 83-85)
N150_DAYS = 150                                         # EA line 80
WM4_SAFETY_MULT = 2.0                                   # demo-order safety stop for W1 only (x A); NOT part of the tested rule, see watch_trade(). Python replay of the 106 MT4 W1 days: worst adverse move 1.31 x A, so 2.0 x A is never touched
WATCH_RULES = ('WM4', 'WM1', 'WEU', 'WN150', 'WLTD4')

RULE_NAME = {'A': 'Rule A · Wednesday momentum', 'B': 'Rule B · day after US holiday',
             'C': 'Rule C · 20-day range break', 'Dbuy': 'Rule D · UK bank holiday (buy)', 'Dsell': 'Rule D · UK bank holiday (sell next day)',
             'E': 'Rule E · 2nd day after UK holiday (sell)', 'F': 'Rule F · day before holiday (buy)',
             'K': 'Rule K+ · overextension fade (new 9 Nov 2026 - thin before 2026)',
             'AW': 'Rule AW · Wednesday re-entry (new 9 Nov 2026 - 2022-heavy)',
             'K2': 'Rule K2 · K+ add-on fade, half size (new 9 Nov 2026 - 2022-heavy)',
             'A16': 'Rule A16 · Wednesday add-on at 16:00 (v1.15)', 'B12': 'Rule B12 · day-after-US-holiday add-on at 12:00 (v1.15)',
             'C14': 'Rule C14 · range-break add-on at 14:00 (v1.15)', 'A12K': 'Rule A12K · early Wednesday start at 12:00 (v1.15)',
             'WM4': 'W1 · month-end buy (DEMO forward test)', 'WM1': 'W2 · first-day-of-month sell (DEMO forward test)',
             'WEU': 'W3 · Europe-only holiday sell (DEMO forward test)', 'WN150': 'W4 · 150-day close break (DEMO forward test)',
             'WLTD4': 'W5 · day before Brent options expiry buy (DEMO forward test)'}

# ---------------- calendar lookups (exact EA lists above) ----------------
def rule_flags(day):
    """(ruleB, ruleD_buy, ruleD_sell, ruleE, ruleF) for broker day `day` - straight lookups in the EA's own date sets."""
    d = pd.Timestamp(day).normalize()
    return (bool(d in RULE_B_DAYS), bool(d in RULE_DBUY_DAYS), bool(d in RULE_DSELL_DAYS),
            bool(d in RULE_E_DAYS), bool(d in RULE_F_DAYS))

def day_type(day):
    day = pd.Timestamp(day).normalize()
    ruleB, d_buy, d_sell, ruleE, ruleF = rule_flags(day)
    return dict(wed=bool(day.dayofweek == 2), ruleB=ruleB, ruleD_buy=d_buy, ruleD_sell=d_sell, ruleE=ruleE, ruleF=ruleF,
                list_expiring=bool(day >= min(LIST_LAST.values()) - pd.Timedelta(days=30)))

# ---------------- history stats (ADR / channel / rule-A move std) ----------------
def adr(daily_hl, day, n=ADR_DAYS):
    """Average daily (high-low) range of the `n` broker days BEFORE `day`. daily_hl: DataFrame indexed by day, cols h,l."""
    d = daily_hl[daily_hl.index < pd.Timestamp(day).normalize()].sort_index()
    if len(d) < n: return np.nan
    return float((d.h - d.l).iloc[-n:].mean())

def channel(daily_hl, day, n=ADR_DAYS):
    """(hi, lo) of the `n` broker days BEFORE `day` (rule C's range)."""
    d = daily_hl[daily_hl.index < pd.Timestamp(day).normalize()].sort_index()
    if len(d) < n: return np.nan, np.nan
    w = d.iloc[-n:]; return float(w.h.max()), float(w.l.min())

def move_std(moves, day, n=MOVE_WIN):
    """std dev of the `n` 10:00->14:00 moves BEFORE `day`. moves: Series indexed by day."""
    v = moves[moves.index < pd.Timestamp(day).normalize()].dropna()
    if len(v) < n: return np.nan
    return float(v.iloc[-n:].std(ddof=1))

# ---------------- today's bars ----------------
def bar_open_at(b, day, minute):
    """Open price of the first closed minute bar at/after broker `minute` of `day` (within ENTRY_LATE min), else NaN."""
    t = pd.Timestamp(day).normalize() + pd.Timedelta(minutes=minute)
    a = int(b.index.searchsorted(t))
    if a >= len(b) or b.index[a] - t > pd.Timedelta(minutes=ENTRY_LATE): return np.nan
    return float(b.o.values[a])

def bar_close_at(b, day, minute):
    """Close price of the first closed minute bar at/after broker `minute` of `day` (within ENTRY_LATE min), else
    NaN. v1.10 rule AW's own reference (the CLOSE of the 14:00 bar, not its open) - companion to bar_open_at()."""
    t = pd.Timestamp(day).normalize() + pd.Timedelta(minutes=minute)
    a = int(b.index.searchsorted(t))
    if a >= len(b) or b.index[a] - t > pd.Timedelta(minutes=ENTRY_LATE): return np.nan
    return float(b.c.values[a])

def today_move_10_14(b, day):
    o10, o14 = bar_open_at(b, day, SIG_START_MIN), bar_open_at(b, day, ENTRY_A_MIN)
    return np.nan if not (np.isfinite(o10) and np.isfinite(o14)) else o14 - o10

def wed_signal(move, sd):
    if not (np.isfinite(move) and np.isfinite(sd) and sd > 0): return 0
    return 1 if move > MOVE_Z * sd else -1 if move < -MOVE_Z * sd else 0

def close_before(b, day, minute):
    """Close of the last closed minute bar that STARTS before broker `minute` of `day` (= the EA's Close[1] at the first tick of `minute`), else NaN."""
    t = pd.Timestamp(day).normalize() + pd.Timedelta(minutes=minute)
    a = int(b.index.searchsorted(t)) - 1
    if a < 0 or t - b.index[a] > pd.Timedelta(minutes=ENTRY_LATE): return np.nan
    return float(b.c.values[a])

def move_std12(m12, day, n=MOVE_WIN, nmin=A12_NMIN):
    """U4: std dev (ddof=1) of the last <=n 10:00->12:00 moves BEFORE `day` (needs at least nmin) - the EA's s12."""
    v = m12[m12.index < pd.Timestamp(day).normalize()].dropna()
    if len(v) < nmin: return np.nan
    return float(v.iloc[-n:].std(ddof=1))

def mid_pos(dcl, day):
    """U8: position of yesterday's 21:29 close inside the min/max of the last MID_DAYS daily closes (yesterday included), 0..1; None = fewer than
    MID_MIN_CLOSES closes (or flat range) = no skip, exactly like the EA. dcl = Series of daily 21:29 closes indexed by broker day."""
    if dcl is None: return None
    v = dcl[dcl.index < pd.Timestamp(day).normalize()].dropna().sort_index().values
    if len(v) < MID_MIN_CLOSES: return None
    w = v[-MID_DAYS:]; mx, mn = float(w.max()), float(w.min())
    return None if not mx > mn else float((v[-1] - mn) / (mx - mn))

def is_mid(pos): return pos is not None and MID_LOW <= pos <= MID_HIGH

# ---------------- trade construction ----------------
def fixed_trade(b, day, entry_min, direction, A, rk, cost, mult=STOP_MULT):
    """A trade entered at a fixed broker-clock minute (first bar within ENTRY_LATE min), stop mult*A, exit EXIT_MIN
    broker (or stopped first, checked low/high every minute). b: today's closed minute bars (idx broker time, o h l c)."""
    if direction == 0 or not np.isfinite(A) or A <= 0 or not len(b): return None
    day = pd.Timestamp(day).normalize(); t0 = day + pd.Timedelta(minutes=entry_min); te = day + pd.Timedelta(minutes=EXIT_MIN)
    a = int(b.index.searchsorted(t0))
    if a >= len(b) or b.index[a] - t0 > pd.Timedelta(minutes=ENTRY_LATE): return None
    s = 1 if direction > 0 else -1; en = float(b.o.values[a]); sd = mult * A; st = en - s * sd
    e = int(b.index.searchsorted(te))
    H, L = b.h.values[a:e], b.l.values[a:e]
    out = dict(t=b.index[a], dir=s, rule=rk, name=RULE_NAME[rk], entry=en, stop=st, stop0=st, exit=None, exit_t=None, status='open', A=A, cost=cost)
    hit = None
    for j in range(len(H)):
        if (L[j] <= st) if s > 0 else (H[j] >= st): hit = ('stopped', st, j); break
    if hit: out.update(status=hit[0], exit=hit[1], exit_t=b.index[a + hit[2]])
    elif e < len(b): out.update(status='exit', exit=float(b.o.values[e]), exit_t=b.index[e])
    if out['exit'] is not None: out['res'] = s * (out['exit'] - en) - cost
    return out

def range_break_trade(b, day, hi, lo, A, cost, mult=BREAK_STOP_MULT):
    """Rule C: price inside [lo,hi] at C_START_MIN; first 1-min CLOSE beyond the range between C_START_MIN and
    C_END_MIN -> enter at the NEXT minute, in the break's direction; stop mult*A (v1.06: 2.0x); exit 21:30 or
    stopped first (same checks as fixed_trade)."""
    if not (np.isfinite(hi) and np.isfinite(lo) and np.isfinite(A) and A > 0) or not len(b): return None
    day = pd.Timestamp(day).normalize(); t0 = day + pd.Timedelta(minutes=C_START_MIN); t1 = day + pd.Timedelta(minutes=C_END_MIN)
    a0 = int(b.index.searchsorted(t0))
    if a0 >= len(b) or b.index[a0] - t0 > pd.Timedelta(minutes=ENTRY_LATE): return None
    if not (lo <= b.c.values[a0] <= hi): return None           # already outside the range at C_START_MIN - rule C sits out today
    win = b[(b.index >= t0) & (b.index < t1)]
    brk = None
    for j in range(1, len(win)):
        c = win.c.values[j]
        if c > hi: brk = (1, j); break
        if c < lo: brk = (-1, j); break
    if brk is None: return None
    s, j = brk; a = int(b.index.searchsorted(win.index[j])) + 1
    if a >= len(b): return None
    en = float(b.o.values[a]); sd = mult * A; st = en - s * sd
    te = day + pd.Timedelta(minutes=EXIT_MIN); e = int(b.index.searchsorted(te))
    H, L = b.h.values[a:e], b.l.values[a:e]
    out = dict(t=b.index[a], dir=s, rule='C', name=RULE_NAME['C'], entry=en, stop=st, stop0=st, exit=None, exit_t=None, status='open', A=A, cost=cost)
    hit = None
    for k in range(len(H)):
        if (L[k] <= st) if s > 0 else (H[k] >= st): hit = ('stopped', st, k); break
    if hit: out.update(status=hit[0], exit=hit[1], exit_t=b.index[a + hit[2]])
    elif e < len(b): out.update(status='exit', exit=float(b.o.values[e]), exit_t=b.index[e])
    if out['exit'] is not None: out['res'] = s * (out['exit'] - en) - cost
    return out

def _run_from(b, day, a, s, en, A, mult, rk, cost, end_min=EXIT_MIN, end_status='exit'):
    """Same mechanics as fixed_trade() but entered at bar index `a` at price `en` (v1.15 trades that need their own entry price or exit time)."""
    st = en - s * mult * A
    te = pd.Timestamp(day).normalize() + pd.Timedelta(minutes=end_min); e = int(b.index.searchsorted(te))
    H, L = b.h.values[a:e], b.l.values[a:e]
    out = dict(t=b.index[a], dir=s, rule=rk, name=RULE_NAME[rk], entry=en, stop=st, stop0=st, exit=None, exit_t=None, status='open', A=A, cost=cost)
    hit = None
    for j in range(len(H)):
        if (L[j] <= st) if s > 0 else (H[j] >= st): hit = (st, j); break
    if hit: out.update(status='stopped', exit=hit[0], exit_t=b.index[a + hit[1]])
    elif e < len(b): out.update(status=end_status, exit=float(b.o.values[e]), exit_t=b.index[e])
    if out['exit'] is not None: out['res'] = s * (out['exit'] - en) - cost
    return out

def d_buy_trade(b, day, A, cost):
    """Rule D UK-holiday BUY with U5 (2x size) + U6 (limit entry): target = 11:00 bar open - D_LIMIT_X*A; the first bar before 11:30 whose LOW reaches it
    fills at the target (or at the bar open if it opened below it); no fill by 11:30 -> market at the first bar from 11:30 on. Stop 1.0 A from the fill."""
    if not (np.isfinite(A) and A > 0) or not len(b): return None
    day = pd.Timestamp(day).normalize(); t0 = day + pd.Timedelta(minutes=ENTRY_BD_MIN); tw = t0 + pd.Timedelta(minutes=D_LIMIT_WAIT)
    a0 = int(b.index.searchsorted(t0))
    if a0 >= len(b) or b.index[a0] - t0 > pd.Timedelta(minutes=ENTRY_LATE): return None
    lim = float(b.o.values[a0]) - D_LIMIT_X * A
    a, en, how = None, None, 'limit'
    for i in range(a0, len(b)):
        if b.index[i] >= tw: break
        if b.l.values[i] <= lim: a, en = i, min(float(b.o.values[i]), lim); break
    if a is None:
        a = int(b.index.searchsorted(tw)); how = 'market'
        if a >= len(b): return None
        en = float(b.o.values[a])
    t = _run_from(b, day, a, 1, en, A, STOP_MULT, 'Dbuy', cost)
    t['lot'] = D_BUY_LOT_X; t['fill'] = how
    return t

def a12k_trade(b, day, A, sd12, awdir, cost):
    """U4 A12K (Wednesday only - the caller checks): see the module docstring. awdir = rule A's own direction today (0 = no A signal, or not known yet:
    before the 14:00 bar exists the trade simply stays open)."""
    if not (np.isfinite(A) and A > 0 and np.isfinite(sd12) and sd12 > 0) or not len(b): return None
    day = pd.Timestamp(day).normalize()
    o10, o12 = bar_open_at(b, day, SIG_START_MIN), bar_open_at(b, day, A12_MIN)
    if not (np.isfinite(o10) and np.isfinite(o12)): return None
    m12 = o12 - o10
    if not abs(m12) > A12_Z * sd12: return None
    s = 1 if m12 > 0 else -1; a = int(b.index.searchsorted(day + pd.Timedelta(minutes=A12_MIN)))
    keep = (awdir == s)
    t = _run_from(b, day, a, s, float(b.o.values[a]), A, UPG_STOP_MULT, 'A12K', cost,
                  end_min=(EXIT_MIN if keep else ENTRY_A_MIN), end_status=('exit' if keep else 'closed (A12K cut)'))
    t['tag'] = 'A12K'
    return t

# ---------------- rule K+ (v1.07a, new 9 Nov 2026 - independent of A-F/C, see module docstring) ----------------
def kfade_trade(b, day, dt, A, c_entry_t, cost, mult=K_STOP_MULT, th_mult=K_TH_MULT):
    """Rule K+ overextension fade. b: today's closed minute bars. dt = day_type(...) for the day (Wednesday/calendar
    flags). A = the same ADR20 the other rules use. c_entry_t = rule C's own entry time today if it fired, else
    None (used only to check whether C already opened BEFORE the moment K+'s signal would fire - a C trade after
    that moment does not cancel K+, per spec). Returns one trade dict or None - at most one K+ trade/day (first
    touch only), own 'K' rule tag and 'KFADE' position tag so autotrade.py tracks it as a separate position from
    any same-day A-F/C trade (autotrade keys each position by market+day+time+side+tag-or-name, already supports
    N simultaneous positions per market - no autotrade.py change needed, see autotrade.py's key_of())."""
    if dt['wed'] or dt['ruleB'] or dt['ruleD_buy'] or dt['ruleD_sell'] or dt['ruleE'] or dt['ruleF']: return None    # skip the day entirely
    if not (np.isfinite(A) and A > 0) or not len(b): return None
    day = pd.Timestamp(day).normalize()
    ref1, ref2 = bar_open_at(b, day, K_REF1_MIN), bar_open_at(b, day, K_REF2_MIN)
    if not (np.isfinite(ref1) or np.isfinite(ref2)): return None
    th = th_mult * A
    t0, t1 = day + pd.Timedelta(minutes=K_REF1_MIN + 1), day + pd.Timedelta(minutes=K_LAST_SIGNAL_MIN)
    win = b[(b.index >= t0) & (b.index < t1)]                  # every closed bar from 09:01 up to (not incl.) 18:00
    sig, j = 0, None
    for i in range(len(win)):
        tt = win.index[i]; h, l = win.h.values[i], win.l.values[i]
        if np.isfinite(ref1):
            if h >= ref1 + th: sig, j = -1, i; break
            if l <= ref1 - th: sig, j = 1, i; break
        if (tt.hour * 60 + tt.minute > K_REF2_MIN) and np.isfinite(ref2):
            if h >= ref2 + th: sig, j = -1, i; break
            if l <= ref2 - th: sig, j = 1, i; break
    if sig == 0: return None
    if c_entry_t is not None and c_entry_t <= win.index[j]: return None       # rule C already opened by the moment K+ would signal -> skip K+ today
    a = int(b.index.searchsorted(win.index[j])) + 1
    if a >= len(b): return None
    en = float(b.o.values[a]); sd = mult * A; st = en - sig * sd
    te = day + pd.Timedelta(minutes=K_CLOSE_MIN); e = int(b.index.searchsorted(te))
    H, L = b.h.values[a:e], b.l.values[a:e]
    out = dict(t=b.index[a], dir=sig, rule='K', name=RULE_NAME['K'], entry=en, stop=st, stop0=st, exit=None, exit_t=None,
               status='open', A=A, cost=cost, tag='KFADE', trig=float(win.c.values[j]))   # v1.10: 'trig' = close of the SIGNAL bar, for k2_trade()
    hit = None
    for k in range(len(H)):
        if (L[k] <= st) if sig > 0 else (H[k] >= st): hit = ('stopped', st, k); break
    if hit: out.update(status=hit[0], exit=hit[1], exit_t=b.index[a + hit[2]])
    elif e < len(b): out.update(status='exit', exit=float(b.o.values[e]), exit_t=b.index[e])
    if out['exit'] is not None: out['res'] = sig * (out['exit'] - en) - cost
    return out

# ---------------- rule AW (v1.10, new 9 Nov 2026 - independent of A-F/K+/K2, see module docstring) ----------------
def aw_trade(b, day, dt, A, awdir, cost, mult=AW_STOP_MULT, window=AW_WINDOW_MIN):
    """Rule AW - Wednesday re-entry. awdir = rule A's OWN direction today (wed_signal()'s return value, passed
    through by run_day() regardless of whether fixed_trade() for 'A' itself returned a trade - the EA arms off the
    signal condition, not off OrderSend()'s success). dt = day_type(...) for the day. Reference = CLOSE of the
    14:00 broker bar. Walks every closed bar from 14:01 to 14:00+window broker (inclusive); first bar whose close
    crosses back through the reference AGAINST awdir (long: close < ref; short: close > ref) -> a 2nd trade IN
    awdir'S OWN DIRECTION at the next bar's open. First touch only - at most one AW trade/day. Returns one trade
    dict or None. Own 'AW' rule/tag (EA magic+7) so autotrade.py tracks it as a separate position - no autotrade.py
    change needed, same key_of() reasoning as kfade_trade()."""
    if awdir == 0 or not (np.isfinite(A) and A > 0) or not len(b): return None
    if dt['ruleB'] or dt['ruleD_buy'] or dt['ruleD_sell'] or dt['ruleE'] or dt['ruleF']: return None    # EA IsCalendarDay() check
    day = pd.Timestamp(day).normalize()
    ref = bar_close_at(b, day, ENTRY_A_MIN)
    if not np.isfinite(ref): return None
    t1 = day + pd.Timedelta(minutes=ENTRY_A_MIN + window)
    win = b[(b.index > day + pd.Timedelta(minutes=ENTRY_A_MIN)) & (b.index <= t1)]      # closed bars 14:01..14:00+window
    sig, j = 0, None
    for i in range(len(win)):
        if (win.c.values[i] - ref) * awdir < 0: sig, j = awdir, i; break                 # back through ref AGAINST awdir -> re-enter IN awdir
    if sig == 0: return None
    a = int(b.index.searchsorted(win.index[j])) + 1
    if a >= len(b): return None
    en = float(b.o.values[a]); sd = mult * A; st = en - sig * sd
    te = day + pd.Timedelta(minutes=EXIT_MIN); e = int(b.index.searchsorted(te))
    H, L = b.h.values[a:e], b.l.values[a:e]
    out = dict(t=b.index[a], dir=sig, rule='AW', name=RULE_NAME['AW'], entry=en, stop=st, stop0=st, exit=None, exit_t=None,
               status='open', A=A, cost=cost, tag='AW')
    hit = None
    for k in range(len(H)):
        if (L[k] <= st) if sig > 0 else (H[k] >= st): hit = ('stopped', st, k); break
    if hit: out.update(status=hit[0], exit=hit[1], exit_t=b.index[a + hit[2]])
    elif e < len(b): out.update(status='exit', exit=float(b.o.values[e]), exit_t=b.index[e])
    if out['exit'] is not None: out['res'] = sig * (out['exit'] - en) - cost
    return out

# ---------------- rule K2 (v1.10, new 9 Nov 2026 - independent of A-F/K+/AW, see module docstring) ----------------
def k2_trade(b, day, dt, A, k_trade, c_entry_t, cost, mult=K2_STOP_MULT, th_mult=K2_MOVE_MULT):
    """Rule K2 - K+ add-on fade at HALF size. k_trade = kfade_trade()'s own return value for today (None if K+
    did not trade). c_entry_t = rule C's own entry time today if it fired, else None - K2 skips the WHOLE day if
    rule C traded at all (unconditional - unlike kfade_trade()'s own timing-gated check against c_entry_t).
    Trigger = k_trade['trig'] (close of the bar that triggered K+). From the bar AFTER the K+ entry bar until
    K2_LAST_SIGNAL_MIN (18:00 broker, the same cutoff K+ itself uses): if price runs a further th_mult*A beyond the
    trigger IN THE SAME DIRECTION AS THE ORIGINAL STRETCH K+ faded against -> a 2nd fade, SAME direction as K+, at
    the next bar's open. First touch only - at most one K2 trade/day. Stop = mult*A (same 2.0x distance as K+'s
    own stop - the half size is in the LOT SIZE only, see tag='K2' below, never the stop distance). Exit EXIT_MIN
    (21:30 - NOT K+'s own 19:00, per spec). Returns one trade dict or None. Own 'K2' rule/tag (EA magic+4) -
    brent_run.row() turns tag='K2' into size=K2_LOT_X so autotrade.py halves the risk; no autotrade.py change
    needed, same key_of() reasoning as kfade_trade()."""
    if k_trade is None or not (np.isfinite(A) and A > 0) or not len(b): return None
    if dt['wed'] or dt['ruleB'] or dt['ruleD_buy'] or dt['ruleD_sell'] or dt['ruleE'] or dt['ruleF']: return None
    if c_entry_t is not None: return None                   # rule C traded today at all -> no K2 (unconditional, per spec)
    trig, kdir = k_trade.get('trig'), k_trade['dir']
    if trig is None or not np.isfinite(trig): return None
    day = pd.Timestamp(day).normalize()
    t1 = day + pd.Timedelta(minutes=K2_LAST_SIGNAL_MIN)
    win = b[(b.index > k_trade['t']) & (b.index < t1)]      # strictly after the K+ entry bar, up to (not incl.) 18:00
    th = th_mult * A; kmove = -kdir                          # kmove = the ORIGINAL stretch direction K+ itself faded against
    sig, j = 0, None
    for i in range(len(win)):
        h, l = win.h.values[i], win.l.values[i]
        if (kmove > 0 and h >= trig + th) or (kmove < 0 and l <= trig - th): sig, j = kdir, i; break   # same direction as K+
    if sig == 0: return None
    a = int(b.index.searchsorted(win.index[j])) + 1
    if a >= len(b): return None
    en = float(b.o.values[a]); sd = mult * A; st = en - sig * sd
    te = day + pd.Timedelta(minutes=EXIT_MIN); e = int(b.index.searchsorted(te))
    H, L = b.h.values[a:e], b.l.values[a:e]
    out = dict(t=b.index[a], dir=sig, rule='K2', name=RULE_NAME['K2'], entry=en, stop=st, stop0=st, exit=None, exit_t=None,
               status='open', A=A, cost=cost, tag='K2')
    hit = None
    for k in range(len(H)):
        if (L[k] <= st) if sig > 0 else (H[k] >= st): hit = ('stopped', st, k); break
    if hit: out.update(status=hit[0], exit=hit[1], exit_t=b.index[a + hit[2]])
    elif e < len(b): out.update(status='exit', exit=float(b.o.values[e]), exit_t=b.index[e])
    if out['exit'] is not None: out['res'] = sig * (out['exit'] - en) - cost
    return out

# ---------------- WATCH rules W1-W4 (v1.12W, new 19 Nov 2026 - demo forward test, independent of every live rule) ----------------
def watch_trade(b, day, entry_min, direction, A, rk, cost, mult):
    """One watch trade at a fixed broker minute, closed 21:30 broker (or stopped first). Same mechanics as fixed_trade().
    mult <= 0 = NO STOP (W1, exactly as MT4-tested): the paper result then never stops out, but the returned row still
    carries a far safety stop (WM4_SAFETY_MULT x A, 'nostop': True) because the demo auto-trader needs a stop level to place
    and size an order - that stop is a demo-order safeguard only and is not used for the paper result. Tag = the rule key."""
    if mult and mult > 0:
        t = fixed_trade(b, day, entry_min, direction, A, rk, cost, mult)
    else:
        t = fixed_trade(b, day, entry_min, direction, A, rk, cost, 1e9)      # a stop so far away it can never fire
        if t:
            sf = t['entry'] - t['dir'] * WM4_SAFETY_MULT * A
            t.update(stop=sf, stop0=sf, nostop=True)
    if t: t['tag'] = rk
    return t

def wn150_dir(dcl, day, n=N150_DAYS):
    """W4 signal for broker `day` from the daily 21:29 closes (Series indexed by broker day, days BEFORE `day` only):
    +1/-1 if yesterday's close is beyond the high/low of the n closes before it AND the day before was not already beyond in
    the same direction (EA TBreakN(k) != 0 and != TBreakN(k-1)); 0 = no signal; None = fewer than n+2 closes yet (warming up).
    k-n-1 >= 0 in the EA = at least n+2 closes."""
    v = dcl[dcl.index < pd.Timestamp(day).normalize()].dropna().sort_index().values
    if len(v) < n + 2: return None
    def brk(k):
        w = v[k - n:k]
        return 1 if v[k] > w.max() else -1 if v[k] < w.min() else 0
    k = len(v) - 1; nY, nP = brk(k), brk(k - 1)
    return nY if (nY != 0 and nY != nP) else 0

def watch_trades(b, day, dt, A, dcl, cost):
    """All four watch rules for `day`. Calendar-list days (live B/D/E/F lists) are skipped for W3/W4 only, exactly as the EA
    (W1/W2 have no calendar test). dcl = daily 21:29 closes Series (None = not built yet -> W4 sits out)."""
    day = pd.Timestamp(day).normalize(); out = []
    cal = bool(dt['ruleB'] or dt['ruleD_buy'] or dt['ruleD_sell'] or dt['ruleE'] or dt['ruleF'])
    if day in WATCH_M4_DAYS:
        t = watch_trade(b, day, M4_ENTRY_MIN, +1, A, 'WM4', cost, M4_STOP_MULT)
        if t: out.append(t)
    if day in WATCH_M1_DAYS:
        t = watch_trade(b, day, M1_ENTRY_MIN, -1, A, 'WM1', cost, M1_STOP_MULT)
        if t: out.append(t)
    if day in WATCH_EU_DAYS and not cal:
        t = watch_trade(b, day, EU_ENTRY_MIN, -1, A, 'WEU', cost, EU_STOP_MULT)
        if t: out.append(t)
    if day in WATCH_LTD4_DAYS:                                  # W5: no calendar test (same as W1/W2), BUY, own position, no conflict-close
        t = watch_trade(b, day, LTD4_ENTRY_MIN, +1, A, 'WLTD4', cost, LTD4_STOP_MULT)
        if t: out.append(t)
    if not cal and dcl is not None:
        nd = wn150_dir(dcl, day)
        if nd:
            t = watch_trade(b, day, N150_ENTRY_MIN, nd, A, 'WN150', cost, N150_STOP_MULT)
            if t: out.append(t)
    return out

# ---------------- conflict-close (v1.06, new) ----------------
def apply_conflict_close(trades):
    """A new signal opposite an earlier-still-open trade from the SAME day closes that trade (at the new signal's
    price/time) and is itself skipped. Mirrors the EA's Open(): it loops every open order and closes any opposite
    one before deciding whether to place the new one. Walks today's trades in entry-time order; a trade is 'still
    open' at time T if its own exit_t is None (never resolved) or later than T."""
    if not USE_CONFLICT_CLOSE or len(trades) < 2: return trades
    kept = []
    for tr in sorted(trades, key=lambda t: t['t']):
        hit = False
        for k in kept:
            if k.get('_closed'): continue
            still_open = (k['exit_t'] is None) or (k['exit_t'] > tr['t'])
            opposite = (tr['dir'] > 0 and k['dir'] < 0) or (tr['dir'] < 0 and k['dir'] > 0)
            if still_open and opposite:
                k['status'] = 'closed (conflict)'; k['exit'] = tr['entry']; k['exit_t'] = tr['t']
                k['res'] = k['dir'] * (k['exit'] - k['entry']) - k.get('cost', 0)
                k['_closed'] = True; hit = True
        if hit: continue                                      # the new signal is skipped entirely
        kept.append(tr)
    for k in kept: k.pop('_closed', None)
    return kept

def run_day(b, day, dt, A, hi, lo, sd, cost=0.08, dcl=None, watch=True, sd12=float('nan'), mid=False, v115=False):
    """b: today's closed minute bars. dt = day_type(...) for the day. A = ADR20; (hi,lo) = rule C's 20-day channel;
    sd = rule A's 60-day move std. Returns the list of trade dicts that fired today (0-N; A-F+C conflict-closed,
    K+ (v1.07a) and AW/K2 (v1.10) appended after - all three independent, never conflict-closed, see
    kfade_trade()/aw_trade()/k2_trade()). v1.15 (v115=True, new 27 Nov 2026): sd12 = U4's 12:00 move std, mid = U8's mid-range flag (True = skip the rule-A
    family today); the A16/B12/C14/A12K add-ons are appended after K2 (own positions, never conflict-closed); v115=False = the v1.10 engine, unchanged."""
    trades = []
    if dt['ruleD_buy']:
        t = d_buy_trade(b, day, A, cost) if (v115 and USE_D_LIMIT) else fixed_trade(b, day, ENTRY_BD_MIN, +1, A, 'Dbuy', cost)
        if t:
            if v115 and USE_D_LOT and 'lot' not in t: t['lot'] = D_BUY_LOT_X
            trades.append(t)
    if dt['ruleD_sell']:
        t = fixed_trade(b, day, ENTRY_BD_MIN, -1, A, 'Dsell', cost)
        if t: trades.append(t)
    if dt['ruleB']:
        t = fixed_trade(b, day, ENTRY_BD_MIN, -1, A, 'B', cost)
        if t: trades.append(t)
    if dt['ruleE']:
        t = fixed_trade(b, day, ENTRY_E_MIN, -1, A, 'E', cost)
        if t:
            if v115 and USE_E_RALLY:                      # U7: 2x when the 09:59 close is at/above the 03:00 bar's close
                c03, c1 = bar_close_at(b, day, E03_MIN), close_before(b, day, ENTRY_E_MIN)
                if np.isfinite(c03) and np.isfinite(c1) and c1 >= c03: t['lot'] = E_RALLY_LOT_X
            trades.append(t)
    awdir = 0                                              # v1.10 rule AW arms off rule A's OWN signal, below
    skipA = bool(v115 and USE_MID and mid)                  # U8: mid-range day -> the whole rule-A family sits out
    if dt['wed'] and not skipA:
        awdir = wed_signal(today_move_10_14(b, day), sd)
        if awdir:
            t = fixed_trade(b, day, ENTRY_A_MIN, awdir, A, 'A', cost)
            if t: trades.append(t)
    tC = range_break_trade(b, day, hi, lo, A, cost)
    if tC: trades.append(tC)
    if dt['ruleF']:
        t = fixed_trade(b, day, ENTRY_F_MIN, +1, A, 'F', cost)
        if t: trades.append(t)
    kept = apply_conflict_close(trades)
    tK = kfade_trade(b, day, dt, A, tC['t'] if tC else None, cost)
    if tK: kept.append(tK)
    tAW = aw_trade(b, day, dt, A, awdir, cost)              # v1.10, new 9 Nov 2026 - independent, see module docstring
    if tAW: kept.append(tAW)
    tK2 = k2_trade(b, day, dt, A, tK, tC['t'] if tC else None, cost)   # v1.10, new 9 Nov 2026 - independent, see module docstring
    if tK2: kept.append(tK2)
    if v115:                                                # v1.15 add-ons: own positions, never conflict-closed, appended like K+/AW/K2
        dayn = pd.Timestamp(day).normalize()
        if USE_A16 and awdir:                               # U1: rule A signalled (not mid-range) -> 16:00 add-on if the 10:00->16:00 move still has A's sign
            o10, o16 = bar_open_at(b, dayn, SIG_START_MIN), bar_open_at(b, dayn, A16_ENTRY_MIN)
            if np.isfinite(o10) and np.isfinite(o16) and (o16 - o10) * awdir > 0:
                t = fixed_trade(b, dayn, A16_ENTRY_MIN, awdir, A, 'A16', cost, A16_STOP_MULT)
                if t: t['tag'] = 'A16'; kept.append(t)
        tB = next((x for x in kept if x['rule'] == 'B'), None)
        if USE_B12 and tB is not None:                      # U2: B opened and its sell is in profit at 12:00
            o12 = bar_open_at(b, dayn, B12_MIN)
            if np.isfinite(o12) and o12 < tB['entry']:
                t = fixed_trade(b, dayn, B12_MIN, -1, A, 'B12', cost, UPG_STOP_MULT)
                if t: t['tag'] = 'B12'; kept.append(t)
        if USE_C14 and tC is not None and tC in kept and tC['t'] < dayn + pd.Timedelta(minutes=C14_MIN):   # U3: C opened before 14:00 and is in profit at 14:00
            o14 = bar_open_at(b, dayn, C14_MIN)
            if np.isfinite(o14) and (o14 - tC['entry']) * tC['dir'] > 0:
                t = fixed_trade(b, dayn, C14_MIN, tC['dir'], A, 'C14', cost, UPG_STOP_MULT)
                if t: t['tag'] = 'C14'; kept.append(t)
        if USE_A12K and dt['wed'] and not skipA:            # U4
            t = a12k_trade(b, dayn, A, sd12, awdir, cost)
            if t: kept.append(t)
    if watch: kept += watch_trades(b, day, dt, A, dcl, cost)   # v1.12W, new 19 Nov 2026 - demo forward test, independent, see module docstring
    return kept
