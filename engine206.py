"""GOLD_DAYTRADE v2.06 signal engine - Python port of the MT4 EA in signal-set mode (settings = DT206_GOLD_AUTO.set).

Driven exactly like the EA: today's 1-minute bars are turned into ticks (open, low, high, close for an up bar;
open, high, low, close for a down bar) and every tick runs the EA's SignalSet() logic.
Inputs: daily bars before today (broker days, New York + 7h), hourly bars (incl. today's), today's minute bars,
and the day's outside values (dollar 1-day / 5-day, VIX 5-day, US 10y 5-day, dollar-driven, low attention).
It never trades. It returns the trades the EA would take, with stop, size weight and (if the day has ended) the result.
"""
import math
import numpy as np

S = dict(Signal_Stop_Target=0.5, Stop_Other=0.75, Signal_Last_Hour=19, Close_Hour=23, Friday_Close_HHMM=2250,
         DailyATR_Days=14, U2_Step=50.0, U2_From=9, U8_From=12,
         N1_Min_Gap=0.05, N1_From=9, N2_Near=0.15, N2_Hour=6, N3_From=0, N4_From=9, N5_From=9,
         N6_End=8, N6_Min_Range=0.6, N11_Calm=0.8, N11_Days=2, N11_From=9, N12_Pct=0.2, N12_Days=3, N12_From=10,
         N13_ADX=15, N13_Days=2, N13_From=9, N15_Hour=6, N15_Pct=0.2, N15_Range_Hours=4, N15_Window_Hours=6,
         A15_ADX=15, A15_Days=2, A15_From=12, T15_KC=1.5, T15_Days=5, T15_From=9, N16_Min=3, N16_Days=5, N16b_Days=3,
         N16_From=12, S24_Hour=3, S24_Max=0.6, S24_Hours=24, G3_Box=1.0156,
         Size_First=0.5, Size_Confirmed=2.5, Size_N4=0.5, Size_N5=0.5, Size_U8=0.5, Dollar_Agree=0.67,
         Quiet_3_Up=1.5, Quiet_0_2=0.67, Quiet_0_Extra=0.67, Size_Min=0.5, Size_Max=2.0, Spread=0.5)
G_DAYS = [0, 2, 2, 0, 2, 2, 2, 3, 5, 5, 3, 3, 0, 2, 0, 2, 3, 2, 3]
G_FROM = [0, 12, 6, 3, 9, 6, 12, 10, 0, 10, 12, 12, 0, 12, 12, 10, 10, 12, 12]
G_TYPE = [0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 2, 0, 4, 0, 0, 0, 3]
G_RULE = [0, 1, 0, 0, 2, 0, 0, 0, 3, 0, 4, 5, 0, 0, 0, 0, 0, 0, 2]
G_GATE = [-9] * 13 + [2, 2, 2, 2, 1, 1]
G_TAG = ["", "G1 q3vs60", "G2 calm3ys", "G3 box20", "G4 q3vsusd", "G5 rng5q3", "G6 calmbuf", "G7 ttmins", "G8 ttmvsc",
         "G9 bb30ys", "G10 q3vstnx", "G11 q3vix", "G12 q3r3s3", "G13 adx18usd", "G14 sq2husd", "G15 bbnr4usd",
         "G16 ttmnr7usd", "G17 adxysusd", "G18 adx5musd"]
OTHER = ("U2 ", "U8 ", "N1 ", "N2 ", "N3 ", "N4 ", "N5 ", "N6 ")


class Daily:
    """Daily bars BEFORE today; shift 1 = yesterday (like iHigh(Symbol(),PERIOD_D1,1))."""
    def __init__(self, t, o, h, l, c):
        self.t = np.asarray(t, dtype='datetime64[D]'); self.o, self.h, self.l, self.c = (np.asarray(x, float) for x in (o, h, l, c)); self.n = len(self.c)
    def _g(self, a, k): return float(a[self.n - k]) if 1 <= k <= self.n else 0.0
    def H(self, k): return self._g(self.h, k)
    def L(self, k): return self._g(self.l, k)
    def C(self, k): return self._g(self.c, k)
    def O(self, k): return self._g(self.o, k)
    def T(self, k): return self.t[self.n - k] if 1 <= k <= self.n else None
    def rng(self, k): return self.H(k) - self.L(k)
    def hi(self, a, b):
        m = 0.0
        for k in range(a, b + 1):
            x = self.H(k)
            if x <= 0: return 0.0
            m = max(m, x)
        return m
    def lo(self, a, b):
        m = 0.0
        for k in range(a, b + 1):
            x = self.L(k)
            if x <= 0: return 0.0
            m = x if m == 0 else min(m, x)
        return m
    def atr(self, k=0):   # DailyATR (k=0) / ATRAt(k): average high-low of bars k+1..k+14
        s = 0.0
        for j in range(k + 1, k + S['DailyATR_Days'] + 1):
            if self.H(j) <= 0: return 0.0
            s += self.rng(j)
        return s / S['DailyATR_Days']
    def rngavg(self, a, b):
        s = 0.0
        for k in range(a, b + 1):
            r = self.rng(k)
            if r <= 0: return -1.0
            s += r
        return s / (b - a + 1)
    def bbw(self, s):
        cs = [self.C(k) for k in range(s, s + 20)]
        if min(cs) <= 0: return -1.0
        mu = sum(cs) / 20.0; sd = math.sqrt(sum((c - mu) ** 2 for c in cs) / 19.0)
        return sd / mu
    def bbrank(self):
        b1 = self.bbw(1)
        if b1 <= 0: return 9.0
        c = n = 0
        for k in range(1, 121):
            bk = self.bbw(k)
            if bk < 0: break
            n += 1; c += (b1 >= bk)
        return 9.0 if n < 60 else c / n
    def rng5rank(self):
        v1 = self.rngavg(1, 5)
        if v1 < 0: return 9.0
        c = n = 0
        for s in range(1, 121):
            v = self.rngavg(s, s + 4)
            if v < 0: break
            n += 1; c += (v1 >= v)
        return 9.0 if n < 60 else c / n
    def ttm(self, kc):
        cs = [self.C(k) for k in range(1, 21)]
        if min(cs) <= 0: return False
        mu = sum(cs) / 20.0; sq = tr = 0.0
        for k in range(1, 21):
            c, hi, lo, cp = self.C(k), self.H(k), self.L(k), self.C(k + 1)
            if cp <= 0: return False
            sq += (c - mu) ** 2; tr += max(hi - lo, abs(hi - cp), abs(lo - cp))
        return 2.0 * math.sqrt(sq / 19.0) < kc * tr / 20.0
    def adx(self):   # ADXD1(): Wilder 1/14 over shifts 300..1
        a = pp = mm = ax = 0.0; init = False
        for sft in range(300, 0, -1):
            hi, lo, hp, lp, cp = self.H(sft), self.L(sft), self.H(sft + 1), self.L(sft + 1), self.C(sft + 1)
            if hi <= 0 or hp <= 0 or cp <= 0: continue
            up, dn = hi - hp, lp - lo
            pdm = up if (up > dn and up > 0) else 0.0; ndm = dn if (dn > up and dn > 0) else 0.0
            tr = max(hi - lo, abs(hi - cp), abs(lo - cp))
            if not init: a, pp, mm = tr, pdm, ndm
            else: a += (tr - a) / 14.0; pp += (pdm - pp) / 14.0; mm += (ndm - mm) / 14.0
            if a <= 0: continue
            pdi, ndi = 100 * pp / a, 100 * mm / a
            dx = 100 * abs(pdi - ndi) / (pdi + ndi) if pdi + ndi > 0 else 0.0
            if not init: ax = dx; init = True
            else: ax += (dx - ax) / 14.0
        return ax if init else 99.0
    def prev_week(self, today):   # last calendar week's high / low / close (weeks start Sunday, like the EA)
        today = np.datetime64(today, 'D'); dow = (int(today.astype('int64')) + 4) % 7   # MQL TimeDayOfWeek: Sunday = 0
        ws = today - np.timedelta64(dow, 'D'); pws = ws - np.timedelta64(7, 'D')
        wh = wl = wc = 0.0
        for k in range(1, 13):
            tk = self.T(k)
            if tk is None: break
            if tk >= ws: continue
            if tk < pws: break
            if wc == 0: wc = self.C(k)
            hh, ll = self.H(k), self.L(k)
            if wh == 0 or hh > wh: wh = hh
            if wl == 0 or ll < wl: wl = ll
        return wh, wl, wc


class Hourly:
    """Hourly bars (start times, incl. today's). shift s at time t = s bars before the bar that holds t."""
    def __init__(self, t, h, l, c):
        self.t = np.asarray(t, dtype='datetime64[m]'); self.h, self.l, self.c = (np.asarray(x, float) for x in (h, l, c))
    def at(self, t):   # index of the bar holding time t
        return int(np.searchsorted(self.t, np.datetime64(t, 'm'), side='right')) - 1
    def _g(self, a, i0, s):
        i = i0 - s
        return float(a[i]) if 0 <= i < len(a) else 0.0
    def H(self, i0, s): return self._g(self.h, i0, s)
    def L(self, i0, s): return self._g(self.l, i0, s)
    def C(self, i0, s): return self._g(self.c, i0, s)
    def bw(self, i0, s):
        cs = [self.C(i0, k) for k in range(s, s + 20)]
        if min(cs) <= 0: return -1.0
        mu = sum(cs) / 20.0; return math.sqrt(sum((c - mu) ** 2 for c in cs) / 19.0) / mu
    def squeeze_pct(self, i0):
        b1 = self.bw(i0, 1)
        if b1 < 0: return 9.0
        c = n = 0
        for k in range(1, 201):
            bk = self.bw(i0, k)
            if bk < 0: break
            n += 1; c += (b1 >= bk)
        return 9.0 if n < 100 else c / n


def raw(x):   # list value (B=+1 = dollar fell) -> raw dollar move sign
    return -1 if x == 1 else (1 if x == -1 else 0)


def run_day(day, D, Hh, m1, inp):
    """day: numpy datetime64[D] broker date. D: Daily (bars before today). Hh: Hourly. m1: dict t,o,h,l,c (today, broker time).
    inp: d5, d1, vix, tnx (list values: +1 = B, -1 = S, 0, 9 unknown), regime(t) -> 1/0, attn 1/0.
    Returns list of trades: dict(t, dir, tag, px, sd, stop, w, first)."""
    T = np.asarray(m1['t'], dtype='datetime64[m]')
    if len(T) == 0: return []
    O, Hi, Lo, Cl = (np.asarray(m1[k], float) for k in ('o', 'h', 'l', 'c'))
    st = dict(net=0); trades = []
    atr = D.atr(0)
    if atr <= 0: return []
    friday = int(day.astype('datetime64[D]').astype('int64')) % 7 == 1   # 1970-01-01 was a Thursday, so day % 7 == 1 is a Friday
    # ---- day setup at the first tick
    p0 = O[0]; h0 = int((T[0] - day.astype('datetime64[m]')).astype(int) // 60)
    yH, yL, pc = D.H(1), D.L(1), D.C(1)
    n3ok = yH > 0 and yH <= D.H(2) and yL >= D.L(2)
    r1 = D.rng(1); n4ok = r1 > 0 and all(D.rng(k) > 0 and D.rng(k) >= r1 for k in range(2, 8))
    a5, a20 = D.rngavg(1, 5), D.rngavg(1, 20)
    n11ok = a5 > 0 and a20 > 0 and a5 / a20 < S['N11_Calm']
    n11H, n11L = D.hi(1, S['N11_Days']), D.lo(1, S['N11_Days']); n11ok = n11ok and n11H > 0 and n11L > 0
    bbr = D.bbrank()
    n12ok = bbr <= S['N12_Pct']; n12H, n12L = D.hi(1, S['N12_Days']), D.lo(1, S['N12_Days']); n12ok = n12ok and n12H > 0 and n12L > 0
    adxY = D.adx()
    n13ok = adxY < S['N13_ADX']; n13H, n13L = D.hi(1, S['N13_Days']), D.lo(1, S['N13_Days']); n13ok = n13ok and n13H > 0 and n13L > 0
    a15ok = adxY < S['A15_ADX']; a15H, a15L = D.hi(1, S['A15_Days']), D.lo(1, S['A15_Days']); a15ok = a15ok and a15H > 0 and a15L > 0
    t15ok = D.ttm(S['T15_KC']); t15H, t15L = D.hi(1, S['T15_Days']), D.lo(1, S['T15_Days']); t15ok = t15ok and t15H > 0 and t15L > 0
    q = 0                                                   # QuietScore
    if adxY < 18: q += 1
    if a5 > 0 and a20 > 0 and a5 / a20 < 0.8: q += 1
    if bbr <= 0.2: q += 1
    if D.ttm(1.5): q += 1
    q += int(n4ok) + int(n3ok)
    n16ok = q >= S['N16_Min']; n16H, n16L = D.hi(1, S['N16_Days']), D.lo(1, S['N16_Days']); n16bH, n16bL = D.hi(1, S['N16b_Days']), D.lo(1, S['N16b_Days'])
    if n16H <= 0 or n16L <= 0 or n16bH <= 0 or n16bL <= 0: n16ok = False
    # G day setup
    a3 = D.rngavg(1, 3); calm = a5 > 0 and a20 > 0 and a5 / a20 < 0.8; c37 = a3 > 0 and a20 > 0 and a3 / a20 < 0.7
    ya = D.atr(1); ysmall = ya > 0 and D.rng(1) / ya < 0.7
    ttm2 = D.ttm(2.0); box3 = D.hi(1, 3) - D.lo(1, 3); adx18 = adxY < 18
    nr4 = r1 > 0 and all(D.rng(k) > 0 and D.rng(k) >= r1 for k in range(2, 5))
    gok = [False, q >= 3, c37 and ysmall, 0 < box3 <= S['G3_Box'] * atr, q >= 3, q >= 3 and D.rng5rank() <= 0.2, calm and q >= 2,
           ttm2 and n3ok, ttm2, ysmall and bbr <= 0.3, q >= 3, q >= 3, q >= 3, adx18, True, nr4 and bbr <= 0.2, ttm2 and n4ok, adx18 and ysmall, adx18]
    gH = [0.0] * 19; gL = [0.0] * 19; gDone = [False] * 19; gSet = [False] * 19; gBrk = [0] * 19; gQ = [0] * 19; gBrkT = [None] * 19
    for g in range(1, 19):
        if not gok[g]: gDone[g] = True; continue
        if G_TYPE[g] in (0, 3):
            buf = 0.1 if g in (6, 17) else 0.0
            gH[g] = D.hi(1, G_DAYS[g]) + buf * atr; gL[g] = D.lo(1, G_DAYS[g]) - buf * atr
            if D.hi(1, G_DAYS[g]) <= 0 or D.lo(1, G_DAYS[g]) <= 0: gDone[g] = True
        if G_TYPE[g] == 2:
            P = (yH + yL + pc) / 3.0; gH[g] = yH + 2 * (P - yL); gL[g] = yL - 2 * (yH - P)
    c1, c60 = D.C(1), D.C(60); yo = D.O(1)
    def gdir_ok(rule, d):
        if rule == 0: return True
        if rule == 1:
            if c1 <= 0 or c60 <= 0: return False
            t = 1 if c1 > c60 else (-1 if c1 < c60 else 0); return t == -d
        if rule == 2: x = inp['d5']; return x in (1, -1) and x == -d
        if rule == 3: t = 1 if pc > yo else (-1 if pc < yo else 0); return t == -d
        if rule == 4: x = inp['tnx']; return x in (1, -1) and x == -d
        if rule == 5: x = inp['vix']; return x in (1, -1) and x == d
        return False
    def dscore(d): return (raw(inp['d5']) + raw(inp['d1'])) * d

    def sig_open(d, tag, t, px):
        sm = S['Stop_Other'] if tag[:3] in OTHER else S['Signal_Stop_Target']; sd = sm * atr
        block = st['net'] == 0 and dscore(d) <= -2
        if block and inp['regime'](t) != 1: block = False
        if block and inp['attn'] == 1: block = False
        if block: trades.append(dict(t=t, dir=d, tag=tag, px=px, skipped='dollar filter')); return
        if st['net'] == 0: w = S['Size_First']
        elif (st['net'] > 0 and d == 1) or (st['net'] < 0 and d == -1): w = S['Size_Confirmed']
        else: return                                     # against today's earlier trades: skipped
        if tag[:3] == 'N4 ': w *= S['Size_N4']
        if tag[:3] == 'N5 ': w *= S['Size_N5']
        if tag[:3] == 'U8 ': w *= S['Size_U8']
        x = inp['d5']
        if x in (1, -1) and x == d: w *= S['Dollar_Agree']
        w *= S['Quiet_3_Up'] if q >= 3 else S['Quiet_0_2']
        if q == 0: w *= S['Quiet_0_Extra']
        w = max(S['Size_Min'], min(S['Size_Max'], w))
        stop = px - sd if d == 1 else px + S['Spread'] + sd
        trades.append(dict(t=t, dir=d, tag=tag, px=px, sd=sd, stop=stop, w=round(w, 2), first=st['net'] == 0))
        st['net'] += d

    # ---- state
    done = {k: False for k in ('u2', 'u8', 'n1', 'n2', 'n3', 'n4', 'n5', 'n6', 'n11', 'n12', 'n13', 'n15', 'a15', 't15', 'n16', 'n16b', 's24')}
    sets = {k: False for k in ('u2', 'u8', 'n5', 'n6', 'n15', 's24')}
    u2Up = u2Dn = u2Last = 0.0; u2Touch = 0; u2Min = None; u8R2 = u8S2 = 0.0; n1Armed = False; n5R1 = n5S1 = 0.0
    n6Hi = n6Lo = p0; n15H = n15L = 0.0; n15End = None; s24H = s24L = 0.0
    if h0 >= S['N6_End']: done['n6'] = True
    sOpen = p0
    for i in range(len(T)):
        t = T[i]; mins = int((t - day.astype('datetime64[m]')).astype(int)); h = mins // 60; hm = h * 100 + mins % 60
        path = (O[i], Lo[i], Hi[i], Cl[i]) if Cl[i] >= O[i] else (O[i], Hi[i], Lo[i], Cl[i])
        for ti, p in enumerate(path):
            def fill(level, p=p, ti=ti): return p if ti == 0 else level   # a break inside the bar fills at the level
            if h >= S['Close_Hour'] or (friday and hm >= S['Friday_Close_HHMM']): break
            last = h < S['Signal_Last_Hour']
            # U2 round $50: first touch, entered only if that minute closes beyond it
            if not done['u2'] and h >= S['U2_From'] and last:
                if not sets['u2']:
                    u2Up = math.ceil(p / S['U2_Step']) * S['U2_Step']; u2Dn = math.floor(p / S['U2_Step']) * S['U2_Step']
                    if u2Up <= p: u2Up += S['U2_Step']
                    if u2Dn >= p: u2Dn -= S['U2_Step']
                    sets['u2'] = True
                if u2Touch == 0:
                    if p >= u2Up: u2Touch, u2Min = 1, t
                    elif p <= u2Dn: u2Touch, u2Min = -1, t
                    u2Last = p
                elif t == u2Min: u2Last = p
                else:
                    if (u2Touch == 1 and u2Last > u2Up) or (u2Touch == -1 and u2Last < u2Dn): sig_open(u2Touch, 'U2 round', t, p)
                    done['u2'] = True
            if h < S['N6_End']: n6Hi = max(n6Hi, p); n6Lo = min(n6Lo, p)
            # N1 gap filled -> keep going
            if not done['n1'] and h >= S['N1_From'] and last and pc > 0:
                g = sOpen - pc
                if not n1Armed:
                    if abs(g) < S['N1_Min_Gap'] * atr or (g > 0 and p <= pc) or (g < 0 and p >= pc): done['n1'] = True
                    else: n1Armed = True
                elif (g > 0 and p <= pc) or (g < 0 and p >= pc): sig_open(-1 if g > 0 else 1, 'N1 gapfill', t, fill(pc)); done['n1'] = True
            # N2 near a $100 level at 6:00 broker
            if not done['n2'] and h >= S['N2_Hour']:
                done['n2'] = True
                if h == S['N2_Hour']:
                    up, dn = math.ceil(p / 100.0) * 100.0, math.floor(p / 100.0) * 100.0; du, dd = up - p, p - dn
                    if min(du, dd) <= S['N2_Near'] * atr and du != dd and du > 0 and dd > 0: sig_open(1 if du < dd else -1, 'N2 near100', t, p)
            # N3 inside day / N4 NR7: first break of yesterday's high / low
            if not done['n3'] and n3ok and h >= S['N3_From'] and last:
                if p >= yH: sig_open(1, 'N3 inside', t, fill(yH)); done['n3'] = True
                elif p <= yL: sig_open(-1, 'N3 inside', t, fill(yL)); done['n3'] = True
            if not done['n4'] and n4ok and h >= S['N4_From'] and last:
                if p >= yH: sig_open(1, 'N4 nr7', t, fill(yH)); done['n4'] = True
                elif p <= yL: sig_open(-1, 'N4 nr7', t, fill(yL)); done['n4'] = True
            # N5 weekly pivot R1 / S1
            if not done['n5'] and h >= S['N5_From'] and last:
                if not sets['n5']:
                    wh, wl, wc = D.prev_week(day); sets['n5'] = True
                    if wh <= 0 or wl <= 0 or wc <= 0: done['n5'] = True
                    else:
                        P = (wh + wl + wc) / 3.0; n5R1 = P + 0.5 * (wh - wl); n5S1 = P - 0.5 * (wh - wl)
                        if not (n5S1 < p < n5R1): done['n5'] = True
                elif p >= n5R1: sig_open(1, 'N5 weekR1', t, fill(n5R1)); done['n5'] = True
                elif p <= n5S1: sig_open(-1, 'N5 weekS1', t, fill(n5S1)); done['n5'] = True
            # N6 big morning range
            if not done['n6'] and h >= S['N6_End'] and last:
                if not sets['n6']:
                    sets['n6'] = True
                    if n6Hi - n6Lo < S['N6_Min_Range'] * atr: done['n6'] = True
                elif p >= n6Hi: sig_open(1, 'N6 bigrange', t, fill(n6Hi)); done['n6'] = True
                elif p <= n6Lo: sig_open(-1, 'N6 bigrange', t, fill(n6Lo)); done['n6'] = True
            # N11 calm / N12 squeeze / N13 low ADX
            for key, ok, hh_, ll_, fr, tag in (('n11', n11ok, n11H, n11L, S['N11_From'], 'N11 calm'), ('n12', n12ok, n12H, n12L, S['N12_From'], 'N12 squeeze'),
                                               ('n13', n13ok, n13H, n13L, S['N13_From'], 'N13 adx')):
                if not done[key] and ok and h >= fr and last:
                    if p >= hh_: sig_open(1, tag, t, fill(hh_)); done[key] = True
                    elif p <= ll_: sig_open(-1, tag, t, fill(ll_)); done[key] = True
            # N15 hourly squeeze (set at the first tick of 6:00, window 6 hours)
            if not done['n15'] and h >= S['N15_Hour']:
                if not sets['n15']:
                    sets['n15'] = True; n15End = t + np.timedelta64(S['N15_Window_Hours'] * 60, 'm')
                    if h != S['N15_Hour']: done['n15'] = True
                    else:
                        i0 = Hh.at(t); ok = Hh.squeeze_pct(i0) <= S['N15_Pct']; n15H = n15L = 0.0
                        for k in range(1, S['N15_Range_Hours'] + 1):
                            hh_, ll_ = Hh.H(i0, k), Hh.L(i0, k)
                            if hh_ <= 0: ok = False; break
                            if n15H == 0 or hh_ > n15H: n15H = hh_
                            if n15L == 0 or ll_ < n15L: n15L = ll_
                        if not ok: done['n15'] = True
                if not done['n15']:
                    if t >= n15End or h >= S['Signal_Last_Hour']: done['n15'] = True
                    elif p >= n15H: sig_open(1, 'N15 hsq', t, fill(n15H)); done['n15'] = True
                    elif p <= n15L: sig_open(-1, 'N15 hsq', t, fill(n15L)); done['n15'] = True
            # G signals
            for g in range(1, 19):
                if gDone[g] or h < G_FROM[g]: continue
                if h >= S['Signal_Last_Hour']: gDone[g] = True; continue
                if not gSet[g]:
                    gSet[g] = True
                    if G_TYPE[g] == 1:
                        if h != G_FROM[g]: gDone[g] = True; continue
                        gH[g] = math.ceil(p / 20.0) * 20.0; gL[g] = math.floor(p / 20.0) * 20.0
                        if gH[g] == p or gL[g] == p: gDone[g] = True; continue
                    if G_TYPE[g] == 2:
                        if h > G_FROM[g] + 1 or not (gL[g] < p < gH[g]): gDone[g] = True; continue
                    if G_TYPE[g] == 4:
                        if h != G_FROM[g]: gDone[g] = True; continue
                        i0 = Hh.at(t); up = max(Hh.H(i0, 1), Hh.H(i0, 2)); dn = min(Hh.L(i0, 1), Hh.L(i0, 2))
                        if up <= 0 or dn <= 0 or up - dn > 0.15 * atr: gDone[g] = True; continue
                        gH[g], gL[g] = up, dn
                if G_TYPE[g] == 4 and h >= G_FROM[g] + 4: gDone[g] = True; continue
                if G_TYPE[g] == 3:
                    if gBrk[g] == 0:
                        if p >= gH[g]: gBrk[g] = 1
                        elif p <= gL[g]: gBrk[g] = -1
                        if gBrk[g] != 0: gBrkT[g] = t; gQ[g] = 1
                        continue
                    lv = gH[g] if gBrk[g] == 1 else gL[g]
                    if (gBrk[g] == 1 and p < lv - 0.3 * atr) or (gBrk[g] == -1 and p > lv + 0.3 * atr) or gQ[g] > 24: gDone[g] = True; continue
                    chk = gBrkT[g] + np.timedelta64(gQ[g] * 5, 'm')
                    if t < chk: continue
                    j = int(np.searchsorted(T, chk - np.timedelta64(1, 'm'), side='right')) - 1   # close of the 1-min bar ending at chk
                    cl = Cl[j] if j >= 0 else 0.0; gQ[g] += 1
                    if cl <= 0 or (cl - lv) * gBrk[g] <= 0: continue
                    d = gBrk[g]; gDone[g] = True
                    if not gdir_ok(G_RULE[g], d): continue
                    if G_GATE[g] > -9 and dscore(d) < G_GATE[g]: continue
                    sig_open(d, G_TAG[g], t, p); continue
                d = 1 if p >= gH[g] else (-1 if p <= gL[g] else 0)
                if d == 0: continue
                gDone[g] = True
                if not gdir_ok(G_RULE[g], d): continue
                if G_GATE[g] > -9 and dscore(d) < G_GATE[g]: continue
                sig_open(d, G_TAG[g], t, fill(gH[g] if d == 1 else gL[g]))
            # S24 24-hour squeeze (set at the first tick of 3:00)
            if not done['s24'] and h >= S['S24_Hour']:
                if not sets['s24']:
                    sets['s24'] = True
                    if h != S['S24_Hour']: done['s24'] = True
                    else:
                        i0 = Hh.at(t); s24H = s24L = 0.0; ok = True
                        for k in range(1, S['S24_Hours'] + 1):
                            hh_, ll_ = Hh.H(i0, k), Hh.L(i0, k)
                            if hh_ <= 0: ok = False; break
                            if s24H == 0 or hh_ > s24H: s24H = hh_
                            if s24L == 0 or ll_ < s24L: s24L = ll_
                        if not ok or s24H - s24L >= S['S24_Max'] * atr: done['s24'] = True
                if not done['s24']:
                    if h >= S['Signal_Last_Hour']: done['s24'] = True
                    elif p >= s24H: sig_open(1, 'S24 sq24', t, fill(s24H)); done['s24'] = True
                    elif p <= s24L: sig_open(-1, 'S24 sq24', t, fill(s24L)); done['s24'] = True
            # A15 / T15 / N16 / N16b
            for key, ok, hh_, ll_, fr, tag in (('a15', a15ok, a15H, a15L, S['A15_From'], 'A15 adx1pm'), ('t15', t15ok, t15H, t15L, S['T15_From'], 'T15 ttm'),
                                               ('n16', n16ok, n16H, n16L, S['N16_From'], 'N16 deep5'), ('n16b', n16ok, n16bH, n16bL, S['N16_From'], 'N16b deep3')):
                if not done[key] and ok and h >= fr and last:
                    if p >= hh_: sig_open(1, tag, t, fill(hh_)); done[key] = True
                    elif p <= ll_: sig_open(-1, tag, t, fill(ll_)); done[key] = True
            # U8 pivot R2 / S2
            if not done['u8'] and h >= S['U8_From'] and last:
                if not sets['u8']:
                    P = (yH + yL + pc) / 3.0; u8R2 = P + (yH - yL); u8S2 = P - (yH - yL); sets['u8'] = True
                    if not (u8S2 < p < u8R2): done['u8'] = True
                elif p >= u8R2: sig_open(1, 'U8 pivot', t, fill(u8R2)); done['u8'] = True
                elif p <= u8S2: sig_open(-1, 'U8 pivot', t, fill(u8S2)); done['u8'] = True
    for tr in trades: tr['atr'] = atr; tr['q'] = q
    return trades


def manage(trades, day, m1, now=None):
    """Stop hit or end-of-day close for each taken trade from today's minute bars. Prices are Bid; buys pay the spread
    at entry, sells at exit. Adds: status, exit (fill), exit_t, pnl_oz, rwf (1 = moved 0.3 daily range our way first)."""
    T = np.asarray(m1['t'], dtype='datetime64[m]'); Hi = np.asarray(m1['h'], float); Lo = np.asarray(m1['l'], float); Cl = np.asarray(m1['c'], float)
    Op = np.asarray(m1['o'], float)
    friday = int(day.astype('datetime64[D]').astype('int64')) % 7 == 1
    eod = day.astype('datetime64[m]') + np.timedelta64(22 * 60 + 50 if friday else 23 * 60, 'm')
    sp = S['Spread']
    for tr in trades:
        if tr.get('skipped'): continue
        d = tr['dir']; tr.update(status='open', exit=None, exit_t=None, pnl_oz=None, rwf=None)
        a = 0.3 * tr['atr']; j0 = int(np.searchsorted(T, tr['t'], side='right'))
        je = j0 - 1          # STOP INSIDE THE ENTRY MINUTE (added 2026-10-10): the part of the entry bar after the fill, on the same
        if 0 <= je < len(T) and T[je] == np.datetime64(tr['t'], 'm'):   # tick path as the fills (up bar O-L-H-C, down bar O-H-L-C)
            at_open = abs(tr['px'] - Op[je]) < 1e-9; up_bar = Cl[je] >= Op[je]
            if d == 1: worst = Lo[je] if (at_open or not up_bar) else Cl[je]; hit = worst <= tr['stop']
            else: worst = Hi[je] if (at_open or up_bar) else Cl[je]; hit = worst + sp >= tr['stop']
            if hit: tr.update(status='stop hit', exit=tr['stop'], exit_t=T[je])
        for j in (range(j0, len(T)) if tr['exit'] is None else ()):
            if T[j] >= eod:
                bid = Cl[j - 1] if j - 1 >= j0 else Cl[j]
                tr.update(status='closed at day end', exit=bid if d == 1 else bid + sp, exit_t=T[j]); break
            if (d == 1 and Lo[j] <= tr['stop']) or (d == -1 and Hi[j] + sp >= tr['stop']):
                tr.update(status='stop hit', exit=tr['stop'], exit_t=T[j]); break
        if tr['exit'] is None and now is not None and np.datetime64(now, 'm') >= eod and len(T) > j0:   # day over, no bar after the close time
            bid = Cl[-1]; tr.update(status='closed at day end', exit=bid if d == 1 else bid + sp, exit_t=T[-1])
        for j in range(j0, len(T)):   # direction yardstick (same as the research): 0.3 daily range our way before 0.3 against, same bar = undecided
            up = (Hi[j] - tr['px']) if d == 1 else (tr['px'] - Lo[j]); dn = (tr['px'] - Lo[j]) if d == 1 else (Hi[j] - tr['px'])
            if dn >= a and up >= a: break
            if up >= a: tr['rwf'] = 1; break
            if dn >= a: tr['rwf'] = 0; break
        if tr['exit'] is not None:
            tr['pnl_oz'] = round(tr['exit'] - (tr['px'] + sp), 2) if d == 1 else round(tr['px'] - tr['exit'], 2)
    return trades
