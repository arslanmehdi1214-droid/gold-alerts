"""Brent Oil (BRENT) dashboard SIGNAL engine - BRENT v1.06 rules (A-F only; rule G and the conflict-close rule's
interaction with it were part of the EA bundle but dropped from this port - his 8 Nov decision: "drop rule G
completely... no changes to autotrade.py"), source of truth EA BRENT_WED_HOL_v106.mq4.
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

RULE_NAME = {'A': 'Rule A · Wednesday momentum', 'B': 'Rule B · day after US holiday',
             'C': 'Rule C · 20-day range break', 'Dbuy': 'Rule D · UK bank holiday (buy)', 'Dsell': 'Rule D · UK bank holiday (sell next day)',
             'E': 'Rule E · 2nd day after UK holiday (sell)', 'F': 'Rule F · day before holiday (buy)'}

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

def today_move_10_14(b, day):
    o10, o14 = bar_open_at(b, day, SIG_START_MIN), bar_open_at(b, day, ENTRY_A_MIN)
    return np.nan if not (np.isfinite(o10) and np.isfinite(o14)) else o14 - o10

def wed_signal(move, sd):
    if not (np.isfinite(move) and np.isfinite(sd) and sd > 0): return 0
    return 1 if move > MOVE_Z * sd else -1 if move < -MOVE_Z * sd else 0

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

def run_day(b, day, dt, A, hi, lo, sd, cost=0.08):
    """b: today's closed minute bars. dt = day_type(...) for the day. A = ADR20; (hi,lo) = rule C's 20-day channel;
    sd = rule A's 60-day move std. Returns the list of trade dicts that fired today (0-N, conflict-closed)."""
    trades = []
    if dt['ruleD_buy']:
        t = fixed_trade(b, day, ENTRY_BD_MIN, +1, A, 'Dbuy', cost)
        if t: trades.append(t)
    if dt['ruleD_sell']:
        t = fixed_trade(b, day, ENTRY_BD_MIN, -1, A, 'Dsell', cost)
        if t: trades.append(t)
    if dt['ruleB']:
        t = fixed_trade(b, day, ENTRY_BD_MIN, -1, A, 'B', cost)
        if t: trades.append(t)
    if dt['ruleE']:
        t = fixed_trade(b, day, ENTRY_E_MIN, -1, A, 'E', cost)
        if t: trades.append(t)
    if dt['wed']:
        side = wed_signal(today_move_10_14(b, day), sd)
        if side:
            t = fixed_trade(b, day, ENTRY_A_MIN, side, A, 'A', cost)
            if t: trades.append(t)
    tC = range_break_trade(b, day, hi, lo, A, cost)
    if tC: trades.append(tC)
    if dt['ruleF']:
        t = fixed_trade(b, day, ENTRY_F_MIN, +1, A, 'F', cost)
        if t: trades.append(t)
    return apply_conflict_close(trades)
