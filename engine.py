"""GOLD_DAYTRADE v1.9 (DT19_GOLD_M5 settings) signal engine - Python port of the MT4 EA.
All times are BROKER time (= New York time + 7 hours, RoboForex/MT4 style)."""
import numpy as np, pandas as pd

LAST = {}
P = dict(first_hours=set(range(3, 15)), first_body=0.1, atr_period=14, jl=14, go=11, gm=18,
         yesterday_cut=0.2, later_min=5, later_last_hour=14, grade_lo=48, grade_hi=72,
         stop=0.75, target=2.4, be_trig=0.15, be_lock=0.02, close_hour=23, fri_close=2250,
         datr_days=14, ema_days=50)

# ---------------- indicators (same as the tested Python mirror) ----------------
def jtpo(c, L=14):
    from scipy.stats import rankdata
    n = len(c); out = np.zeros(n, int); tt = np.arange(L) - (L - 1) / 2
    for i in range(L - 1, n):
        w = c[i - L + 1:i + 1]
        if w.max() == w.min(): continue
        out[i] = int(np.sign(np.sum((rankdata(w) - (L + 1) / 2) * tt)))
    return out

def grucha(o, c, ok=11, ma=18):
    d = o - c
    up = pd.Series(np.where(d < 0, -d, 0.0)).rolling(ok).sum().values
    dn = pd.Series(np.where(d >= 0, d, 0.0)).rolling(ok).sum().values
    s = up + dn
    with np.errstate(invalid='ignore', divide='ignore'): w = np.where(s > 0, up / s * 100, 0.0)
    w[:ok - 1] = np.nan; m = pd.Series(w).rolling(ma).mean().values
    return np.nan_to_num(np.sign(w - m)).astype(int)

def atr_sma(h, l, c, n=14):   # MT4 iATR = simple average of true range
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).rolling(n).mean().values

def rsi_wilder(c, n=14):      # MT4 iRSI
    d = np.diff(c, prepend=np.nan)
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    out = np.full(len(c), np.nan)
    if len(c) <= n: return out
    au = up[1:n + 1].mean(); ad = dn[1:n + 1].mean()
    out[n] = 100 if ad == 0 else 100 - 100 / (1 + au / ad)
    for i in range(n + 1, len(c)):
        au = (au * (n - 1) + up[i]) / n; ad = (ad * (n - 1) + dn[i]) / n
        out[i] = 100 if ad == 0 else 100 - 100 / (1 + au / ad)
    return out

# ---------------- bar preparation ----------------
def prepare(h1):
    """h1: DataFrame index=broker time (bar open), columns o,h,l,c. Returns dict of derived series."""
    h1 = h1.sort_index()
    o, h, l, c = (h1[k].values.astype(float) for k in 'ohlc')
    H1 = h1.copy()
    H1['J'] = jtpo(c, P['jl']); H1['G'] = grucha(o, c, P['go'], P['gm']); H1['atr'] = atr_sma(h, l, c, P['atr_period'])
    day = H1.index.normalize()
    D1 = H1.groupby(day).agg(o=('o', 'first'), h=('h', 'max'), l=('l', 'min'), c=('c', 'last'))
    D1['J'] = jtpo(D1.c.values, P['jl']); D1['G'] = grucha(D1.o.values, D1.c.values, P['go'], P['gm'])
    D1['ema'] = D1.c.ewm(span=P['ema_days'], adjust=False).mean()
    D1['rng'] = D1.h - D1.l
    H4 = H1.groupby(H1.index.floor('4h')).agg(c=('c', 'last'))
    H4['rsi'] = rsi_wilder(H4.c.values, 14)
    return dict(H1=H1, D1=D1, H4=H4)

# ---------------- one broker day ----------------
def replay_day(S, day, m1, yd, sd):
    """S = prepare() output, day = broker date (Timestamp), m1 = that day's 1-min bars (index broker time, o h l c),
    yd/sd = US 10y yield / S&P 5-day direction for this day (+1 helps buys, -1 helps sells, 0 flat, 9 unknown).
    Returns list of events (dicts) in time order."""
    H1, D1, H4 = S['H1'], S['D1'], S['H4']
    prev = D1.index[D1.index < day]
    if len(prev) < max(P['datr_days'], 60): return []
    y = D1.loc[prev[-1]]
    datr = D1.rng.loc[prev[-P['datr_days']:]].mean()
    trend = int(np.sign(y.c - y.ema))
    d1g = int(y.G); d1j = int(y.J); d1state = d1j if (d1j != 0 and d1j == d1g) else 0
    rngy = y.h - y.l
    def yest_ok(d):
        if rngy <= 0: return False
        loc = (y.c - y.l) / rngy; return (loc if d == 1 else 1 - loc) > P['yesterday_cut']
    def day_allowed(d): return yest_ok(d) and (yd == d or (trend == d and sd == d))
    def grade(d, t_h1):
        i4 = H4.index.searchsorted(t_h1.floor('4h')) - 1          # last CLOSED H4 bar before this H1 bar
        r = H4.rsi.iloc[i4] if i4 >= 0 else np.nan
        rin = r if d == 1 else 100 - r
        pts = int(d1g == d) + int(P['grade_lo'] <= rin < P['grade_hi'])
        return 'A' if pts == 2 else ('B' if pts == 1 else 'C')
    bars = H1[(H1.index >= day) & (H1.index < day + pd.Timedelta(days=1))]
    ev = []; st = dict(first=0, fpx=None, ft=None, blocked=False, alt=0, grade='-', n=0)
    def fri_late(t): return t.dayofweek == 4 and t.hour * 100 + t.minute >= P['fri_close']
    def enter(d, t, px, kind):
        if st['grade'] != '-' and st['grade'] != 'A' and grade(d, t.floor('h')) != 'A': return False
        if st['grade'] == '-': st['grade'] = grade(d, t.floor('h'))
        st['n'] += 1
        ev.append(dict(t=t, type='ENTRY', dir=d, px=px, n=st['n'], grade=st['grade'], kind=kind,
                       stop=px - d * P['stop'] * datr, target=px + d * P['target'] * datr,
                       be_at=px + d * P['be_trig'] * datr, be_to=px + d * P['be_lock'] * datr, datr=datr))
        return True
    for k in range(1, len(bars)):
        t = bars.index[k]; sig = bars.iloc[k - 1]
        if t.hour >= P['close_hour'] or fri_late(t): break
        body = sig.c - sig.o; d = int(np.sign(body)); hs = bars.index[k - 1].hour
        if d == 0 or not datr > 0: continue
        big = abs(body) >= P['first_body'] * sig.atr
        if st['blocked'] and st['alt'] != 0:
            if hs in P['first_hours'] and d == st['alt'] and big:
                if enter(d, t, bars.iloc[k].o, 'alt'):
                    st.update(first=d, fpx=bars.iloc[k].o, ft=t, blocked=False, alt=0)
            continue
        if st['first'] != 0: continue          # later entries come from 5-min candles
        if not (hs in P['first_hours'] and big): continue
        if not (int(sig.J) == d and int(sig.G) == d): continue
        st.update(first=d, fpx=bars.iloc[k].o, ft=t)
        if not day_allowed(d):
            st['blocked'] = True
            if yest_ok(d) and d1state != 0 and d1state == sd: st['alt'] = d1state
            if st['alt'] != 0 and st['alt'] == d:
                if enter(d, t, bars.iloc[k].o, 'alt'): st.update(blocked=False, alt=0)
            continue
        enter(d, t, bars.iloc[k].o, 'first')
    # 5-minute later entries (need first entry of a non-blocked day)
    firsts = [e for e in ev if e['type'] == 'ENTRY']
    if firsts and m1 is not None and len(m1):
        f = firsts[0]; d = f['dir']; ft = f['t']; fpx = f['px']
        c5 = m1.groupby(m1.index.floor(f"{P['later_min']}min")).agg(o=('o', 'first'), h=('h', 'max'), l=('l', 'min'), c=('c', 'last'))
        for cs, row in c5.iterrows():
            if cs < ft or cs.hour > P['later_last_hour']: continue
            now = cs + pd.Timedelta(minutes=P['later_min'])
            if now.hour >= P['close_hour'] or fri_late(now) or now.normalize() != day: continue
            if int(np.sign(row.c - row.o)) != d: continue
            if (row.c - fpx) * d <= 0: continue
            if now in [e['t'] for e in ev]: continue
            enter(d, now, row.c, 'add')
    ev.sort(key=lambda e: (e['t'], e['n']))
    global LAST
    LAST = dict(first=st['first'], blocked=st['blocked'], alt=st['alt'], grade=st['grade'], datr=datr, trend=trend)
    return ev

def manage(ev, m1, day):
    """Walk the day's 1-min path for each entry: break-even move, stop, target, end-of-day close."""
    out = []
    if m1 is None or not len(m1): return out
    eod = day + pd.Timedelta(hours=P['close_hour'])
    if day.dayofweek == 4: eod = day + pd.Timedelta(hours=22, minutes=50)
    for e in [x for x in ev if x['type'] == 'ENTRY']:
        d = e['dir']; path = m1[(m1.index >= e['t']) & (m1.index < eod)]
        stop = e['stop']; be = False
        for t, r in path.iterrows():
            fav = r.h if d == 1 else r.l; adv = r.l if d == 1 else r.h
            if (adv - stop) * d <= 0:
                out.append(dict(t=t, type='STOPPED' if not be else 'BE_EXIT', n=e['n'], dir=d, px=stop)); break
            if (fav - e['target']) * d >= 0:
                out.append(dict(t=t, type='TARGET', n=e['n'], dir=d, px=e['target'])); break
            if not be and (fav - e['be_at']) * d >= 0:
                be = True; stop = e['be_to']; out.append(dict(t=t, type='BREAKEVEN', n=e['n'], dir=d, px=e['be_to'], entry=e['px']))
    return out
