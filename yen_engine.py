"""USDJPY_DAYTRADE v1.01 rules (the MT4 EA, 11 signals) as a PAPER engine for the portal - same logic as the EA, line by line.
Prices are Bid. Broker clock = New York + 7h. Window = 01:05-23:57 broker, Monday-Friday (FX rollover minutes left out).
History = the EA's own daily and hourly bars: finished broker days / hours built from the window's minute bars.
Times are integer seconds on the broker clock (naive)."""
import numpy as np

NS = 11
TAG = ['J13', 'L3', 'M8', 'N3', 'M1a', 'J21', 'M1b', 'L1', 'U5', 'L7', 'Q5']
NAME = ['Heikin-Ashi 7am', 'Week-so-far break', 'Inside-week break', 'Inside-day break', 'Quiet 5-day break', 'Squeeze 4pm',
        'Quiet 2-day break', 'EMA10 break', 'Last-week break', 'Morning pullback', 'Hourly squeeze 3pm']
PT = 0.001; STOP_X = 0.25; MIN_SPREAD = 0.01          # 1 pip = the MT4 test spread; the paper P/L never uses less
KEEP_DAYS, KEEP_HOURS = 300, 600                      # history kept in the cache (enough for the 120-day rank, EMA30, 200-hour rank)

def dow(t): return int(((t // 86400) + 4) % 7)        # 0 = Sunday
def hour(t): return int((t % 86400) // 3600)
def minute(t): return int((t % 3600) // 60)
def dateof(t): return t - t % 86400
def weekof(d): return d - ((dow(d) + 6) % 7) * 86400
def inwin(t):
    d = dow(t)
    if d < 1 or d > 5: return False
    mm = hour(t) * 60 + minute(t); return 65 <= mm <= 1437
CLOSE_HHMM, FRI_CLOSE_HHMM = 1800, 1800              # v1.01 inputs Close_Hour=18, Friday_Close_HHMM=1800 (6 pm broker = London 4 pm fix; MT4 run 2026-10-04 passed)
def isclose(t):
    hm = hour(t) * 100 + minute(t)
    return hm >= FRI_CLOSE_HHMM if dow(t) == 5 else hm >= CLOSE_HHMM

def history(t, o, h, l, c):
    """EA daily and hourly bars from raw minute bars: [(date_s, o, h, l, c)], [(hour_s, o, h, l, c)] (window bars only)."""
    t = np.asarray(t, np.int64); m = np.array([inwin(x) for x in t], bool)
    t, o, h, l, c = t[m], np.asarray(o, float)[m], np.asarray(h, float)[m], np.asarray(l, float)[m], np.asarray(c, float)[m]
    out = []
    for key in (t - t % 86400, t - t % 3600):
        if not len(t): out.append([]); continue
        cut = np.r_[0, np.flatnonzero(np.diff(key)) + 1, len(t)]
        out.append([(int(key[a]), float(o[a]), float(h[a:b].max()), float(l[a:b].min()), float(c[b - 1])) for a, b in zip(cut[:-1], cut[1:])])
    return out[0], out[1]

class Yen:
    def __init__(self, days, hours):
        """days / hours: finished EA daily / hourly bars before the day to run, oldest first."""
        self.dDate, self.dWeek, self.dH, self.dL, self.dC, self.dR5, self.dRank, self.dE10, self.dE30 = ([] for _ in range(9))
        self.wKey, self.wH, self.wL = [], [], []
        self.hClose = [0.] * 20; self.bbw = [0.] * 200; self.bbwOK = [False] * 200
        self.nH = 0; self.haOprev = self.haCprev = 0.; self.haCol = 0; self.lastRank = -1.
        for d in days: self._finish_day(*d)
        for x in hours: self._finish_hour(*x[1:])
    # ---- EA FinishDay / FinishHour
    def _finish_day(self, dt, o, h, l, c):
        n = len(self.dDate); dH, dL, dR5 = self.dH, self.dL, self.dR5
        self.dDate.append(dt); self.dWeek.append(weekof(dt)); dH.append(h); dL.append(l); self.dC.append(c); dR5.append(-1.); self.dRank.append(-1.)
        if n >= 4: dR5[n] = sum(dH[n - q] - dL[n - q] for q in range(5)) / 5.0
        ln = min(120, n + 1); ok = le = 0
        for q in range(ln):
            p = n - q
            if dR5[p] >= 0:
                ok += 1
                if dR5[n] >= 0 and dR5[p] <= dR5[n]: le += 1
        if ok >= 60 and dR5[n] >= 0: self.dRank[n] = le / ln
        a10, a30 = 2 / 11, 2 / 31
        if n == 0: self.dE10.append(c); self.dE30.append(c)
        else: self.dE10.append(a10 * c + (1 - a10) * self.dE10[n - 1]); self.dE30.append(a30 * c + (1 - a30) * self.dE30[n - 1])
        if not self.wKey or self.wKey[-1] != self.dWeek[n]: self.wKey.append(self.dWeek[n]); self.wH.append(h); self.wL.append(l)
        else: self.wH[-1] = max(self.wH[-1], h); self.wL[-1] = min(self.wL[-1], l)
    def _finish_hour(self, hO, hH, hL, hC):
        nH = self.nH
        haC = (hO + hH + hL + hC) / 4.0; haO = hO if nH == 0 else (self.haOprev + self.haCprev) / 2.0
        self.haCol = 1 if haC > haO else (-1 if haC < haO else 0); self.haOprev = haO; self.haCprev = haC
        self.hClose[nH % 20] = hC; slot = nH % 200; self.bbwOK[slot] = False
        if nH >= 19:
            mn = sum(self.hClose) / 20.0; v = sum((x - mn) ** 2 for x in self.hClose)
            if mn > 0: self.bbw[slot] = (v / 19.0) ** 0.5 / mn; self.bbwOK[slot] = True
        nH += 1; self.nH = nH; self.lastRank = -1.
        if self.bbwOK[slot]:
            ln = min(200, nH); ok = le = 0
            for q in range(ln):
                sl = (nH - 1 - q) % 200
                if self.bbwOK[sl]:
                    ok += 1
                    if self.bbw[sl] <= self.bbw[slot]: le += 1
            if ok >= 100: self.lastRank = le / ln
    def atr(self):
        nD = len(self.dDate)
        return sum(self.dH[nD - q] - self.dL[nD - q] for q in range(1, 15)) / 14 if nD >= 14 else 0.

    def run_day(self, day, T, O_, H_, L_, C_, now=None, spread=None):
        """One broker day. T..C_ = raw closed minute bars (any bars before `day` are only a look-back for the 2h / 6h ranges).
        Returns the day's trades (entry, stop, exit or open, pips, right-way-first). Changes no history (the object can be reused)."""
        T = np.asarray(T, np.int64); O_, H_, L_, C_ = (np.asarray(x, float) for x in (O_, H_, L_, C_))
        sel = np.flatnonzero((T >= day) & (T < day + 86400))
        if not len(sel): return []
        i0, i1 = int(sel[0]), int(sel[-1]) + 1
        S = dict(curDate=0, cO=0., cH=0., cL=0., cC=0., cBars=0, dayATR=0., dayDir=0, dayOK=False, hKey=0, hO=0., hH=0., hL=0., hC=0., hBars=0)
        # hourly state is copied so the object stays reusable
        hC0, bbw0, ok0 = list(self.hClose), list(self.bbw), list(self.bbwOK); st0 = (self.nH, self.haOprev, self.haCprev, self.haCol, self.lastRank)
        hourDone = [False] * 24; fills = []; TR = []
        sArmed = [False] * NS; sUp = [0.] * NS; sDn = [0.] * NS; sUpDir = [1] * NS; sDnDir = [-1] * NS; sBarsMax = [0] * NS; sBarsCnt = [0] * NS
        dDate, dWeek, dH, dL, dC, dRank, dE10, dE30, wKey, wH, wL = (self.dDate, self.dWeek, self.dH, self.dL, self.dC, self.dRank, self.dE10,
                                                                    self.dE30, self.wKey, self.wH, self.wL)
        def ResetSig(s): sArmed[s] = False; sUp[s] = 0.; sDn[s] = 0.; sUpDir[s] = 1; sDnDir[s] = -1; sBarsMax[s] = 0; sBarsCnt[s] = 0
        def ArmBreak(s, up, dn, bm):
            if not S['dayOK'] or up <= 0 or dn <= 0: return
            ResetSig(s); sUp[s] = up; sDn[s] = dn; sBarsMax[s] = bm; sArmed[s] = True
        def FinishHour():
            self._finish_hour(S['hO'], S['hH'], S['hL'], S['hC']); S['hBars'] = 0
        def StartDay(dt, o0):
            S.update(curDate=dt, cO=o0, cH=o0, cL=o0, cC=o0, cBars=0, dayDir=0); fills.clear()
            for h in range(24): hourDone[h] = False
            for s in range(NS): ResetSig(s)
            S['dayATR'] = self.atr(); S['dayOK'] = S['dayATR'] > 0
            if not S['dayOK']: return
            k = len(dDate); wd = dow(dt); cw = weekof(dt)
            if wd >= 3:
                qs = [q for q in range(max(0, k - 5), k) if dWeek[q] == cw]
                if len(qs) >= 2: ArmBreak(1, max(dH[q] for q in qs), min(dL[q] for q in qs), 0)
            p1 = len(wKey) - 2 if (wKey and wKey[-1] == cw) else len(wKey) - 1
            if p1 >= 1 and wH[p1] <= wH[p1 - 1] and wL[p1] >= wL[p1 - 1]: ArmBreak(2, wH[p1], wL[p1], 0)
            if k >= 2 and dH[k - 1] <= dH[k - 2] and dL[k - 1] >= dL[k - 2]: ArmBreak(3, dH[k - 1], dL[k - 1], 0)
            if k >= 5 and 0 <= dRank[k - 1] <= 0.2:
                ArmBreak(4, max(dH[k - 5:k]), min(dL[k - 5:k]), 0); ArmBreak(6, max(dH[k - 2:k]), min(dL[k - 2:k]), 0)
        def AddClosedBar(i):
            t = int(T[i])
            if S['curDate'] == 0 or not inwin(t) or dateof(t) != S['curDate']: return
            if S['cBars'] == 0: S['cH'] = H_[i]; S['cL'] = L_[i]
            else: S['cH'] = max(S['cH'], H_[i]); S['cL'] = min(S['cL'], L_[i])
            S['cC'] = C_[i]; S['cBars'] += 1
            hk = S['curDate'] + hour(t) * 3600
            if S['hBars'] > 0 and hk != S['hKey']: FinishHour()
            if S['hBars'] == 0: S.update(hKey=hk, hO=O_[i], hH=H_[i], hL=L_[i])
            else: S['hH'] = max(S['hH'], H_[i]); S['hL'] = min(S['hL'], L_[i])
            S['hC'] = C_[i]; S['hBars'] += 1
        def Fire(s, d, lv, i, px, opentick):
            if S['dayDir'] != 0 and d != S['dayDir']: return
            for (fm, fd, fl, fo) in fills:
                if fm == i and fd == d and ((lv > 0 and abs(fl - lv) < PT / 2) or (fo and opentick)): return
            TR.append(dict(i=i, s=s, dir=d, px=float(px), atr=S['dayATR'], first=S['dayDir'] == 0))
            if S['dayDir'] == 0: S['dayDir'] = d
            fills.append((i, d, lv, opentick))
        def HourEvents(i):
            t = int(T[i]); h = hour(t); k = len(dDate); wd = dow(t); cw = weekof(S['curDate'])
            if h >= 6 and not hourDone[6]:
                hourDone[6] = True
                if self.nH >= 211 and self.haCol != 0: Fire(0, self.haCol, 0., i, O_[i], True)
                if wd >= 3:
                    p1 = len(wKey) - 2 if (wKey and wKey[-1] == cw) else len(wKey) - 1
                    if p1 >= 0: ArmBreak(8, wH[p1], wL[p1], 0)
            if h >= 8 and not hourDone[8]:
                hourDone[8] = True
                if S['cBars'] > 0:
                    mv = O_[i] - S['cO']
                    if abs(mv) >= 0.5 * S['dayATR'] and mv != 0:
                        d = 1 if mv > 0 else -1; ext = S['cH'] if d > 0 else S['cL']; lv = ext - d * 0.382 * abs(ext - S['cO'])
                        ResetSig(9); sArmed[9] = True
                        if d > 0: sDn[9] = lv; sDnDir[9] = 1
                        else: sUp[9] = lv; sUpDir[9] = -1
            if h >= 9 and not hourDone[9]:
                hourDone[9] = True
                if k >= 32:
                    ef, es, c1 = dE10[k - 1], dE30[k - 1], dC[k - 1]
                    up = c1 > ef > es; dn = c1 < ef < es
                    if up and O_[i] > ef: ResetSig(7); sDn[7] = ef; sDnDir[7] = -1; sArmed[7] = True
                    if dn and O_[i] < ef: ResetSig(7); sUp[7] = ef; sUpDir[7] = 1; sArmed[7] = True
            if h >= 14 and not hourDone[14]:
                hourDone[14] = True
                if self.nH >= 221 and 0 <= self.lastRank <= 0.1 and i > 361: ArmBreak(10, H_[i - 360:i].max(), L_[i - 360:i].min(), 360)
            if h >= 15 and not hourDone[15]:
                hourDone[15] = True
                if i > 121:
                    up, dn = H_[i - 120:i].max(), L_[i - 120:i].min()
                    if up - dn <= 0.2 * S['dayATR']: ArmBreak(5, up, dn, 240)
        def NewBar(i):
            if i - 1 >= i0: AddClosedBar(i - 1)
            t = int(T[i])
            if not inwin(t): return
            dt = dateof(t); hk = dt + hour(t) * 3600
            if S['hBars'] > 0 and hk != S['hKey']: FinishHour()
            if dt != S['curDate']: StartDay(dt, O_[i])
            for s in range(NS):
                if sArmed[s] and sBarsMax[s] > 0:
                    sBarsCnt[s] += 1
                    if sBarsCnt[s] >= sBarsMax[s]: sArmed[s] = False
            if hour(t) >= 19:
                for s in range(NS):
                    if sArmed[s] and sBarsMax[s] == 0: sArmed[s] = False
            HourEvents(i)
        try:
            for i in range(i0, i1):
                NewBar(i)
                t = int(T[i])
                if isclose(t) or dateof(t) != S['curDate'] or not S['dayOK']:
                    for s in range(NS): sArmed[s] = False
                    continue
                if not any(sArmed): continue
                path = (O_[i], L_[i], H_[i], C_[i]) if C_[i] >= O_[i] else (O_[i], H_[i], L_[i], C_[i])
                for ti, b in enumerate(path):
                    for s in range(NS):
                        if not sArmed[s]: continue
                        d = 0; lv = 0.
                        if sUp[s] > 0 and b >= sUp[s]: d = sUpDir[s]; lv = sUp[s]
                        elif sDn[s] > 0 and b <= sDn[s]: d = sDnDir[s]; lv = sDn[s]
                        if d == 0: continue
                        sArmed[s] = False
                        Fire(s, d, lv, i, b if ti == 0 else lv, ti == 0)
        finally:   # put the hourly history back as it was before the day
            self.hClose, self.bbw, self.bbwOK = hC0, bbw0, ok0; self.nH, self.haOprev, self.haCprev, self.haCol, self.lastRank = st0
        return self._manage(TR, day, T, O_, H_, L_, C_, i0, i1, now, spread)

    def _manage(self, TR, day, T, O_, H_, L_, C_, i0, i1, now, spread):
        """Exits exactly like the research / MT4 check: stop = 0.25 x 14-day range from the entry Bid, checked from the next minute
        (a gap through the stop fills at that minute's open); close at the first minute at/after the close time (18:00 broker, Fridays too) at its open; P/L after
        the spread (at least 1 pip). Right-way-first = 0.3 x 14-day range in favour before 0.3 against, up to the close minute."""
        w = [j for j in range(i0, i1) if inwin(int(T[j]))]
        ct = [j for j in w if isclose(int(T[j]))]; e_close = ct[0] if ct else None
        eod_t = day + ((FRI_CLOSE_HHMM if dow(day) == 5 else CLOSE_HHMM) // 100) * 3600 + ((FRI_CLOSE_HHMM if dow(day) == 5 else CLOSE_HHMM) % 100) * 60
        day_over = now is not None and now >= eod_t
        out = []
        for tr in TR:
            i, d, px = tr['i'], tr['dir'], tr['px']; sd = STOP_X * tr['atr']; stop = px - d * sd; a = 0.3 * tr['atr']
            sp = max(MIN_SPREAD, float(spread[i])) if spread is not None and np.isfinite(spread[i]) else MIN_SPREAD
            after = [j for j in w if j > i and (e_close is None or j <= e_close)]
            ex = ext = None; status = 'open'
            for j in after:
                if j == e_close: ex, ext, status = O_[j], j, 'eod'; break
                if d > 0 and O_[j] <= stop: ex, ext, status = O_[j], j, 'stopped'; break
                if d > 0 and L_[j] <= stop: ex, ext, status = stop, j, 'stopped'; break
                if d < 0 and O_[j] >= stop: ex, ext, status = O_[j], j, 'stopped'; break
                if d < 0 and H_[j] >= stop: ex, ext, status = stop, j, 'stopped'; break
            if ex is None and e_close is None and day_over and w and w[-1] > i:      # day ended before the close minute (holiday / no data)
                ex, ext, status = C_[w[-1]], w[-1], 'eod'
            rwf = None
            for j in after:
                up = (H_[j] - px) if d > 0 else (px - L_[j]); dn = (px - L_[j]) if d > 0 else (H_[j] - px)
                if dn >= a and up >= a: rwf = None; break
                if up >= a: rwf = 1; break
                if dn >= a: rwf = 0; break
            pips = None if ex is None else round(((ex - px) * d - sp) * 100, 1)
            out.append(dict(t=int(T[i]), sig=TAG[tr['s']], name=NAME[tr['s']], dir=d, px=round(px, 3), stop=round(stop, 3), stop_pips=round(sd * 100, 1),
                            first=bool(tr['first']), spread_pips=round(sp * 100, 1), status=status, exit=None if ex is None else round(float(ex), 3),
                            exit_t=None if ext is None else int(T[ext]), pips=pips, rwf=rwf, atr=round(tr['atr'], 3)))
        return out
