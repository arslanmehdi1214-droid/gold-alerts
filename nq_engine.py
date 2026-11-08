"""Nasdaq 100 (US Tech 100) PAPER engine for the Signal Desk - the 2026 walk-forward set (re-picked each January in Python).
Signals = the research idea code itself (nq_a = normal hours, nq_b = every start hour shifted +10 h into the US session), run on a
rolling base of recent minute bars (broker clock = New York + 7 h, bid prices). Per day: the first CORE signal of the day is a trade;
a FILLER signal is a trade only if it fires before the day's first core signal (first filler of the day only); max 2 trades a day.
Fills (same as the research): market = the minute's open; break = at the level when the minute trades to it; fade/limit = at the level
only if the minute trades THROUGH it by max(0.25, 0.01 x range). Stop = 0.25 x 14-day average daily range from the fill level;
no target; close at the day end (23:00 broker, Fri 22:50). No entry in the day-end minute.
v1.01 EXITS (manage_v101, MT4-proven 18 Oct: his run, spread 18, 2020-26: green 58.7%, won 64.9%, net/DD 8.60, worst day -$2,039 at $1,000 risk):
buys stop 0.5 x range, sells stop 0.25 x range and 1/3 size; close 25% when profit = 0.5 x risk (risk = stop distance incl. spread), then the rest
closes at the entry; day lock: once the day reaches +3R, close all at +1.5R or less, no more trades; close at the day end.
v1.02 EXITS (manage_v102, MT4-proven 19 Oct: his run, spread 18, 2020-26: green 59.2%, won 66.2%, net $126,676, net/DD 13.90, worst day -$2,046):
v1.01 + buy stop 0.4 x range; part close buys 25% / sells 15% at +0.5 x risk; after the part close the rest's stop = max(entry, best price - 0.45 x range)
(sells mirrored, best = lowest ask); no new trades from 22:00 broker (Fridays from 20:00)."""
import os, sys, io, json, contextlib, importlib, tempfile, pickle, numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = {'a': os.path.join(HERE, 'nq_a'), 'b': os.path.join(HERE, 'nq_b')}
MODS = ['core', 'comp', 'spxC'] + [f'fam{s}' for s in ('', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11')]
SET = json.load(open(os.path.join(HERE, 'nq_set.json')))
SETF = json.load(open(os.path.join(HERE, 'nq_set_full.json')))          # the full version (needs the gold engine replayed on Nasdaq)
STOP_X = SET['stop']; TICK = 0.25; KEEP_DAYS = 300
V101 = dict(buy_stop=0.5, sell_stop=0.25, sell_w=1/3, k=0.5, part=0.25, lock_pk=3.0, lock_fl=1.5)
V102 = dict(buy_stop=0.4, sell_stop=0.25, sell_w=1/3, k=0.5, part_buy=0.25, part_sell=0.15, trail=0.45, last=22 * 60, fri_last=20 * 60, lock_pk=3.0, lock_fl=1.5)
ENG_SET = dict(U2_Step=100.0, N2_Step=200.0, G3_Step=40.0, Spread=0.6)   # same settings as the research replay (replay_n.py raw 100 200 40)
NEUTRAL = dict(d5=0, d1=0, vix=0, tnx=0, regime=lambda t: 0, attn=0)
LAST_PICKS = {}                                   # 22 Oct: the day's picks (before the exits) for the S&P page (sp_run copies them)

# ---------------- FOMC-overnight (8 Nov 2026 port, lead #10/#384 from the Nasdaq chat's research hunt) ----------------
# Its OWN low-frequency signal, long only, ~8x/year - never counted against v1.02's 2-trades-a-day cap, never
# touched by manage_v102 (separate position, separate journal docs/journal_nq_fomc.json, shown alongside the
# existing US100 card, not folded into its v1.02-tagged journal/summary). Rule (exactly as MT4-confirmed, his run
# 8 Nov, window 2018.01.02-2026.10.30, spread 18, 0.01 lot: 56 trades, PF 2.55, maxDD 4.83 (0.00%), 20/56=35.7%
# hit target, 38/56=67.9% closed in profit): go long at the RTH close (23:00 broker Mon-Thu, 22:50 Fri) on the
# trading day immediately before a scheduled FOMC rate-decision day; stop = entry - R, R = FOMC_R_MULT x the
# 14-day average D1 range, lagged 2 trading days before the entry day; target = entry + FOMC_TP_MULT x R; force-
# close at the RTH open (16:30 broker) on the decision day if neither hit. Decision dates 2010-2027 = the real,
# ALFRED/FOMC.gov-verified FOMC release history (2027 = the Fed's own published tentative schedule) - copied
# verbatim from the Nasdaq chat's MT4-confirmed EA (NASDAQ_FOMC_OVERNIGHT_v1.00.mq4); none fall on a Monday in
# this list (all Tue/Wed), so the entry day is always 1 calendar day back; update every December.
FOMC_DECISIONS = [
    '2010.01.27', '2010.03.16', '2010.04.28', '2010.06.23', '2010.08.10', '2010.09.21', '2010.11.03', '2010.12.14',
    '2011.01.26', '2011.03.15', '2011.04.27', '2011.06.22', '2011.08.09', '2011.09.21', '2011.11.02', '2011.12.13',
    '2012.01.25', '2012.03.13', '2012.04.25', '2012.06.20', '2012.08.01', '2012.09.13', '2012.10.24', '2012.12.12',
    '2013.01.30', '2013.03.20', '2013.05.01', '2013.06.19', '2013.07.31', '2013.09.18', '2013.10.30', '2013.12.18',
    '2014.01.29', '2014.03.19', '2014.04.30', '2014.06.18', '2014.07.30', '2014.09.17', '2014.10.29', '2014.12.17',
    '2015.01.28', '2015.03.18', '2015.04.29', '2015.06.17', '2015.07.29', '2015.09.17', '2015.10.28', '2015.12.16',
    '2016.01.27', '2016.03.16', '2016.04.27', '2016.06.15', '2016.07.27', '2016.09.21', '2016.11.02', '2016.12.14',
    '2017.02.01', '2017.03.15', '2017.05.03', '2017.06.14', '2017.07.26', '2017.09.20', '2017.11.01', '2017.12.13',
    '2018.01.31', '2018.03.21', '2018.05.02', '2018.06.13', '2018.08.01', '2018.09.26', '2018.11.08', '2018.12.19',
    '2019.01.30', '2019.03.20', '2019.05.01', '2019.06.19', '2019.07.31', '2019.09.18', '2019.10.30', '2019.12.11',
    '2020.01.29', '2020.03.15', '2020.04.29', '2020.06.10', '2020.07.29', '2020.09.16', '2020.11.05', '2020.12.16',
    '2021.01.27', '2021.03.17', '2021.04.28', '2021.06.16', '2021.07.28', '2021.09.22', '2021.11.03', '2021.12.15',
    '2022.01.26', '2022.03.16', '2022.05.04', '2022.06.15', '2022.07.27', '2022.09.21', '2022.11.02', '2022.12.14',
    '2023.02.01', '2023.03.22', '2023.05.03', '2023.06.14', '2023.07.26', '2023.09.20', '2023.11.01', '2023.12.13',
    '2024.01.31', '2024.03.20', '2024.05.01', '2024.06.12', '2024.07.31', '2024.09.18', '2024.11.07', '2024.12.18',
    '2025.01.29', '2025.03.19', '2025.05.07', '2025.06.18', '2025.07.30', '2025.09.17', '2025.10.29', '2025.12.10',
    '2026.01.28', '2026.03.18', '2026.04.29', '2026.06.17', '2026.07.29', '2026.09.16', '2026.10.28', '2026.12.09',
    '2027.01.27', '2027.03.17', '2027.04.28', '2027.06.09', '2027.07.28', '2027.09.15', '2027.10.27', '2027.12.08',
]
FOMC_R_MULT, FOMC_TP_MULT = 0.35, 1.0
FOMC_EXIT_HM = 16 * 60 + 30                       # RTH open deadline, broker time, on the decision day
FOMC_FROM = pd.Timestamp('2026-11-08')            # push day - the already-past 27 Oct entry day is never retroactively traded

def fomc_decision_dates():
    return sorted(pd.Timestamp(d.replace('.', '-')) for d in FOMC_DECISIONS)

def fomc_entry_map():
    """{entry-day date string: decision day Timestamp}, entry days on/after FOMC_FROM only (so past days never recompute)."""
    out = {}
    for dday in fomc_decision_dates():
        back = 3 if dday.dayofweek == 0 else 1          # Monday decision -> back to Friday (never occurs in this list, kept for safety)
        eday = dday - pd.Timedelta(days=back)
        if eday >= FOMC_FROM: out[str(eday.date())] = dday
    return out

def daily_range_atr(m):
    """Daily O/H/L/C + 14-day avg(H-L) lagged 1 trading day (same construction as build_base's own internal DB), from minute bars m."""
    day = m.index.normalize(); g = m.groupby(day)
    DB = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    DB['rng'] = DB.h - DB.l; DB['atr'] = DB.rng.rolling(14).mean().shift(1)
    return DB

def fomc_r(DB, entry_day):
    """R = FOMC_R_MULT x the 14-day avg range, lagged 2 trading days before entry_day - taking DB['atr'] (already
    lag-1) from the trading day BEFORE entry_day's own row gives exactly that second day of lag (matches the EA's
    ComputeR: avg(H-L) over the 14 D1 bars ending 2 bars before entry's own bar)."""
    ed = pd.Timestamp(entry_day)
    if ed not in DB.index: return None
    pos = DB.index.get_loc(ed)
    if pos < 1: return None
    v = DB['atr'].iloc[pos - 1]
    return None if not np.isfinite(v) or v <= 0 else round(FOMC_R_MULT * float(v), 2)

def fomc_check_exit(m, entry_time, entry, sl, tp, decision_day, now):
    """Scan minute bars after entry_time for stop/target (long only; stop checked before target each minute, same
    precedence as every other signal's exit logic), else force-close at the decision day's RTH-open deadline.
    Returns (status, exit_px, exit_time); status 'open' means still running (nothing to report yet)."""
    deadline = pd.Timestamp(decision_day).normalize() + pd.Timedelta(minutes=FOMC_EXIT_HM)
    bars = m[(m.index > pd.Timestamp(entry_time)) & (m.index <= now)]
    for t, r in bars.iterrows():
        if t >= deadline: return 'eod', float(r.o), t
        o, h, l = float(r.o), float(r.h), float(r.l)
        if o <= sl: return 'stopped', o, t
        if l <= sl: return 'stopped', sl, t
        if o >= tp: return 'target', o, t
        if h >= tp: return 'target', tp, t
    if now >= deadline and len(m[m.index <= now]):
        last = m[m.index <= now]
        return 'eod', float(last.c.iloc[-1]), last.index[-1]        # deadline passed with a data gap right at it - close at the last known price
    return 'open', None, None

def engine_first(m, day):
    """Gold v2.06 signal engine replayed on today's Nasdaq minutes (outside inputs neutral, as in the research):
    returns (direction, entry time) of its first trade today so far, or (0, None)."""
    import nq_eng as E
    E.S.update(ENG_SET)
    tt = m.index; dd = tt.normalize()
    g = m.groupby(dd); DB = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    DB = DB[DB.index < day].iloc[-320:]
    D = E.Daily(DB.index.values.astype('datetime64[D]'), DB.o.values, DB.h.values, DB.l.values, DB.c.values)
    T = tt.values.astype('datetime64[m]'); hr = T.astype('datetime64[h]'); chg = np.r_[True, hr[1:] != hr[:-1]]; hs = np.where(chg)[0]; he = np.r_[hs[1:], len(T)]
    H = m.h.values.astype(float); L = m.l.values.astype(float); C = m.c.values.astype(float); O = m.o.values.astype(float)
    Hh = E.Hourly(hr[hs].astype('datetime64[m]'), np.maximum.reduceat(H, hs), np.minimum.reduceat(L, hs), C[he - 1])
    k = dd == day
    m1 = dict(t=T[k], o=O[k], h=H[k], l=L[k], c=C[k])
    tr = E.run_day(np.datetime64(day.date(), 'D'), D, Hh, m1, NEUTRAL)
    if not tr: return 0, None
    f = min(tr, key=lambda x: x['t'])
    return int(f['dir']), pd.Timestamp(f['t'])

def eod_minutes(day):
    return 22 * 60 + 50 if pd.Timestamp(day).dayofweek == 4 else 23 * 60

def build_base(m, out, eng=None, open_last=False):
    """m: minute bars (index = broker time, columns o h l c), weekdays, sorted. Same layout as the research base (build_base_n.py).
    open_last (22 Oct fix): the last day is still running - until a bar at/after its close time exists, its latest closed bar is not
    the day-end bar (EODX = entry check only; the research EOD in base.npz is unchanged)."""
    t = m.index.values.astype('datetime64[ns]'); O, H, L, C = (m[c].values.astype(float) for c in 'ohlc')
    tt = pd.DatetimeIndex(t); day = tt.normalize(); hr = tt.hour.values; mi = tt.minute.values
    dcode, duniq = pd.factorize(day)
    g = pd.DataFrame({'h': H, 'l': L, 'o': O, 'c': C, 'd': dcode}).groupby('d')
    DB = pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})
    DB['rng'] = DB.h - DB.l; DB['atr'] = DB.rng.rolling(14).mean().shift(1); DB['ph'] = DB.h.shift(1); DB['pl'] = DB.l.shift(1)
    A = DB.atr.values[dcode]; PH = DB.ph.values[dcode]; PL = DB.pl.values[dcode]; DO = DB.o.values[dcode]
    dow = tt.dayofweek.values
    eod_t = (day + pd.to_timedelta(np.where(dow == 4, 22 * 60 + 50, 23 * 60), unit='m')).values
    EOD = np.searchsorted(t, eod_t); dlast = np.r_[np.where(np.diff(dcode) != 0)[0], len(t) - 1][dcode]; EOD = np.minimum(EOD, dlast)
    np.savez(os.path.join(out, 'base.npz'), O=O, H=H, L=L, C=C, V=np.zeros(len(O)), A=A, PH=PH, PL=PL, DO=DO, dcode=dcode, hr=hr, mi=mi, EOD=EOD,
             yr=tt.year.values, dow=dow)
    pickle.dump(dict(t=t), open(os.path.join(out, 'base_t.pkl'), 'wb'))
    lad = pd.DataFrame({'edir': np.zeros(len(duniq), int), 'et': pd.Series([pd.NaT] * len(duniq), dtype='datetime64[s]').values}, index=duniq)
    if eng and eng[0]:                                   # today's engine trade (the full version only)
        lad.iloc[-1, 0] = eng[0]; lad.iloc[-1, 1] = eng[1]
    lad.to_pickle(os.path.join(out, 'lad.pkl'))
    EODX = EOD.copy()
    if open_last and len(t) and not (hr[EOD[-1]] * 60 + mi[EOD[-1]] >= eod_minutes(tt[-1])): EODX[dcode == dcode[-1]] = len(t)
    return dict(O=O, H=H, L=L, C=C, A=A, EOD=EOD, EODX=EODX, t=tt, dcode=dcode, hm=hr * 60 + mi)

def _purge():
    for n in MODS: sys.modules.pop(n, None)

def ideas(pkg, base_dir):
    """Import the research idea code from one package on the base in base_dir; returns {name: function} (twins not included)."""
    _purge(); os.environ['NQ_BASE'] = base_dir; sys.path.insert(0, PKG[pkg])
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            mods = [importlib.import_module(n) for n in ('fam5', 'fam6', 'fam7', 'fam11', 'spxC')]
        ALL = {}
        for mod in mods[:4]:
            for dn in ('IDEAS', 'IDEAS2', 'IDEAS3', 'IDEAS4', 'IDEAS5', 'IDEAS6', 'IDEAS7', 'IDEAS8', 'IDEAS9', 'IDEAS10', 'IDEAS11'):
                if hasattr(mod, dn): ALL.update(getattr(mod, dn))
        for n, f in mods[4].IDEASC.items(): ALL['C ' + n] = f
        return ALL
    finally:
        sys.path.remove(PKG[pkg])

def s11_events(name, B):
    """S11 ideas made inside the research script s11.py (only the opening-drive family is used)."""
    w = name.split()                                   # 'S11 opening drive 5min >0.2 follow'
    mins = int(w[3].replace('min', '')); thr = float(w[4][1:])
    hm, dc = B['hm'], B['dcode']; starts = np.r_[0, np.where(np.diff(dc) != 0)[0] + 1]; ends = np.r_[starts[1:], len(dc)]; E = []
    def at(k, mn):
        s, e = starts[k], ends[k]; p = s + np.searchsorted(hm[s:e], mn)
        return p if p < e and hm[p] <= mn + 5 else -1
    for k in range(len(starts)):
        a = at(k, 990); i = at(k, 990 + mins)
        if a < 0 or i < 0: continue
        mv = (B['C'][i - 1] - B['O'][a]) / B['A'][i]
        if abs(mv) > thr: E.append((k, i, B['O'][i], int(np.sign(mv))))
    return E

def filled(j, px, d, B):
    """Research fill rule (wf.py fill_acc): True if the order fills inside minute j."""
    O, H, L, A = B['O'], B['H'], B['L'], B['A']; m = max(TICK, 0.01 * A[j])
    if px == O[j]: return True
    if px > O[j]: return H[j] >= px if d > 0 else H[j] >= px + m
    return L[j] <= px if d < 0 else L[j] <= px - m

def day_events(B, names, funcs_a, funcs_b, k_today):
    """All filled events of day k_today for every name: list of (j, order_in_set, name, d, px)."""
    out = []
    for oi, nm in enumerate(names):
        rev = nm.startswith('REV '); base = nm[4:] if rev else nm
        if base.startswith('US+10 '): f = funcs_b.get(base[6:])
        elif base.startswith('S11 '): f = (lambda b=base: s11_events(b, B))
        else: f = funcs_a.get(base)
        if f is None: raise KeyError('signal not found: ' + nm)
        for (k, j, px, d) in f():
            if int(k) != k_today: continue
            j = int(j); d = -int(d) if rev else int(d); px = float(px)
            if j >= B['EODX'][j]: continue                       # no entry in the day-end minute (22 Oct: a real one, at/after the close time)
            if filled(j, px, d, B): out.append((j, oi, nm, d, px))
    return out

def first_trade(ev):
    """Research ladder with cap 1 = the earliest event (ties: set order)."""
    return min(ev, key=lambda e: (e[0], e[1])) if ev else None

def manage(B, j, d, px, now_idx, stop_x=None):
    """Stop / day-end exit of a trade entered in minute j, using minutes after j up to now_idx (inclusive)."""
    O, H, L, A, EOD = B['O'], B['H'], B['L'], B['A'], B['EOD']; stop = px - d * (stop_x or STOP_X) * A[j]; e = EOD[j]
    full_day = B['t'][e].hour * 60 + B['t'][e].minute >= eod_minutes(B['t'][j])
    for m in range(j + 1, min(e, now_idx) + 1):
        if m == e and full_day: return stop, 'eod', O[m], B['t'][m]
        if d > 0:
            if O[m] <= stop: return stop, 'stop', O[m], B['t'][m]
            if L[m] <= stop: return stop, 'stop', stop, B['t'][m]
        else:
            if O[m] >= stop: return stop, 'stop', O[m], B['t'][m]
            if H[m] >= stop: return stop, 'stop', stop, B['t'][m]
    return stop, 'open', None, None

def manage_v101(B, picks, now_idx, sp, P=V101):
    """v1.01 exits for the day's trades (same order of steps as the research sim ndx_dt/fix/nsim.py that the MT4 run matched):
    per minute: 1) new trade (skipped once the day is locked); 2) trades from earlier minutes: stop first (a gap fills at the open), then the
    25% level (part closed there, the rest's stop -> entry); 3) day lock at the minute's close. Close all at the day-end minute's open."""
    O, H, L, C, A, EOD = B['O'], B['H'], B['L'], B['C'], B['A'], B['EOD']
    if not picks: return []
    j0 = picks[0][0]; ce = EOD[j0]
    full_day = B['t'][ce].hour * 60 + B['t'][ce].minute >= eod_minutes(B['t'][j0])
    legs = []; banked = 0.0; peak = 0.0; off = False; byj = {p[0]: p for p in picks}
    def mark(g, m):
        rem = 1 - P['part'] if g['half'] else 1.0; px = C[m] if g['d'] > 0 else C[m] + sp
        return g['w'] * (g['bank'] + rem * g['d'] * (px - g['e']) / g['sd'])
    def shut(g, px, m, why):
        nonlocal banked
        rem = 1 - P['part'] if g['half'] else 1.0
        g['r'] = g['bank'] + rem * g['d'] * (px - g['e']) / g['sd']; banked += g['w'] * g['r']
        g.update(on=False, ex=float(px), ext=B['t'][m], status=why)
    last = min(ce, now_idx)
    for m in range(j0, last + 1):
        if m == ce and full_day:
            for g in legs:
                if g['on']: shut(g, O[m] if g['d'] > 0 else O[m] + sp, m, 'eod')
            break
        if m in byj and not off:
            (j, oi, nm, d, px) = byj[m]; s_ = (P['buy_stop'] if d > 0 else P['sell_stop']) * A[j]
            e = px + sp if d > 0 else px; sl = px - s_ if d > 0 else px + sp + s_
            legs.append(dict(j=j, oi=oi, name=nm, d=d, px=px, e=e, sl=sl, sl0=sl, sd=s_, w=(1.0 if d > 0 else P['sell_w']),
                             hp=e + d * P['k'] * abs(e - sl), half=False, half_t=None, bank=0.0, on=True, r=None, ex=None, ext=None, status='open'))
        for g in legs:
            if not g['on'] or m <= g['j']: continue
            d = g['d']
            if (d > 0 and L[m] <= g['sl']) or (d < 0 and H[m] + sp >= g['sl']):
                px = min(g['sl'], O[m]) if d > 0 else max(g['sl'], O[m] + sp)
                shut(g, px, m, 'be' if g['half'] else 'stopped'); continue
            if not g['half'] and ((d > 0 and H[m] >= g['hp']) or (d < 0 and L[m] + sp <= g['hp'])):
                g['bank'] = P['part'] * d * (g['hp'] - g['e']) / g['sd']; g['half'] = True; g['half_t'] = B['t'][m]
                g['sl'] = max(g['sl'], g['e']) if d > 0 else min(g['sl'], g['e'])
        tot = banked + sum(mark(g, m) for g in legs if g['on']); peak = max(peak, tot)
        if P['lock_pk'] > 0 and not off and peak >= P['lock_pk'] and tot <= P['lock_fl']:
            for g in legs:
                if g['on']: shut(g, C[m] if g['d'] > 0 else C[m] + sp, m, 'day lock')
            off = True
    for g in legs:
        g['r_now'] = g['r'] if g['r'] is not None else (g['bank'] + (1 - P['part'] if g['half'] else 1.0) * g['d'] *
                                                       ((C[last] if g['d'] > 0 else C[last] + sp) - g['e']) / g['sd'])
        g['locked_day'] = off
    return legs

def manage_v102(B, picks, now_idx, sp, P=V102):
    """v1.02 exits (same order of steps as the research sim ndx_dt/fix/nsim3.py / nsim4.py that the MT4 v1.02 run matched): per minute:
    1) new trade (skipped once the day is locked, or at/after 22:00 broker, Fridays 20:00); 2) trades from earlier minutes: stop first (a gap
    fills at the open), then the part level (part closed there, the rest's stop -> entry), then the runner trail (best price since the part
    close - 0.45 x range, never below entry; sells mirrored on the ask); 3) day lock at the minute's close. Close all at the day-end minute's open."""
    O, H, L, C, A, EOD = B['O'], B['H'], B['L'], B['C'], B['A'], B['EOD']
    if not picks: return []
    j0 = picks[0][0]; ce = EOD[j0]
    full_day = B['t'][ce].hour * 60 + B['t'][ce].minute >= eod_minutes(B['t'][j0])
    legs = []; banked = 0.0; peak = 0.0; off = False; byj = {p[0]: p for p in picks}
    def mark(g, m):
        rem = 1 - g['pt'] if g['half'] else 1.0; px = C[m] if g['d'] > 0 else C[m] + sp
        return g['w'] * (g['bank'] + rem * g['d'] * (px - g['e']) / g['sd'])
    def shut(g, px, m, why):
        nonlocal banked
        rem = 1 - g['pt'] if g['half'] else 1.0
        g['r'] = g['bank'] + rem * g['d'] * (px - g['e']) / g['sd']; banked += g['w'] * g['r']
        g.update(on=False, ex=float(px), ext=B['t'][m], status=why)
    last = min(ce, now_idx)
    for m in range(j0, last + 1):
        if m == ce and full_day:
            for g in legs:
                if g['on']: shut(g, O[m] if g['d'] > 0 else O[m] + sp, m, 'eod')
            break
        if m in byj and not off:
            (j, oi, nm, d, px) = byj[m]; tm = B['t'][j]; hm = tm.hour * 60 + tm.minute
            late = hm >= P['last'] or (tm.dayofweek == 4 and hm >= P['fri_last'])
            if not late:
                s_ = (P['buy_stop'] if d > 0 else P['sell_stop']) * A[j]
                e = px + sp if d > 0 else px; sl = px - s_ if d > 0 else px + sp + s_
                legs.append(dict(j=j, oi=oi, name=nm, d=d, px=px, e=e, sl=sl, sl0=sl, sd=s_, w=(1.0 if d > 0 else P['sell_w']),
                                 pt=(P['part_buy'] if d > 0 else P['part_sell']), A=A[j], xt=e,
                                 hp=e + d * P['k'] * abs(e - sl), half=False, half_t=None, bank=0.0, on=True, r=None, ex=None, ext=None, status='open'))
        for g in legs:
            if not g['on'] or m <= g['j']: continue
            d = g['d']
            if (d > 0 and L[m] <= g['sl']) or (d < 0 and H[m] + sp >= g['sl']):
                px = min(g['sl'], O[m]) if d > 0 else max(g['sl'], O[m] + sp)
                why = 'stopped' if not g['half'] else ('be' if abs(g['sl'] - g['e']) < 1e-9 else 'trail')
                shut(g, px, m, why); continue
            if not g['half'] and ((d > 0 and H[m] >= g['hp']) or (d < 0 and L[m] + sp <= g['hp'])):
                g['bank'] = g['pt'] * d * (g['hp'] - g['e']) / g['sd']; g['half'] = True; g['half_t'] = B['t'][m]
                g['sl'] = max(g['sl'], g['e']) if d > 0 else min(g['sl'], g['e'])
            if g['half'] and P['trail'] > 0:
                if d > 0:
                    g['xt'] = max(g['xt'], H[m]); ts = g['xt'] - P['trail'] * g['A']
                    if ts > g['sl']: g['sl'] = ts
                else:
                    g['xt'] = min(g['xt'], L[m] + sp); ts = g['xt'] + P['trail'] * g['A']
                    if ts < g['sl']: g['sl'] = ts
        tot = banked + sum(mark(g, m) for g in legs if g['on']); peak = max(peak, tot)
        if P['lock_pk'] > 0 and not off and peak >= P['lock_pk'] and tot <= P['lock_fl']:
            for g in legs:
                if g['on']: shut(g, C[m] if g['d'] > 0 else C[m] + sp, m, 'day lock')
            off = True
    for g in legs:
        g['r_now'] = g['r'] if g['r'] is not None else (g['bank'] + (1 - g['pt'] if g['half'] else 1.0) * g['d'] *
                                                       ((C[last] if g['d'] > 0 else C[last] + sp) - g['e']) / g['sd'])
        g['locked_day'] = off
    return legs

def run_day(m, day, now=None, S=None, exits=None, sp=1.8):
    """m: minute bars (broker time) of the last ~300 days INCLUDING today's closed minutes; returns today's paper trades."""
    day = pd.Timestamp(day).normalize(); m = m[(m.index < day + pd.Timedelta(days=1))]
    if now is not None: m = m[m.index + pd.Timedelta(minutes=1) <= now]
    if not len(m) or m.index[-1].normalize() != day: return []
    S = S or SET
    eng = engine_first(m, day) if S.get('engine') else None
    with tempfile.TemporaryDirectory() as td:
        B = build_base(m, td, eng, open_last=now is not None and now < day + pd.Timedelta(minutes=eod_minutes(day)))
        k_today = int(B['dcode'][-1])
        if not np.isfinite(B['A'][-1]): return []
        names = S['core'] + S['fill']
        need_b = any(n.replace('REV ', '', 1).startswith('US+10 ') for n in names)
        fa = ideas('a', td); fb = ideas('b', td) if need_b else {}
        _purge()
        ev = day_events(B, names, fa, fb, k_today)
    nc = len(S['core'])
    c = first_trade([e for e in ev if e[1] < nc]); f = first_trade([e for e in ev if e[1] >= nc])
    picks = ([c] if c else []) + ([f] if f and (c is None or f[0] < c[0]) else [])
    LAST_PICKS.clear(); LAST_PICKS.update(day=str(day.date()), picks=[(str(B['t'][j]), int(d)) for (j, oi, nm, d, px) in sorted(picks)])
    trades = []
    if exits in ('v1.01', 'v1.02'):
        legs = manage_v101(B, sorted(picks), len(B['O']) - 1, sp) if exits == 'v1.01' else manage_v102(B, sorted(picks), len(B['O']) - 1, sp)
        for g in legs:
            pt = g.get('pt', V101['part'])
            pts = None if g['r'] is None else g['w'] * ((pt * g['d'] * (g['hp'] - g['e']) if g['half'] else 0.0) +
                                                       (1 - pt if g['half'] else 1.0) * g['d'] * (g['ex'] - g['e']))
            trades.append(dict(t=B['t'][g['j']], j=g['j'], name=g['name'], role='core' if g['oi'] < nc else 'filler', dir=g['d'], px=g['px'], entry=g['e'],
                               stop=float(g['sl']), stop0=float(g['sl0']), half_px=float(g['hp']), half=g['half'], half_t=g['half_t'],
                               size='full' if g['w'] >= 1 else 'third', w=g['w'], sd=float(g['sd']), A=float(B['A'][g['j']]), status=g['status'],
                               exit=g['ex'], exit_t=g['ext'], r=g['r'], r_now=g['r_now'], pts=pts, locked_day=g['locked_day'], part=pt))
        return trades
    for (j, oi, nm, d, px) in sorted(picks):
        stop, st, ex, ext = manage(B, j, d, px, len(B['O']) - 1, S['stop'])
        trades.append(dict(t=B['t'][j], j=j, name=nm, role='core' if oi < nc else 'filler', dir=d, px=px, stop=float(stop),
                           A=float(B['A'][j]), status=st, exit=None if ex is None else float(ex), exit_t=ext))
    return trades
