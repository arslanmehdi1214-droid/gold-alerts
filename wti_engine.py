"""WTI_DAYTRADE v1.07 rules (= v1.06 + P['later_buys_off']: a BUY only as the day's FIRST trade, later buy signals skipped; his MT4 run 26 Oct 2026)
v1.06 rules (= v1.05 + P['expiry_first_only']: on the WTI option-expiry day only the day's FIRST trade; + P['hold_sells']: production rose in the last
EIA report AND yesterday's close < its 50-day average -> that day's SELLS keep the whole trade: no part-close, no stop to entry; his MT4 run 23 Oct 2026)
v1.05 rules (= v1.04 + the day's FIRST trade, if a SELL, is FULL size when P['first_sell_full'] is set: last EIA Cushing report = build AND yesterday's close < close 5 trading days earlier; his MT4 run 20 Oct 2026)
(v1.04 = v1.03 + part-close 25% instead of 50%) as a PAPER engine for the Signal Desk - same logic as the EA / its line-by-line Python port
(wti_ea_port.py: 4,300 of 4,300 MT4 trades 2020-2026 same minute and direction). Prices are Bid; broker clock = New York + 7 h.
History = finished broker days: [date 'YYYY-MM-DD', open, high, low, close, settle] where settle = open of the first bar 21:30-21:35.
Rules:
 - range A = mean (high - low) of the 14 previous days; trade only if A exists and the previous day is <= 3 calendar days back.
 - 7 level families, each gives at most ONE trade a day (its first touched level), break direction, scanned from its start bar
   to the close bar (first bar >= 20:00 broker):
   1 yesterday's settlement (start 16:00-16:05)   2-4 day open +/- 0.5 / 0.7 / 1.0 x yesterday's range (start: the day's 2nd bar)
   5 yesterday's high / low (start 7:00-7:05)     6 last week's high / low (start 2:00-2:05)
   7 nearest whole dollar below / above the 10:00 price (only if >= 0.15 x A away; start 10:00-10:05)
   A level counts only if the start-bar open is >= 0.05 x A away. Touch = a bar trades THROUGH the level by 1 cent;
   signal price = the level (or the bar open if it opened beyond) + the MT4-like slip (1.3-2.5 cents by the minute's range),
   which reproduced his MT4 fills (direction 53.0% 2020-26).
 - LADDER: the day's first trade either way; later trades only the same way; same minute + same way = one trade.
 - v1.03 ENTRY TIMES: no new trade from 16:30 broker, except ONE first trade until 19:00 on a day with no trade yet.
 - v1.03 EXITS: stop buys 1.0 x A, sells 0.75 x A; half-close at +0.05 (buys) / +0.15 (sells) x the trade's risk, then the rest's stop
   goes to the entry price; day lock: once the day is +2R, close all if it falls back to +1R (no more trades); everything closes at 20:00
   broker (Fridays too) at the close bar's open.
 - v1.03 SIZE: first trade 1/3, buys 1/3, later sells full while the day is in profit (R, marked at the signal price), else 1/3.
 - Right way first = +0.3 A before -0.3 A from the signal price, until the close bar (same bar both = undecided)."""
import numpy as np, pandas as pd

KEEP_DAYS = 60
SLIP = True                     # False only for the parity test against the no-slip EA port
EDG = (0.05, 0.10, 0.20, 0.40); SLP = (0.013, 0.017, 0.020, 0.023, 0.025)   # MT4-like slip by the signal minute's range (calibrated on his MT4 run 1: 53.0%)
RWF_X, MIN_DIST, ROUND_GAP = 0.3, 0.05, 0.15
# ---- v1.03 exits / times / sizes (same inputs as the EA WTI_DAYTRADE v1.03, his MT4 runs 18 Oct 2026)
BUY_STOP, SELL_STOP = 1.00, 0.75          # x 14-day range
BUY_HALF, SELL_HALF = 0.05, 0.15          # close PART at +k x the trade's risk, then the rest's stop goes to the entry price
PART = 0.25                               # v1.04: part closed at that level (v1.03 = 0.5)
LOCK_PEAK, LOCK_FLOOR = 2.0, 1.0          # day up +2R -> close all if it falls back to +1R; no more trades that day
LAST_ENTRY, LATE_FIRST, CLOSE_HM = 16 * 60 + 30, 19 * 60, 20 * 60      # broker minutes
MIN_SP = 0.02
FIX_SP = 0.04                             # 23 Oct fix: ONE fixed spread (4 cents = the MT4 test's spread 4 and Capital.com's usual) for entry,
                                          # stop, part level and P/L. Capital.com re-sends a different ask for the same finished minute, so the
                                          # live spread made shown stops / part levels change after the fact.
FAM_NAME = {'settle': "Yesterday's settlement", 'open+-0.5': 'Open ± ½ range', 'open+-0.7': 'Open ± 0.7 range', 'open+-1.0': 'Open ± 1 range',
            'yday': "Yesterday's high/low", 'lastweek': "Last week's high/low", 'round1': 'Whole dollar',
            'open_b': 'Day open (buy)', 'morn_b': 'Morning high (buy)'}

def close_hm(day):
    return CLOSE_HM                                                     # v1.03: 20:00 broker every day (Fridays too)

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
    return dict(wf=weak_dayfeat(H), A=A, yhi=prev[2], ylo=prev[3], yrange=prev[2] - prev[3], settle=prev[5],
                lwh=(max(r[2] for r in lw) if lw else np.nan), lwl=(min(r[3] for r in lw) if lw else np.nan))


# ---- v1.08 (1 Nov 2026): weak-entry downsize. A fixed logistic score (28 numbers, trained on 2011-2019 only; same numbers as the EA WTI_DAYTRADE v1.08 wCoef/wBias)
# is computed for every entry from the daily bars known before the entry; entries at or below the cut (bottom third) trade at WEAK_SIZE x their normal size.
WEAK_SIZE = 0.5
WEAK_FEATS = ["dir", "A", "first", "late", "min", "dow", "k", "f_lastweek", "f_open+-0.5", "f_open+-0.7", "f_open+-1.0", "f_round1", "f_settle", "f_yday", "mo3", "mo5", "mo8", "mo13", "ret1", "ret2", "pos20", "pos60", "clpos", "rng", "rng_z", "rv5", "rv20", "gap"]
WEAK_COEF = [-0.5352394806450879, -0.02830949921719838, 0.005116710210724173, 0.0, 0.0005147930923764709, -0.0012416927151276463, 0.08453939361160567, -0.22943521702675845, 0.18493028315074325, -0.002804805016805929, 0.05083154959690975, -0.03976765427206761, -0.15652653320503077, 0.0043576513682883665, 0.0038262385505347892, -0.019763965909276662, 0.017818503255894545, -0.012670375713047766, 0.06691811936848882, 0.01918147038914972, -0.34272854653997986, -0.4223363180261314, -0.4918263562071827, -0.05836813577194137, -0.11891213291886576, -0.031067116439657542, -0.032135105767732375, 0.190623657629336]
WEAK_B = -0.928435081404478
WEAK_THR = -1.7276181366535104
WEAK_FAMS = ['lastweek', 'open+-0.5', 'open+-0.7', 'open+-1.0', 'round1', 'settle', 'yday']

def weak_dayfeat(H):
    """Daily features for the day AFTER the finished rows H ([date, o, h, l, c, settle], oldest first); None if fewer than 63 rows."""
    i = len(H)
    if i < 63: return None
    c = np.array([r[4] for r in H], float); h = np.array([r[2] for r in H], float); l = np.array([r[3] for r in H], float)
    f = {}
    for k in (3, 5, 8, 13): f[f'mo{k}'] = (c[i - 1] / c[i - 1 - k] - 1) * 100
    f['ret1'] = (c[i - 1] / c[i - 2] - 1) * 100; f['ret2'] = (c[i - 2] / c[i - 3] - 1) * 100
    for n in (20, 60):
        w = c[i - n:i]; f[f'pos{n}'] = (c[i - 1] - w.min()) / (w.max() - w.min())
    f['clpos'] = (c[i - 1] - l[i - 1]) / (h[i - 1] - l[i - 1]); f['rng'] = (h[i - 1] - l[i - 1]) / c[i - 1] * 100
    rr = (h[i - 60:i] - l[i - 60:i]) / c[i - 60:i]; f['rng_z'] = rr[-1] / rr.mean()
    for n in (5, 20):
        r = c[i - n:i] / c[i - n - 1:i - 1] - 1; f[f'rv{n}'] = r.std(ddof=1) * 100
    f['pc'] = float(c[i - 1])
    return f

def weak_score(wf, day_open, d, nm, A, k, mn, dow):
    """Score of one entry (higher = better); None if it cannot be computed (then the entry keeps its normal size)."""
    if wf is None or nm not in WEAK_FAMS: return None
    r = dict(wf); r['gap'] = (day_open / wf['pc'] - 1) * 100
    r.update({'dir': d, 'A': A, 'first': int(k == 0), 'late': int(mn >= 1630), 'min': mn, 'dow': dow, 'k': k})
    for x in WEAK_FAMS: r['f_' + x] = 1.0 if x == nm else 0.0
    return float(sum(c_ * r[n_] for c_, n_ in zip(WEAK_COEF, WEAK_FEATS)) + WEAK_B)

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
    if P.get('buyl'):                                    # v1.14: two buy-only level families (a break UP through a level the price is below = a buy, once a day each)
        fams.append(('open_b', at(7 * 60), [O[0]]))      #   the day open, watched from 7:00 broker
        _a10 = at(10 * 60)
        if _a10 >= 1: fams.append(('morn_b', _a10, [float(np.max(H[:_a10]))]))   # the high of 0:00-10:00, set at 10:00
    EV = []
    for fi, (nm, a, lvls) in enumerate(fams):
        if a < 0 or a >= end: continue
        best = None
        for lv in lvls:
            if lv is None or not np.isfinite(lv): continue
            side = 1 if O[a] > lv else -1
            if nm in ('open_b', 'morn_b') and side > 0: continue      # v1.14: buy-only families (price must start BELOW the level)
            if abs(O[a] - lv) < P.get('mind', MIN_DIST) * A: continue   # v1.13: closer levels count (P['mind'] = 0.0125 from v1.13, else the old 0.05)
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
    SK = None
    if P.get('skew'):                                    # v1.12: causal 5-minute down-vs-up squared-move flow, from completed 5-min bars (minute :04, :09 ...) strictly before bar m
        _c = pd.Series(C, index=t); _bc = _c[t.minute % 5 == 4]; _r = np.log(_bc).diff().fillna(0.0)
        _dn = (_r.clip(upper=0) ** 2).cumsum(); _up = (_r.clip(lower=0) ** 2).cumsum()
        SK = ((_dn - _up) / (_dn + _up).replace(0, np.nan)).fillna(0.0).reindex(t, method='ffill').shift(1).fillna(0.0).values
    def SPm(m): return FIX_SP              # 23 Oct: fixed spread; the `spread` argument is accepted for old callers but no longer used
    bym = {}
    for ev in EV: bym.setdefault(ev[0], []).append(ev)
    legs = []; banked = 0.0; peak = 0.0; off = False; ddir = 0; lastm = -1; lastd = 0; off_i = None
    def mark(g, bid):                                   # leg result in R x its size, at a bid price
        px = bid if g['dir'] > 0 else bid + g['sp']
        return g['w'] * (g['bank'] + g['q'] * g['dir'] * (px - g['e']) / g['sd'])
    def close_leg(g, bid, q_i, why):
        nonlocal banked
        px = bid if g['dir'] > 0 else bid + g['sp']
        g['bank'] += g['q'] * g['dir'] * (px - g['e']) / g['sd']; g['q'] = 0.0; g['on'] = False
        g['exit'], g['exit_i'], g['why'] = float(bid), q_i, why; banked += g['w'] * g['bank']
    m0 = EV[0][0] if EV else n
    for m in range(m0, n):
        if m == eod:                                                    # 20:00 broker close: everything out at the close bar's open
            for g in legs:
                if g['on']: close_leg(g, O[m], m, 'eod')
            break
        for (mm, fi, d, px, nm, lv) in bym.get(m, []):
            if off: continue
            if hm[m] >= LAST_ENTRY and not (len(legs) == 0 and hm[m] < LATE_FIRST): continue
            if P.get('expiry_first_only') and len(legs) > 0: continue                 # v1.06: option-expiry day = only the first trade
            if P.get('later_buys_off') and d > 0 and len(legs) > 0: continue          # v1.07: a buy only as the day's first trade
            if ddir != 0 and d != ddir: continue
            if m == lastm and d == lastd: continue
            sd = (BUY_STOP if d > 0 else SELL_STOP) * A; sp = SPm(m)
            st = banked + sum(mark(g, px) for g in legs if g['on'])
            w = ((1.0 if (d < 0 and P.get('first_sell_full')) else 1 / 3) if len(legs) == 0 else ((1.0 if st > 0 else 1 / 3) if d < 0 else 1.0))   # v1.05 first sell
            if d > 0: w = min(w, 1 / 3)
            weak = False
            if P.get('weak_down'):                                                     # v1.08: bottom-third entries trade at half their size
                z_ = weak_score(P.get('wf'), O[0], d, nm, A, len(legs), int(hm[m]), day.dayofweek)
                if z_ is not None and z_ <= WEAK_THR: w = w * WEAK_SIZE; weak = True
            e = px + sp if d > 0 else px                                   # buy fills at the ask, sell at the bid
            stop_b = px - sd if d > 0 else px + sd                          # stop in BID terms (sell stop = ask + sd)
            rk = sd + sp; k = BUY_HALF if d > 0 else SELL_HALF
            if SK is not None and d < 0 and SK[m] <= P['skew'][0]: k = min(k, P['skew'][1])   # v1.12: weak-flow ladder sell -> easier first target from the start
            hp = e + d * k * rk                                             # half level in the order's own price (buy: bid, sell: ask)
            nohalf = bool(d < 0 and P.get('hold_sells'))                    # v1.06: supply day -> sells keep the whole trade (no part, no stop move)
            legs.append(dict(i=m, t=t[m], dir=d, px=float(px), level=float(lv), fam=nm, name=FAM_NAME[nm], sd=sd, sp=sp, e=e, w=w,
                             stop0=float(stop_b), stop=float(stop_b), half_px=(None if nohalf else float(hp if d > 0 else hp - sp)), half=False, bank=0.0, q=1.0,
                             on=True, exit=None, exit_i=None, why=None, late=bool(hm[m] >= LAST_ENTRY), first=(len(legs) == 0), weak=weak))
            if ddir == 0: ddir = d
            lastm, lastd = m, d
        for g in legs:                                                  # bar m: stop first (gap-aware), then the half-close
            if not g['on'] or m <= g['i']: continue
            d = g['dir']
            if (d > 0 and L[m] <= g['stop']) or (d < 0 and H[m] >= g['stop']):
                b = min(g['stop'], O[m]) if d > 0 else max(g['stop'], O[m])
                close_leg(g, b, m, 'be' if g['half'] else 'stopped'); continue
            if P.get('decay') and not g['half'] and g['half_px'] is not None and not g.get('dec') and (t[m] - t[g['i']]) >= pd.Timedelta(minutes=P['decay'][0]):
                g['dec'] = True; kk = P['decay'][1] if d < 0 else P['decay'][2]; rk_ = g['sd'] + g['sp']      # v1.11: still no part-close after DECAY minutes -> the part-close level drops to kk x the trade's risk (ladder trades only)
                g['half_px'] = float(g['e'] - kk * rk_ - g['sp']) if d < 0 else float(g['e'] + kk * rk_)
            if not g['half'] and g['half_px'] is not None and ((d > 0 and H[m] >= g['half_px']) or (d < 0 and L[m] <= g['half_px'])):
                g['bank'] += PART * d * ((g['half_px'] if d > 0 else g['half_px'] + g['sp']) - g['e']) / g['sd']; g['q'] = 1.0 - PART; g['half'] = True
                g['half_t'] = t[m]; g['stop'] = float(g['e'] if d > 0 else g['e'] - g['sp'])      # rest's stop = entry price (bid terms)
        tot = banked + sum(mark(g, C[m]) for g in legs if g['on']); peak = max(peak, tot)
        if not off and peak >= LOCK_PEAK and tot <= LOCK_FLOOR:
            for g in legs:
                if g['on']: close_leg(g, C[m], m, 'day lock')
            off = True; off_i = m
    if final and not has_close:
        for g in legs:
            if g['on']: close_leg(g, C[n - 1], n - 1, 'eod')
    out = []
    for g in legs:
        m, d, px = g['i'], g['dir'], g['px']
        rwf = None; tg = RWF_X * A; last = min(eod, n - 1) if has_close else n - 1; decided = False
        for q in range(m + 1, last + 1):
            up = (H[q] - px) if d > 0 else (px - L[q]); dn = (px - L[q]) if d > 0 else (H[q] - px)
            if up >= tg and dn >= tg: decided = True; break
            if up >= tg: rwf = 1; decided = True; break
            if dn >= tg: rwf = 0; decided = True; break
        res = None if g['on'] else round(g['bank'] * g['sd'], 4)          # $ per barrel for a FULL-size trade, spread included
        out.append(dict(i=m, t=t[m], dir=d, px=px, level=g['level'], fam=g['fam'], name=g['name'], stop=g['stop'], stop0=g['stop0'],
                        half_px=g['half_px'], half=g['half'], part=(None if g['half_px'] is None else PART), first=g['first'], late=g['late'], size=('full' if g['w'] == 1.0 else '1/3' if abs(g['w'] - 1 / 3) < 1e-9 else round(g['w'], 6)), weak=bool(g.get('weak')),
                        status=('open' if g['on'] else g['why']), exit=g['exit'], exit_t=(None if g['exit_i'] is None else t[g['exit_i']]),
                        res=res, R=(None if g['on'] else round(g['bank'], 4)), rwf=rwf, rwf_final=decided or has_close or final, A=A, spread=g['sp']))
    return out

# ---- v1.10 (2 Nov 2026): SIDE SELL after a weak close. At the 7:00 broker bar, if yesterday's 21:30 price (settle) sits in the bottom SIDE_MAX_POS of
# yesterday's range AND the ladder has not traded before that bar, sell once at SIDE_SIZE x full size. Own stop (0.75 x A), half-close at +0.15 risk
# (part PART), rest's stop to entry, closed at the 20:00 close bar. Independent of the ladder (no day state, no day lock). Same numbers as the EA row 46-49.
SIDE_MAX_POS, SIDE_SIZE = 0.20, 0.25

def side_sell(P, t, O, H, L, C, ladder_legs, final=False):
    """Returns [] or one leg dict (same keys as run_day legs, side=True). ladder_legs = run_day's output for the same day."""
    if P is None or len(t) == 0: return []
    t = pd.DatetimeIndex(t); O, H, L, C = (np.asarray(x, float) for x in (O, H, L, C)); n = len(t)
    hm = (t.hour * 60 + t.minute).values
    s = np.flatnonzero((hm >= 420) & (hm <= 425))
    if len(s) == 0: return []
    ms = int(s[0]); yH, yL, st = P['yhi'], P['ylo'], P['settle']
    if st is None or yH <= yL or st <= 0 or (st - yL) / (yH - yL) > SIDE_MAX_POS: return []
    if any(g['i'] < ms for g in ladder_legs): return []                 # the ladder traded before 7:00 -> no side sell
    A = P['A']; sd = SELL_STOP * A; sp = FIX_SP; e = float(O[ms]); stop = e + sd; rk = sd + sp; hp = e - SELL_HALF * rk - sp
    eod = int(np.searchsorted(hm, close_hm(t[0]))); has_close = eod < n
    bank = 0.0; q = 1.0; half = False; why = None; xi = None; xb = None
    for m in range(ms + 1, n):
        if m == eod: xb, xi, why = O[m], m, 'eod'; break
        if H[m] >= stop:
            xb, xi, why = max(stop, O[m]), m, ('be' if half else 'stopped'); break
        if not half and L[m] <= hp:
            bank += PART * -1 * ((hp + sp) - e) / sd; q = 1.0 - PART; half = True; stop = e - sp
    if why is None and final and not has_close: xb, xi, why = C[n - 1], n - 1, 'eod'
    if why is not None: bank += q * -1 * ((xb + sp) - e) / sd
    return [dict(i=ms, t=t[ms], dir=-1, px=e, fam='side', name='Side sell (weak close)', stop0=float(e + sd), stop=float(stop), half_px=float(hp), half=half,
                 part=PART, first=False, late=False, size=SIDE_SIZE, weak=False, side=True, status=('open' if why is None else why), exit=(None if xb is None else float(xb)),
                 exit_t=(None if xi is None else t[xi]), res=(None if why is None else round(bank * sd, 4)), R=(None if why is None else round(bank, 4)), A=A, spread=sp, rwf=None, rwf_final=True)]
