"""GBP/USD crowd engine (GBP_CROWD v1.04 rules, MT4-proven 24 Oct 2026: his run 5, 3,810 trades 2011-2026, net $15,966.95 at 0.10 lot,
max DD $1,636.34, net/DD 9.76, profit days 54.3% of weekdays, 57.3% of trades closed in profit; v1.03 = his run 4, 3,810 trades 2011-2026, net $12,108.90 at 0.10 lot,
max DD $2,090.54, net/DD 5.79, all 4 periods positive, 95.3% of weekdays traded, profit days 49.2%; v1.02 = layers 1-3 only). Pure functions, no I/O - used by gbp_run.py (desk) and the parity tests.
Signal (weekly, CFTC Traders in Financial Futures, British Pound 096742; Tuesday report used from the Monday after = report date + 6 days):
  layer 1: leveraged funds' net/OI in the top / bottom 10% of the last 52 weeks -> fade them (SELL / BUY)
  layer 2: else small traders' (non-reportable) net/OI in the top / bottom 20% -> fade them
  layer 3: else small traders' 1-week change of net/OI in the top / bottom 25% -> fade it
  layer 4 (v1.03, daily): else EUR/GBP at 10:00 broker of the last 20 trading days BEFORE today: z of the newest > 1.5 -> BUY (pound cheap
           vs euro, snaps back), z < -1.5 -> SELL
  layer 5 (v1.03, weekly): else FOLLOW leveraged funds in EURO futures (CFTC TFF 099741): net/OI in the top 25% of 52 weeks -> BUY, bottom 25% -> SELL
Trade: one a day, entry at the first bar from 10:00 to 10:05 broker (New York + 7 h), stop 1.0 x the 14-day average daily range,
target 1.0 x stop, close 23:45 broker; a trade still open when the day has no 23:45 bar closes at the day's last price (v1.02 catch-up).
v1.04 REGIME rules on crowd days (layers 1-3), regime = percentile of today's 14-day range among the last 250 days (min 120):
  busy (>= 0.8): stop 1.25 x range, target 1.5 x stop
  calm (< 0.5): once the trade is +0.35 x stop in profit, the stop moves to entry + 5 pips (from the next minute); and if GBP ran
        ahead of / behind EUR from 00:00 to 10:00 broker by >= 0.3 (each move in its own 14-day range) -> trade AGAINST that gap."""
import numpy as np, pandas as pd

Q1, Q2, Q3 = 0.10, 0.20, 0.25
STOP_X, TGT_X, RANGE_DAYS = 1.0, 1.0, 14
ENTRY_MIN, ENTRY_LATE, CLOSE_MIN = 10 * 60, 5, 23 * 60 + 45
COST = 0.00015                                   # 1.5 pips (the research cost); the desk uses max(this, live spread)
LAYER_NAME = {1: 'Layer 1 · hedge funds crowded', 2: 'Layer 2 · small traders crowded', 3: 'Layer 3 · small traders jumped in',
              4: 'Layer 4 · pound stretched vs euro', 5: 'Layer 5 · euro hedge funds trend', 6: 'Holiday sell · day after a UK/US holiday'}
Q5, EG_W, EG_Z = 0.25, 20, 1.5
HOL_SIZE, HOL_STOP = 0.5, 1.5                    # v1.05 extra trade
POST_HOL = frozenset([
    '2010-09-07', '2010-10-12', '2010-11-12', '2010-11-26', '2010-12-29', '2011-01-04', '2011-01-18', '2011-02-22',
    '2011-04-25', '2011-05-03', '2011-05-31', '2011-07-05', '2011-09-06', '2011-10-11', '2011-11-14', '2011-11-25',
    '2011-12-28', '2012-01-03', '2012-01-17', '2012-02-21', '2012-04-09', '2012-05-08', '2012-05-29', '2012-06-06',
    '2012-07-05', '2012-09-04', '2012-10-09', '2012-11-13', '2012-11-23', '2012-12-27', '2013-01-02', '2013-01-22',
    '2013-02-19', '2013-04-01', '2013-05-07', '2013-05-28', '2013-07-05', '2013-09-03', '2013-10-15', '2013-11-12',
    '2013-11-29', '2013-12-27', '2014-01-02', '2014-01-21', '2014-02-18', '2014-04-21', '2014-05-06', '2014-05-27',
    '2014-07-07', '2014-09-02', '2014-10-14', '2014-11-12', '2014-11-28', '2014-12-29', '2015-01-02', '2015-01-20',
    '2015-02-17', '2015-04-06', '2015-05-05', '2015-05-26', '2015-07-06', '2015-09-08', '2015-10-13', '2015-11-12',
    '2015-11-27', '2015-12-29', '2016-01-04', '2016-01-19', '2016-02-16', '2016-03-28', '2016-05-03', '2016-05-31',
    '2016-07-05', '2016-09-06', '2016-10-11', '2016-11-14', '2016-11-25', '2016-12-28', '2017-01-03', '2017-01-17',
    '2017-02-21', '2017-04-17', '2017-05-02', '2017-05-30', '2017-07-05', '2017-09-05', '2017-10-10', '2017-11-13',
    '2017-11-24', '2017-12-27', '2018-01-02', '2018-01-16', '2018-02-20', '2018-04-02', '2018-05-08', '2018-05-29',
    '2018-07-05', '2018-09-04', '2018-10-09', '2018-11-13', '2018-11-23', '2018-12-27', '2019-01-02', '2019-01-22',
    '2019-02-19', '2019-04-22', '2019-05-07', '2019-05-28', '2019-07-05', '2019-09-03', '2019-10-15', '2019-11-12',
    '2019-11-29', '2019-12-27', '2020-01-02', '2020-01-21', '2020-02-18', '2020-04-13', '2020-05-11', '2020-05-26',
    '2020-07-06', '2020-09-08', '2020-10-13', '2020-11-12', '2020-11-27', '2020-12-29', '2021-01-04', '2021-01-19',
    '2021-02-16', '2021-04-05', '2021-05-04', '2021-06-01', '2021-06-21', '2021-07-06', '2021-09-07', '2021-10-12',
    '2021-11-12', '2021-11-26', '2021-12-29', '2022-01-04', '2022-01-18', '2022-02-22', '2022-04-18', '2022-05-03',
    '2022-05-31', '2022-06-06', '2022-06-21', '2022-07-05', '2022-09-06', '2022-09-20', '2022-10-11', '2022-11-14',
    '2022-11-25', '2022-12-28', '2023-01-03', '2023-01-17', '2023-02-21', '2023-04-10', '2023-05-02', '2023-05-09',
    '2023-05-30', '2023-06-20', '2023-07-05', '2023-09-05', '2023-10-10', '2023-11-13', '2023-11-24', '2023-12-27',
    '2024-01-02', '2024-01-16', '2024-02-20', '2024-04-01', '2024-05-07', '2024-05-28', '2024-06-20', '2024-07-05',
    '2024-09-03', '2024-10-15', '2024-11-12', '2024-11-29', '2024-12-27', '2025-01-02', '2025-01-21', '2025-02-18',
    '2025-04-21', '2025-05-06', '2025-05-27', '2025-06-20', '2025-07-07', '2025-09-02', '2025-10-14', '2025-11-12',
    '2025-11-28', '2025-12-29', '2026-01-02', '2026-01-20', '2026-02-17', '2026-04-06', '2026-05-05', '2026-05-26',
    '2026-06-22', '2026-07-06', '2026-09-08', '2026-10-13', '2026-11-12', '2026-11-27', '2026-12-29', '2027-01-04',
    '2027-01-19', '2027-02-16', '2027-03-29', '2027-05-04', '2027-06-01', '2027-06-21', '2027-07-06', '2027-09-07',
    '2027-10-12', '2027-11-12', '2027-11-26', '2027-12-29'])

def is_post_holiday(day):
    """v1.05: True on the weekday after a UK or US holiday (list = the EA's hpD list, 2010-2027)."""
    return str(pd.Timestamp(day).date()) in POST_HOL

REG_W, REG_MIN, BUSY_Q, CALM_Q = 250, 120, 0.8, 0.5
BUSY_STOP, BUSY_TGT, LOCK_AT, LOCK_PX, DIV_X = 1.25, 1.5, 0.35, 0.0005, 0.3

def rank_pct(v, win=52, minp=26):
    """rolling 52-week percentile of the newest value = pandas rolling(52, min_periods=26).rank(pct=True) (average ties)."""
    v = np.asarray(v, float); out = np.full(len(v), np.nan)
    for i in range(len(v)):
        w = v[max(0, i - win + 1):i + 1]; w = w[np.isfinite(w)]
        if len(w) < minp or not np.isfinite(v[i]): continue
        out[i] = (np.sum(w < v[i]) + (np.sum(w == v[i]) + 1) / 2) / len(w)
    return out

def codes(W):
    """W: weekly DataFrame indexed by report date with oi, lev_l, lev_s, nr_l, nr_s. Returns a DataFrame with the percentiles and
    code = +-1 / +-2 / +-3 (sign = BUY / SELL, number = layer), 0 = no trade."""
    W = W.sort_index(); lev = (W.lev_l - W.lev_s) / W.oi; nr = (W.nr_l - W.nr_s) / W.oi
    lp, npc, ncp = rank_pct(lev.values), rank_pct(nr.values), rank_pct(nr.diff().values)
    f = lambda p, q: np.where(p >= 1 - q, -1, np.where(p <= q, 1, 0))
    t1, t2, t3 = f(lp, Q1), f(npc, Q2), f(ncp, Q3)
    c = np.where(t1 != 0, t1, np.where(t2 != 0, 2 * t2, 3 * t3))
    return pd.DataFrame(dict(lev=lev, nr=nr, levp=lp, nrp=npc, nrcp=ncp, code=c), index=W.index)

def code_for(C, day):
    """the code that applies on broker day `day`: latest report with report date + 6 days <= day. Returns (code, report date) or (0, None)."""
    if C is None or not len(C): return 0, None
    use = C.index + pd.Timedelta(days=6); i = int(use.searchsorted(pd.Timestamp(day), side='right')) - 1
    if i < 0: return 0, None
    return int(C.code.values[i]), C.index[i]

def eur_codes(W):
    """W: weekly EURO FX TFF rows (oi, lev_l, lev_s) by report date -> levp + code +1 (funds long euro: BUY GBP/USD) / -1 / 0 (layer 5 follows them)."""
    W = W.sort_index(); lev = (W.lev_l - W.lev_s) / W.oi; p = rank_pct(lev.values)
    return pd.DataFrame(dict(lev=lev, levp=p, code=np.where(p >= 1 - Q5, 1, np.where(p <= Q5, -1, 0))), index=W.index)

def eg_side(vals):
    """vals = EUR/GBP at 10:00 broker on the trading days BEFORE today, oldest first. Uses the newest 20 (= pandas rolling(20) z of
    yesterday's value). Returns (+1 BUY / -1 SELL / 0, z)."""
    v = np.asarray(vals, float)[-EG_W:]
    if len(v) < EG_W or not np.isfinite(v).all(): return 0, np.nan
    sd = v.std(ddof=1)
    if not sd > 0: return 0, np.nan
    z = (v[-1] - v.mean()) / sd
    return (1 if z > EG_Z else -1 if z < -EG_Z else 0), float(z)

def decide(gcode, eg, ecode):
    """v1.03 order: GBP layers 1-3, else layer 4 (EUR/GBP), else layer 5 (euro funds). Returns code +-1..+-5 or 0."""
    if gcode: return int(gcode)
    if eg: return 4 * int(eg)
    return 5 * int(ecode)

def range_hist(daily, day):
    """A (14-day average high-low of the days BEFORE each day) for every stored weekday up to and including `day` (oldest first)."""
    d = daily[(daily.index <= pd.Timestamp(day)) & (daily.index.dayofweek < 5)].sort_index()
    r = (d.h - d.l); A = r.rolling(RANGE_DAYS).mean().shift(1)
    if pd.Timestamp(day) not in d.index:                                   # today not stored yet: append today's A from the last 14 days
        A = pd.concat([A, pd.Series([r.iloc[-RANGE_DAYS:].mean() if len(r) >= RANGE_DAYS else np.nan], index=[pd.Timestamp(day)])])
    return A.dropna()

def regime_pct(A_hist):
    """percentile of the newest A among the newest 250 (incl. itself), average ties = pandas rolling(250, min_periods=120).rank(pct=True)."""
    v = np.asarray(A_hist, float)[-REG_W:]
    if len(v) < REG_MIN or not np.isfinite(v[-1]): return np.nan
    return float((np.sum(v < v[-1]) + (np.sum(v == v[-1]) + 1) / 2) / len(v))

def gap_div(g0, g10, e0, e10, A, eA):
    """GBP move 00:00->10:00 in its 14-day range minus EUR move in its own 14-day range."""
    try: return float((g10 - g0) / A - (e10 - e0) / eA)
    except Exception: return np.nan

def mode(code, pct, div):
    """v1.04 trade shape for the day: returns (code, k_stop, t_target, lock, name). code may flip on calm days."""
    lay = abs(int(code))
    if code == 0 or lay > 3 or not np.isfinite(pct): return int(code), STOP_X, TGT_X, False, 'normal'
    if pct >= BUSY_Q: return int(code), BUSY_STOP, BUSY_TGT, False, 'busy'
    if pct < CALM_Q:
        if np.isfinite(div) and abs(div) >= DIV_X: return (-1 if div > 0 else 1) * lay, STOP_X, TGT_X, True, 'calm_gap'
        return int(code), STOP_X, TGT_X, True, 'calm'
    return int(code), STOP_X, TGT_X, False, 'normal'

def avg_range(daily, day):
    """14-day average daily high-low of the weekdays BEFORE `day` (daily: index broker dates, columns h, l). NaN if fewer than 14 days."""
    d = daily[(daily.index < pd.Timestamp(day)) & (daily.index.dayofweek < 5)]
    if len(d) < RANGE_DAYS: return np.nan
    return float((d.h - d.l).iloc[-RANGE_DAYS:].mean())

def trade(b, day, code, A, now=None, cost=COST, k=STOP_X, tx=TGT_X, lock=False):
    """b = the day's closed minute bars (index broker time, columns o h l c, bid). Returns a trade dict or None.
    status: open / target / stopped / eod (23:45 close) / close_now (day over, no 23:45 bar = catch-up close)."""
    if code == 0 or not np.isfinite(A) or A <= 0 or not len(b): return None
    day = pd.Timestamp(day); t0 = day + pd.Timedelta(minutes=ENTRY_MIN); te = day + pd.Timedelta(minutes=CLOSE_MIN)
    a = int(b.index.searchsorted(t0))
    if a >= len(b) or b.index[a] - t0 > pd.Timedelta(minutes=ENTRY_LATE): return None    # no bar 10:00-10:05 -> no trade (as the EA)
    s = 1 if code > 0 else -1; en = float(b.o.values[a]); sd = k * A
    st, tg = en - s * sd, (en + s * tx * sd if tx > 0 else None)   # v1.05: tx <= 0 = no target
    e = int(b.index.searchsorted(te))                                                      # first bar at/after 23:45 (exit at its open)
    H, L = b.h.values[a:e], b.l.values[a:e]
    lk_px, lk_st = en + s * LOCK_AT * sd, en + s * LOCK_PX
    out = dict(t=b.index[a], dir=s, layer=abs(code), entry=en, sd=sd, A=A, stop=st, stop0=st, target=tg, exit=None, exit_t=None, status='open', pips=None,
               lock=bool(lock), lock_px=lk_px if lock else None, lock_stop=lk_st if lock else None, locked=False, locked_t=None)
    cur = st; hit = None
    for j in range(len(H)):                                                 # same order as the research: stop, target, then the lock (next minute on)
        if (L[j] <= cur) if s > 0 else (H[j] >= cur): hit = ('stopped', cur, j); break
        if tg is not None and ((H[j] >= tg) if s > 0 else (L[j] <= tg)): hit = ('target', tg, j); break
        if lock and not out['locked'] and ((H[j] >= lk_px) if s > 0 else (L[j] <= lk_px)):
            out.update(locked=True, locked_t=b.index[a + j], stop=lk_st); cur = lk_st
    if hit:
        out.update(status=hit[0], exit=hit[1], exit_t=b.index[a + hit[2]])
    elif e < len(b):
        out.update(status='eod', exit=float(b.o.values[e]), exit_t=b.index[e])
    elif now is not None and pd.Timestamp(now) >= day + pd.Timedelta(days=1):                # day over without a 23:45 bar
        out.update(status='close_now', exit=float(b.c.values[-1]), exit_t=b.index[-1])
    if out['exit'] is not None: out['pips'] = (s * (out['exit'] - en) - cost) * 1e4
    return out
