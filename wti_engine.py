"""WTI_DAYTRADE v1.02 rules as a PAPER engine for the Signal Desk - same logic as the EA / its line-by-line Python port
(wti_ea_port.py: 4,300 of 4,300 MT4 trades 2020-2026 same minute and direction). Prices are Bid; broker clock = New York + 7 h.
History = finished broker days: [date 'YYYY-MM-DD', open, high, low, close, settle] where settle = open of the first bar 21:30-21:35.
Rules:
 - range A = mean (high - low) of the 14 previous days; trade only if A exists and the previous day is <= 3 calendar days back.
 - 7 level families, each gives at most ONE trade a day (its first touched level), break direction, scanned from its start bar
   to the close bar (first bar >= 23:00, Friday 22:50):
   1 yesterday's settlement (start 16:00-16:05)   2-4 day open +/- 0.5 / 0.7 / 1.0 x yesterday's range (start: the day's 2nd bar)
   5 yesterday's high / low (start 7:00-7:05)     6 last week's high / low (start 2:00-2:05)
   7 nearest whole dollar below / above the 10:00 price (only if >= 0.15 x A away; start 10:00-10:05)
   A level counts only if the start-bar open is >= 0.05 x A away. Touch = a bar trades THROUGH the level by 1 cent;
   signal price = the level (or the bar open if it opened beyond) + the MT4-like slip (1.3-2.5 cents by the minute's range),
   which reproduced his MT4 fills (direction 53.0% 2020-26).
 - LADDER: the day's first trade either way; later trades only the same way; same minute + same way = one trade.
 - EXIT: stop 0.25 x A from the signal price (checked from the next bar, gap-aware), else close at the open of the close bar.
 - SIZE (v1.02): sells from the day's 2nd trade on = full size, every other trade = 1/3.
 - Right way first = +0.3 A before -0.3 A from the signal price, until the close bar (same bar both = undecided)."""
import numpy as np, pandas as pd

KEEP_DAYS = 60
SLIP = True                     # False only for the parity test against the no-slip EA port
EDG = (0.05, 0.10, 0.20, 0.40); SLP = (0.013, 0.017, 0.020, 0.023, 0.025)   # MT4-like slip by the signal minute's range (calibrated on his MT4 run 1: 53.0%)
STOP_X, RWF_X, MIN_DIST, ROUND_GAP = 0.25, 0.3, 0.05, 0.15
FAM_NAME = {'settle': "Yesterday's settlement", 'open+-0.5': 'Open ± ½ range', 'open+-0.7': 'Open ± 0.7 range', 'open+-1.0': 'Open ± 1 range',
            'yday': "Yesterday's high/low", 'lastweek': "Last week's high/low", 'round1': 'Whole dollar'}

def close_hm(day):
    return 22 * 60 + 50 if pd.Timestamp(day).dayofweek == 4 else 23 * 60

def daily_from_minutes(t, o, h, l, c):
    """One finished broker day of minute bars (broker times) -> [open, high, low, close, settle]."""
    t = pd.DatetimeIndex(t); hm = t.hour * 60 + t.minute
    s = np.flatnonzero((hm >= 21 * 60 + 30) & (hm <= 21 * 60 + 35))
    return [float(o[0]), float(np.max(h)), float(np.min(l)), float(c[-1]), (float(o[s[0]]) if len(s) else None)]

def prep(hist, day):
    """Levels input for `day` from finished history rows (oldest first). Returns None when the EA would not trade the day."""
    day = pd.Timestamp(day).normalize()
    H = [r for r in hist if pd.Timestamp(r[0]) < day]
    if len(H) < 15: return None
    prev = H[-1]; pd_ = pd.Timestamp(prev[0])
    if (day - pd_).days > 3: return None
    rng = [r[2] - r[3] for r in H[-14:]]; A = float(np.mean(rng))
    wk = day.to_period('W'); lw = [r for r in H if pd.Timestamp(r[0]).to_period('W') == wk - 1]
    return dict(A=A, yhi=prev[2], ylo=prev[3], yrange=prev[2] - prev[3], settle=prev[5],
                lwh=(max(r[2] for r in lw) if lw else np.nan), lwl=(min(r[3] for r in lw) if lw else np.nan))

def run_day(P, t, O, H, L, C, now=None, spread=None, final=False):
    """P = prep(...); t/O/H/L/C = today's minute bars so far (broker times, closed bars only). Returns the day's ladder trades with their
    state as of `now` (default: end of the bars). A trade is reported only once its signal bar has closed. final=True (the broker day is over):
    a day with no close bar (holiday early close) closes open trades at the last bar's close, like the EA port."""
    if P is None or len(t) == 0: return []
    t = pd.DatetimeIndex(t); O, H, L, C = (np.asarray(x, float) for x in (O, H, L, C)); n = len(t)
    hm = (t.hour * 60 + t.minute).values; day = t[0].normalize(); lim = close_hm(day)
    eod = int(np.searchsorted(hm, lim)); has_close = eod < n           # index of the close bar if it already exists
    end = min(eod, n)                                                   # signals are scanned up to (not incl.) the close bar
    def at(x, slack=5):
        p = int(np.searchsorted(hm, x)); return p if p < n and hm[p] <= x + slack else -1
    A = P['A']; fams = []
    a = at(16 * 60); fams.append(('settle', a, [P['settle']] if P['settle'] is not None else []))
    for x in (0.5, 0.7, 1.0): fams.append((f'open+-{x}', 1, [O[0] + x * P['yrange'], O[0] - x * P['yrange']]))
    fams.append(('yday', at(7 * 60), [P['yhi'], P['ylo']]))
    fams.append(('lastweek', at(2 * 60), [P['lwh'], P['lwl']]))
    a = at(10 * 60)
    if a >= 0:
        p0 = O[a]; fl, ce = np.floor(p0), np.ceil(p0)
        fams.append(('round1', a, [fl if p0 - fl > ROUND_GAP * A else np.nan, ce if ce - p0 > ROUND_GAP * A else np.nan]))
    EV = []
    for fi, (nm, a, lvls) in enumerate(fams):
        if a < 0 or a >= end: continue
        best = None
        for lv in lvls:
            if lv is None or not np.isfinite(lv): continue
            side = 1 if O[a] > lv else -1
            if abs(O[a] - lv) < MIN_DIST * A: continue
            for m in range(a, end):
                if (side > 0 and L[m] <= lv - 0.01) or (side < 0 and H[m] >= lv + 0.01):
                    if best is None or m < best[0]: best = (m, lv, -side)
                    break
        if best:
            m, lv, d = best; px = max(lv, O[m]) if d > 0 else min(lv, O[m])
            r = H[m] - L[m]; j = 0
            while j < 4 and r > EDG[j]: j += 1
            EV.append((m, fi, d, px + (d * SLP[j] if SLIP else 0.0), nm, lv))
    EV.sort(key=lambda r: (r[0], r[1]))
    kept = []; net = 0; lj = -1; ld = 0
    for m, fi, d, px, nm, lv in EV:
        if net != 0 and np.sign(net) != d: continue
        if m == lj and d == ld: continue
        kept.append((m, d, px, nm, lv)); net += d; lj = m; ld = d
    out = []
    for i, (m, d, px, nm, lv) in enumerate(kept):
        stop = px - d * STOP_X * A; ex = None; ex_i = None; why = None
        for q in range(m + 1, n):
            if q == eod: ex, ex_i, why = O[q], q, 'eod'; break
            if d > 0:
                if O[q] <= stop: ex, ex_i, why = O[q], q, 'stopped'; break
                if L[q] <= stop: ex, ex_i, why = stop, q, 'stopped'; break
            else:
                if O[q] >= stop: ex, ex_i, why = O[q], q, 'stopped'; break
                if H[q] >= stop: ex, ex_i, why = stop, q, 'stopped'; break
        if why is None and final and not has_close: ex, ex_i, why = C[n - 1], n - 1, 'eod'
        rwf = None; tg = RWF_X * A; last = min(eod, n - 1) if has_close else n - 1
        decided = False
        for q in range(m + 1, last + 1):
            up = (H[q] - px) if d > 0 else (px - L[q]); dn = (px - L[q]) if d > 0 else (H[q] - px)
            if up >= tg and dn >= tg: decided = True; break
            if up >= tg: rwf = 1; decided = True; break
            if dn >= tg: rwf = 0; decided = True; break
        sp = None if spread is None else float(spread[m]) if np.isfinite(spread[m]) else None
        full = (d < 0 and i >= 1)
        out.append(dict(i=m, t=t[m], dir=d, px=float(px), level=float(lv), fam=nm, name=FAM_NAME[nm], stop=float(stop), first=(i == 0),
                        size='full' if full else '1/3', status=('open' if why is None else why), exit=(None if ex is None else float(ex)),
                        exit_t=(None if ex_i is None else t[ex_i]), rwf=rwf, rwf_final=decided or has_close or final, A=A, spread=sp))
    return out
