"""USDJPY_DAYTRADE v1.07 rules (v1.06 + a 13th signal "WGAP": fades the Friday-close-to-Monday-open gap, firing once at
Monday's first bar when the gap >= WGAP_MIN_ATR x the 14-day range; its own stop (WGAP_STOP x range) and its own tiny
target (WGAP_TARGET x risk, closes WHOLE like S1/S12), full size. KEY FIX (the whole point of this signal): WGAP's own
open leg is EXEMPT from the day-side BREAKOUT FLIP below - it still exits normally via its own stop, its own tiny target,
or the day's close, it just never gets force-closed by another signal's flip. Without this exemption the flip mechanism
force-closed ~29% of WGAP's own trades (era 2012-19 alone), always for a loss, masking the real edge. Corresponds to the
MT4-confirmed EA build "v1.11 WGAP", real MT4 run 5 Nov 2026: PASSED (win rate hit-target +0.15pt FULL / +0.23pt 2023-26,
both clearing the +0.1pt bar; flip-protected count >0 in both "on" runs - the fix engaged for real; net/DD/worst-day/
green-days all flat or improved) - see day-trading-usdjpy-2.
v1.06 (v1.05 + a 12th signal "HAM": the SAME Heikin-Ashi 7am scalp as signal 1, fired again at one
more broker hour (HAM_HOUR=7) to raise win rate and trade frequency - the accuracy/frequency goal, 2 Nov. Corresponds to the
MT4-confirmed EA build "v1.09 HAM(hour7)", real MT4 run 3 Nov 2026: PASSED all 12 pass-bar criteria (win rate +1.39pt FULL /
+1.28pt 2023-26, trades/day +23%, every P&L guardrail milder than predicted, worst day unchanged) - see day-trading-usdjpy-2.
v1.05 (v1.04 + at most ONE flip a day that closes open trades; MT4 run 22 Oct passed)
= v1.04 rules (the MT4 EA, 11 signals) as a PAPER engine for the portal - same logic as the EA, line by line.
v1.04 (MT4 run 22 Oct passed): (a) the Heikin-Ashi 7am trade closes WHOLE at a tiny target = 0.03 x its risk (status 'target');
(b) BREAKOUT FLIP: a quiet signal (3,4,5,6,7,11) against the day's side closes today's open trades at its price (status 'reversed')
and switches the day to the new side.
v1.03 exits: quiet signals stop 0.25 x range, close half at +0.5 x risk; other signals stop 0.75 x range, half at +0.10 x risk;
after the half the rest closes at the entry price; day lock +2R / +1R; one trade per minute; Heikin-Ashi 7am at 1/3 size;
close 18:00 broker, Fridays 14:00.
Prices are Bid. Broker clock = New York + 7h. Window = 01:05-23:57 broker, Monday-Friday (FX rollover minutes left out).
History = the EA's own daily and hourly bars: finished broker days / hours built from the window's minute bars.
Times are integer seconds on the broker clock (naive)."""
import numpy as np

NS = 13
TAG = ['J13', 'L3', 'M8', 'N3', 'M1a', 'J21', 'M1b', 'L1', 'U5', 'L7', 'Q5', 'S12 HAM', 'S13 WGAP']
NAME = ['Heikin-Ashi 7am', 'Week-so-far break', 'Inside-week break', 'Inside-day break', 'Quiet 5-day break', 'Squeeze 4pm',
        'Quiet 2-day break', 'EMA10 break', 'Last-week break', 'Morning pullback', 'Hourly squeeze 3pm', 'HAM (Heikin-Ashi, 2nd hour)',
        'WGAP (weekend-gap fade)']
PT = 0.001; MIN_SPREAD = 0.01                        # 1 pip = the MT4 test spread; the paper P/L never uses less
FIX_SPREAD = 0.010                                   # 22 Oct fix: ONE fixed spread (1.0 pip = the MT4 v1.05 test) for entry, stop, half level and P/L.
                                                     # Capital.com re-sends a different ask for the same finished minute, so the live spread made
                                                     # shown stops / half flags change after the fact. MT4 tests use a fixed spread too (10 points).
EOD_GRACE = 600                                      # 23 Oct fix: with no bar at/after the close yet, book the day-end close at the last close only
                                                     # this many seconds after the close time (was: at once -> 17:59 close, then 18:00 open a minute later)
QUIET = {2, 3, 4, 5, 6, 10}                          # EA signals 3,4,5,6,7,11 (inside-week / inside-day / quiet 5-day / squeeze 4pm / quiet 2-day / hourly squeeze)
Q_STOP, Q_HALF, O_STOP, O_HALF = 0.25, 0.50, 0.75, 0.10   # stop = x 14-day range; half at + x risk (risk = stop distance incl. spread)
PART, LOCK_PK, LOCK_FL, HA_W = 0.5, 2.0, 1.0, 1 / 3      # half part; day lock peak / floor in R; Heikin-Ashi 7am size
HA_TARGET = 0.03                                     # v1.04: Heikin-Ashi 7am closes the whole trade at + this x risk (0 = v1.03 half-close)
HAM_HOUR = 7                                         # v1.06: signal 12 "HAM" - the EXACT same Heikin-Ashi scalp as signal 0 (weight/target below),
                                                     # fired again once more at this broker hour (do not use 6,8,9,14,15 - already used by other signals)
WGAP_ON = True                                       # v1.07: signal 12 (0-based) "WGAP" on/off switch (yen_run.py date-gates this, like HAM_HOUR=-1)
WGAP_MIN_ATR = 0.10                                  # gap vs the last finished day's close must be >= this x the 14-day range to fire
WGAP_STOP = 0.60                                     # WGAP's own real stop, x the 14-day range (not the quiet/other convention)
WGAP_TARGET = 0.03                                   # WGAP closes the WHOLE trade at + this x risk - same tiny-target mechanism as S1/S12
FLIP = True                                          # v1.04: a quiet signal against the day's side closes open trades and switches the side
FLIP_MAX = 1                                         # v1.05: at most this many flips a day that close open trades (0 = no limit = v1.04)
RISK_USD = 100.0                                     # v1.03 set file Risk_Dollars=100: a full-size stop = $100 (the MT4 backtest's size)
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
CLOSE_HHMM, FRI_CLOSE_HHMM = 1800, 1400              # v1.03 inputs Close_Hour=18, Friday_Close_HHMM=1400 (MT4 run 2026-10-18 passed)
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
        """`spread` is accepted for old callers but ignored: every level and P/L uses FIX_SPREAD (23 Oct fix). One broker day. T..C_ = raw closed minute bars (any bars before `day` are only a look-back for the 2h / 6h ranges).
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
        def StartDay(dt, o0, i):
            S.update(curDate=dt, cO=o0, cH=o0, cL=o0, cC=o0, cBars=0, dayDir=0); fills.clear()
            for h in range(24): hourDone[h] = False
            for s in range(NS): ResetSig(s)
            S['dayATR'] = self.atr(); S['dayOK'] = S['dayATR'] > 0
            if not S['dayOK']: return
            k = len(dDate); wd = dow(dt); cw = weekof(dt)
            if WGAP_ON and wd == 1 and k >= 1:              # v1.07: S13 WGAP - fade the gap vs the last finished day's close (normally Friday's), fires once
                gap = o0 - dC[k - 1]
                if abs(gap) >= WGAP_MIN_ATR * S['dayATR']: Fire(12, (-1 if gap > 0 else 1), 0., i, o0, True)
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
        def Fire(s, d, lv, i, px, opentick):          # v1.04+: the day's side (ladder / flip) is decided in _manage, trade by trade (= MT4 + Python port)
            if not FLIP and S['dayDir'] != 0 and d != S['dayDir']: return                 # v1.03 days: ladder here, exactly as before
            if not FLIP:                                # v1.04+: same-minute duplicates are dropped in _manage (one trade per minute), after the ladder, like the EA
                for (fm, fd, fl, fo) in fills:
                    if fm == i and fd == d and ((lv > 0 and abs(fl - lv) < PT / 2) or (fo and opentick)): return
            TR.append(dict(i=i, s=s, dir=d, px=float(px), atr=S['dayATR'], first=S['dayDir'] == 0))
            if not FLIP and S['dayDir'] == 0: S['dayDir'] = d
            fills.append((i, d, lv, opentick))
        def HourEvents(i):
            t = int(T[i]); h = hour(t); k = len(dDate); wd = dow(t); cw = weekof(S['curDate'])
            if h >= 6 and not hourDone[6]:
                hourDone[6] = True
                if self.nH >= 211 and self.haCol != 0: Fire(0, self.haCol, 0., i, O_[i], True)
                if wd >= 3:
                    p1 = len(wKey) - 2 if (wKey and wKey[-1] == cw) else len(wKey) - 1
                    if p1 >= 0: ArmBreak(8, wH[p1], wL[p1], 0)
            if HAM_HOUR >= 0 and h >= HAM_HOUR and not hourDone[HAM_HOUR]:        # v1.06: S12 HAM - a 2nd sample of signal 0's own logic, same hour each day
                hourDone[HAM_HOUR] = True
                if self.nH >= 211 and self.haCol != 0: Fire(11, self.haCol, 0., i, O_[i], True)
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
            if dt != S['curDate']: StartDay(dt, O_[i], i)
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
        """v1.03 exits, in the order of the Python port that the MT4 v1.03 run matched (check/port103y.py), per minute:
        1) new trades (skipped once the day is locked, and a 2nd trade in the same minute is skipped); buys fill at Ask = Bid + spread,
           sells at Bid; stop = Bid - sd (buys) / Ask + sd (sells), risk = |entry - stop|; 2) trades from earlier minutes: stop first
           (a gap fills at the minute's open), then the half level (half closed there, the rest's stop moves to the entry);
           3) day lock at the minute's close: once the day (closed + open, in R) has reached +2R, everything closes at +1R or less and
           no more trades that day. Close everything at the first minute at/after the close time, at its open.
        R = the trade's full-size stop sd (the EA's lgU), so the Heikin-Ashi 7am trade counts 1/3. Right-way-first kept for the record
        (0.3 x 14-day range in favour before 0.3 against, up to the close minute)."""
        w = [j for j in range(i0, i1) if inwin(int(T[j]))]
        ct = [j for j in w if isclose(int(T[j]))]; e_close = ct[0] if ct else None
        hm = FRI_CLOSE_HHMM if dow(day) == 5 else CLOSE_HHMM
        eod_t = day + (hm // 100) * 3600 + (hm % 100) * 60
        day_over = now is not None and now >= eod_t + EOD_GRACE      # 23 Oct: until then, open trades wait for the close bar's open (row shows 'close_now')
        def SP(j): return FIX_SPREAD          # 23 Oct: fixed spread (the `spread` argument is no longer used for levels or P/L - see FIX_SPREAD)
        byi = {}
        for tr in TR: byi.setdefault(tr['i'], []).append(tr)
        legs = []; banked = 0.; peak = 0.; off = False; ddir = 0; nflip = 0
        def mark(l, bid, sp):            # value of a leg in R (sized) at this Bid
            rem = 1 - PART if l['half'] else 1.0; px = bid if l['d'] > 0 else bid + sp
            return l['w'] * (l['bank'] + rem * l['d'] * (px - l['e']) / l['sd'])
        def shut(l, px, j, why):
            nonlocal banked
            rem = 1 - PART if l['half'] else 1.0
            l['r'] = l['bank'] + rem * l['d'] * (px - l['e']) / l['sd']; banked += l['w'] * l['r']
            l.update(on=False, ex=px, ext=j, status=why)
        for j in w:
            if e_close is not None and j >= e_close: break
            took = False
            for tr in byi.get(j, []):
                if off: continue
                if FLIP and ddir != 0 and tr['dir'] != ddir:         # ladder: later trades only the day's side ...
                    if not (FLIP and tr['s'] in QUIET): continue
                    if any(l['on'] for l in legs):         # ... v1.04 flip: a quiet signal closes the open trades at its price and switches the side
                        if FLIP_MAX > 0 and nflip >= FLIP_MAX: continue          # v1.05: at most FLIP_MAX such flips a day
                        fsp = SP(j)
                        for l in legs:                                          # v1.07: S13 WGAP's own leg is EXEMPT from flip-closure (still exits via its own stop/target/EOD)
                            if l['on'] and l['tr']['s'] != 12: shut(l, tr['px'] if l['d'] > 0 else tr['px'] + fsp, j, 'reversed')
                        nflip += 1
                    ddir = tr['dir']
                if took: continue
                s, d, px = tr['s'], tr['dir'], tr['px']; q = s in QUIET
                sd = (WGAP_STOP if s == 12 else (Q_STOP if q else O_STOP)) * tr['atr']    # v1.07: S13 WGAP uses its own stop (x 14-day range)
                if not sd > 0: continue
                sp = SP(j); e = px + sp if d > 0 else px; sl = px - sd if d > 0 else px + sp + sd; k = Q_HALF if q else O_HALF
                tgt = (s in (0, 11) and HA_TARGET > 0) or (s == 12 and WGAP_TARGET > 0)   # v1.06: S12 HAM; v1.07: S13 WGAP - both close WHOLE at a tiny target
                if tgt: k = WGAP_TARGET if s == 12 else HA_TARGET
                legs.append(dict(tr=tr, w=(HA_W if s in (0, 11) else 1.0), d=d, px=px, e=e, sl=sl, sl0=sl, sd=sd, sp=sp,
                                 hp=(e + d * k * abs(e - sl)) if k > 0 else None, half=False, half_t=None, bank=0., j=j, on=True,
                                 r=None, ex=None, ext=None, status='open', tgt=tgt, first=(ddir == 0)))
                if ddir == 0: ddir = d
                took = True
            sp = SP(j)
            for l in legs:
                if not l['on'] or j <= l['j']: continue
                d = l['d']
                if (d > 0 and L_[j] <= l['sl']) or (d < 0 and H_[j] + sp >= l['sl']):
                    px = min(l['sl'], O_[j]) if d > 0 else max(l['sl'], O_[j] + sp)
                    shut(l, px, j, 'be' if l['half'] else 'stopped'); continue
                if not l['half'] and l['hp'] is not None and ((d > 0 and H_[j] >= l['hp']) or (d < 0 and L_[j] + sp <= l['hp'])):
                    if l['tgt']: shut(l, l['hp'], j, 'target'); continue          # v1.04: Heikin-Ashi whole trade at the tiny target
                    l['bank'] = PART * d * (l['hp'] - l['e']) / l['sd']; l['half'] = True; l['half_t'] = j
                    l['sl'] = max(l['sl'], l['e']) if d > 0 else min(l['sl'], l['e'])
            tot = banked + sum(mark(l, C_[j], sp) for l in legs if l['on']); peak = max(peak, tot)
            if LOCK_PK > 0 and not off and peak >= LOCK_PK and tot <= LOCK_FL:
                for l in legs:
                    if l['on']: shut(l, C_[j] if l['d'] > 0 else C_[j] + sp, j, 'day lock')
                off = True
        if e_close is not None:
            sp = SP(e_close)
            for l in legs:
                if l['on']: shut(l, O_[e_close] if l['d'] > 0 else O_[e_close] + sp, e_close, 'eod')
        elif day_over and w:                 # no bar at/after the close EOD_GRACE after the close time (holiday / no data): last close
            sp = SP(w[-1])
            for l in legs:
                if l['on']: shut(l, C_[w[-1]] if l['d'] > 0 else C_[w[-1]] + sp, w[-1], 'eod')
        out = []
        lastj = w[-1] if w else None
        for l in legs:
            tr = l['tr']; i, d, px = l['j'], l['d'], l['px']; a = 0.3 * tr['atr']
            after = [j for j in w if j > i and (e_close is None or j <= e_close)]
            rwf = None
            for j in after:
                up = (H_[j] - px) if d > 0 else (px - L_[j]); dn = (px - L_[j]) if d > 0 else (H_[j] - px)
                if dn >= a and up >= a: rwf = None; break
                if up >= a: rwf = 1; break
                if dn >= a: rwf = 0; break
            rem = 1 - PART if l['half'] else 1.0
            if l['r'] is None:               # still open: value now (last closed minute)
                now_px = None if lastj is None else (C_[lastj] if d > 0 else C_[lastj] + SP(lastj))
                r_now = None if now_px is None else l['bank'] + rem * d * (now_px - l['e']) / l['sd']
                pips = None
            else:
                r_now = l['r']
                pips = l['w'] * ((PART * d * (l['hp'] - l['e']) if l['half'] else 0.) + rem * d * (l['ex'] - l['e'])) * 100
            out.append(dict(t=int(T[i]), sig=TAG[tr['s']], name=NAME[tr['s']], dir=d, px=round(px, 3), entry=round(l['e'], 3),
                            stop=round(l['sl'], 3), stop0=round(l['sl0'], 3), stop_pips=round(abs(l['e'] - l['sl0']) * 100, 1),
                            half_px=None if l['hp'] is None else round(l['hp'], 3), half=bool(l['half']),
                            half_t=None if l['half_t'] is None else int(T[l['half_t']]), size='third' if l['w'] < 1 else 'full', w=l['w'], part=1.0 if l['tgt'] else PART,
                            quiet=tr['s'] in QUIET, first=bool(l['first'] if FLIP else tr['first']), spread_pips=round(l['sp'] * 100, 1), status=l['status'],
                            exit=None if l['ex'] is None else round(float(l['ex']), 3), exit_t=None if l['ext'] is None else int(T[l['ext']]),
                            r=None if l['r'] is None else round(l['r'], 4), r_now=None if r_now is None else round(r_now, 4),
                            pips=None if pips is None else round(pips, 1), rwf=rwf, atr=round(tr['atr'], 3), locked_day=off))
        return out
