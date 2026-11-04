"""GOLD v2.20 trade manager (from V220_FROM; v2.15 before that, v2.11 before that) (SPLIT=False below; v2.09/v2.10 = SPLIT=True) for the Signal Desk (same rules as EA GOLD_DAYTRADE v2.09 + DT209_GOLD_MAX2_HALF020.set).
Input: today's engine signals (engine206.run_day, skipped ones removed) + today's closed minute bars. Output: the trades he
should hold (legs), their state, and a time-ordered list of ACTIONS for the page (no Telegram).

Rules (tested: MT4 his run 2020-26, trades win ~80%, ~73% green days; Python mirror sim10.py):
- ONE direction at a time. A signal the same way while trades are open: ADD if fewer than 2 open and not in the same minute
  as an open trade's entry, else HOLD (do nothing).
- Opposite engine signals never reach here (the engine skips signals against the day's earlier trades), except against a
  range-fade FILL trade: then CLOSE ALL and open the other way (REVERSE) - same as the EA.
- Every trade: size 1 (desk size), stop = 0.5 x 14-day average daily range from the signal price (buy: below the bid,
  sell: above the ask). CLOSE HALF when profit = 0.20 x stop distance, then MOVE STOP TO ENTRY on the rest.
  The rest runs to its stop (entry) or the day-end close.
- FILL: if no engine signal by then, the broker 10:00-11:59 range; the first break within 6 hours is faded (break up = SELL,
  break down = BUY), entered at the next minute's open. v2.20 (from V220_FROM, mirrors EA Fill_Target_x_DailyATR=0.5): the FILL
  leg also gets a take-profit target = entry +/- FILLTX x atr; whichever of stop/target is touched first in a bar closes it
  (tie-break on the same up/down-bar tick order already used for the entry-minute stop check). Signal ('s') legs never get a
  target - only the FILL ('f') leg does.
Prices: bars are Bid. Buys fill at Ask (= bid + spread) and exit at Bid; sells fill at Bid and exit at Ask."""
import numpy as np

SP = 0.5          # Capital.com gold spread ($/oz) - same as the engine's S['Spread']
V211_FROM = np.datetime64('2026-10-20')   # v2.11 from this broker day (MT4 passed twice 20 Oct): NO half-close, NO stop to entry -
                                          # trades run to their stop or the day-end close (Use_Split_Exit=false). Earlier days = v2.10 (half at K).
K = 0.20          # close half at K x stop distance (Split_At_x_Stop) - used only when SPLIT = True (v2.10)
EX = 0.0          # extra $ beyond the half level (Split_Extra_Dollars)
STOPX = 0.5       # stop = STOPX x 14-day range for every signal (Signal_Stop_Target, Stop_Other = 0)
FILLX = 0.5       # stop for the fill trade (Fill_Stop_x_DailyATR)
NMAX = 2          # Max_Same_Way_Trades
FILL_FROM, FILL_MIN, FILL_HOURS = 10 * 60, 120, 6
# ---- v2.15 (= EA GOLD_DAYTRADE v2.15 + DT215_GOLD_ADDWIN.set, MT4 passed 21 Oct: $247/$263 per weekday at $1,000 risk 2020-22/2023-26)
V215_FROM = np.datetime64('2026-10-22')   # from this broker day: day lock + real-yield size + strong-family size + add to winners
LOCK_AT, LOCK_KEEP = 2.0, 0.5             # v2.12 day lock: once today's gold result (closed + open, in R) reached +2R, close ALL and stop if it falls to +0.5R
RY_SIZE = 1.5                             # v2.13: a trade AGAINST the latest known 1-day change of the US 10-yr real yield (dated 2+ days before) = size 1.5
FAM_SIZE = 1.5                            # v2.14: strong-family signals (quiet/compression breakouts) = size 1.5 (signal trades only, not the fill)
STRONG = {'G1', 'G2', 'G3', 'G4', 'G5', 'G6', 'G7', 'G8', 'G9', 'G10', 'G11', 'G13', 'A15', 'N11', 'N13', 'N16', 'N16b', 'S24', 'T15'}
PYRN, PYRX = 3, 1.25                      # v2.15: a 3rd same-way trade only if EVERY open trade is up >= 1.25 x its own stop distance
# ---- v2.20 (= EA GOLD_DAYTRADE v2.20 Fill_Target fix: the FILL range-fade leg gets a take-profit, mirroring its stop)
V220_FROM = np.datetime64('2026-11-04')   # from this broker day: the FILL leg also gets a target (before this, no target - stop only)
FILLTX = 0.5                              # FILL take-profit = FILLTX x 14-day average daily range (Fill_Target_x_DailyATR)


def size_of(kind, tag, d, ry):
    """v2.15 size multiplier of a new trade. ry = latest known real-yield 1-day change (None = unknown -> no yield size)."""
    fam = FAM_SIZE if (kind == 's' and str(tag).split(' ')[0] in STRONG) else 1.0
    yz = RY_SIZE if (ry is not None and ((ry > 0 and d > 0) or (ry < 0 and d < 0))) else 1.0
    return round(fam * yz, 4)


def fill_event(T, O, H, L, day, eod):
    """Range-fade fill for broker day `day` from today's minute bars. Returns (bar index of entry, dir) or None."""
    m = ((T - day.astype('datetime64[m]')) / np.timedelta64(1, 'm')).astype(int)
    rng = np.where((m >= FILL_FROM) & (m < FILL_FROM + FILL_MIN))[0]
    if len(rng) == 0: return None
    b = rng[-1]; hi, lo = H[rng].max(), L[rng].min()
    for j in range(b + 1, len(T)):
        if m[j] >= FILL_FROM + FILL_MIN + FILL_HOURS * 60 or T[j] >= eod: return None
        if H[j] > hi: return (j + 1, -1) if j + 1 < len(T) else ('pending', -1)
        if L[j] < lo: return (j + 1, 1) if j + 1 < len(T) else ('pending', 1)
    return None


def run(signals, day, m1, now, atr, eod, label=None, ry=None):
    """signals: engine trades (dict t, dir, tag, px). day: np.datetime64[D]. m1: dict t,o,h,l,c (closed bars, broker time).
    atr: 14-day average daily range. eod: np.datetime64[m] day-end close. Returns (legs, actions)."""
    T = np.asarray(m1['t'], dtype='datetime64[m]'); O, H, L, C = (np.asarray(m1[k], float) for k in ('o', 'h', 'l', 'c'))
    SPLIT = np.datetime64(day, 'D') < V211_FROM                      # True = v2.10 half-close rules (days before the switch)
    V215 = np.datetime64(day, 'D') >= V215_FROM                      # True = v2.15 lock + sizes + add to winners
    V220 = np.datetime64(day, 'D') >= V220_FROM                      # True = v2.20 FILL leg gets a take-profit target
    st = dict(closedR=0.0, peak=0.0, locked=False)
    legs, act = [], []
    if len(T) == 0 or atr <= 0: return legs, act
    jidx = lambda t: int(np.searchsorted(T, np.datetime64(t, 'm'), side='left'))
    ev = [(jidx(s['t']), s['dir'], 's', float(s['px']), s['tag'], np.datetime64(s['t'], 'm')) for s in signals]
    ev = [e for e in ev if e[0] < len(T)]
    fe = fill_event(T, O, H, L, day, eod)
    if fe and fe[0] != 'pending' and (not ev or ev[0][0] > fe[0]):
        ev.append((fe[0], fe[1], 'f', float(O[fe[0]]), 'FILL range fade', T[fe[0]]))
    ev.sort(key=lambda e: (e[0], 0 if e[2] == 'f' else 1))
    side = lambda d: 'BUY' if d > 0 else 'SELL'
    openl = lambda: [g for g in legs if g['status'] in ('open', 'half')]

    def add(t, kind, d, text, px=None, g=None):   # li = index of the leg this action belongs to (None = whole-position action)
        act.append(dict(t=t, kind=kind, side=side(d), text=text, price=px, li=(None if g is None else g['li'])))

    def new_leg(j, d, kind, p0, tag, t):
        sd = (FILLX if kind == 'f' else STOPX) * atr
        if d > 0: e = p0 + SP; sl = (e - sd) if kind == 'f' else (p0 - sd)
        else: e = p0; sl = (e + sd) if kind == 'f' else (p0 + SP + sd)
        risk = abs(e - sl); hp = (e + d * (K * risk + EX)) if SPLIT else None
        tgt = (e + d * FILLTX * atr) if (kind == 'f' and V220) else None   # v2.20: FILL leg only, from V220_FROM
        g = dict(li=len(legs), j=j, t=t, dir=d, tag=tag, kind=kind, p0=float(p0), entry=round(e, 2), stop0=round(sl, 2), stop=round(sl, 2), risk=round(risk, 2), sd=sd,
                 size_x=(size_of(kind, tag, d, ry) if V215 else 1.0),
                 half_px=(round(hp, 2) if hp is not None else None), target=(round(tgt, 2) if tgt is not None else None),
                 status='open', half_t=None, exit=None, exit_t=None, pnl_oz=None, time_txt=('from ' + label(t)) if label else '#%d' % (len(legs) + 1))
        legs.append(g); return g

    def close_leg(g, px, t, why):
        d = g['dir']; full = 0.5 if g['status'] == 'half' else 1.0
        banked = 0.5 * d * (g['half_px'] - g['entry']) if g['status'] == 'half' else 0.0
        g.update(exit=round(px, 2), exit_t=t, status=why, pnl_oz=round(banked + full * d * (px - g['entry']), 2))
        st['closedR'] += g['size_x'] * (banked + full * d * (px - g['entry'])) / g['sd']

    def walk(j0, j1):
        """Stops and half-closes on bars j0..j1-1. FIX 22 Oct (fixpack): the stop is live from the fill, like the EA and
        engine206.manage - in the ENTRY minute the part of the bar after the fill is checked on the EA tester's tick path
        (up bar O-L-H-C, down bar O-H-L-C; a fill at the bar open meets the whole bar). Before: the entry minute was skipped.
        v2.20: the FILL leg's target competes with its stop the same way - see touch() below."""

        def touch(j, g):
            """v2.20: which of stop/target (if either) is hit on bar j. Reuses the SAME up/down-bar tick order as the
            entry-minute stop check above (up bar visits L before H: O-L-H-C; down bar visits H before L: O-H-L-C) to
            decide which is touched first when BOTH are hit within the same bar. Only called for legs that have a target
            (the FILL leg, from V220_FROM) - other legs keep the plain stop-only checks below untouched."""
            d = g['dir']
            stop_hit = (L[j] <= g['stop']) if d > 0 else (H[j] + SP >= g['stop'])
            targ_hit = (H[j] >= g['target']) if d > 0 else (L[j] + SP <= g['target'])
            if stop_hit and targ_hit:
                up_bar = C[j] >= O[j]
                stop_first = up_bar if d > 0 else (not up_bar)   # up bar: L-side level first (stop if long, target if short)
                return 'stop' if stop_first else 'target'
            if stop_hit: return 'stop'
            if targ_hit: return 'target'
            return None

        for j in range(j0, j1):
            if T[j] >= eod: return
            for g in openl():
                if j < g['j']: continue
                d = g['dir']
                has_tgt = g['target'] is not None
                if j == g['j']:
                    at_open = abs(g['p0'] - O[j]) < 1e-9; up_bar = C[j] >= O[j]
                    if has_tgt:
                        w = touch(j, g)
                        if w == 'target':
                            close_leg(g, g['target'], T[j], 'target hit')
                            add(T[j], 'TARGET', d, f"{side(d)} {g['time_txt']}: TARGET HIT at {g['target']:.2f} in its entry minute - trade closed", g['target'], g)
                            continue
                        hit = (w == 'stop')
                    elif d > 0: hit = (L[j] if (at_open or not up_bar) else C[j]) <= g['stop']
                    else: hit = (H[j] if (at_open or up_bar) else C[j]) + SP >= g['stop']
                    if hit:
                        close_leg(g, g['stop'], T[j], 'stop hit')
                        add(T[j], 'STOP', d, f"{side(d)} {g['time_txt']}: STOP HIT at {g['stop']:.2f} in its entry minute - trade closed", g['stop'], g)
                    continue
                if has_tgt:
                    w = touch(j, g)
                    if w == 'target':
                        close_leg(g, g['target'], T[j], 'target hit')
                        add(T[j], 'TARGET', d, f"{side(d)} {g['time_txt']}: TARGET HIT at {g['target']:.2f} - trade closed", g['target'], g)
                        continue
                    stop_now = (w == 'stop')
                else:
                    stop_now = (d > 0 and L[j] <= g['stop']) or (d < 0 and H[j] + SP >= g['stop'])
                if stop_now:
                    px = min(g['stop'], O[j]) if d > 0 else max(g['stop'], O[j] + SP)
                    be = g['status'] == 'half'
                    close_leg(g, px, T[j], 'stop at entry' if be else 'stop hit')
                    add(T[j], 'STOP', d, (f"{side(d)} {g['time_txt']}: stop at entry hit at {px:.2f} - the rest is closed, half was banked"
                                          if be else f"{side(d)} {g['time_txt']}: STOP HIT at {px:.2f} - trade closed"), round(px, 2), g)
                    continue
                if SPLIT and g['status'] == 'open' and ((d > 0 and H[j] >= g['half_px']) or (d < 0 and L[j] + SP <= g['half_px'])):
                    g.update(status='half', half_t=T[j], stop=g['entry'])
                    add(T[j], 'HALF', d, f"CLOSE HALF of your {side(d)} {g['time_txt']} now at {g['half_px']:.2f}, then MOVE STOP of the rest to {g['entry']:.2f} (entry)", g['half_px'], g)
            op = openl()
            if V215 and op:                      # v2.12 day lock on this bar's close (same as the EA / Python sim11)
                d0 = op[0]['dir']; pxc = C[j] if d0 > 0 else C[j] + SP
                tot = st['closedR'] + sum(g['size_x'] * d0 * (pxc - g['entry']) / g['sd'] for g in op); st['peak'] = max(st['peak'], tot)
                if st['peak'] >= LOCK_AT and tot <= LOCK_KEEP:
                    for g in op: close_leg(g, pxc, T[j], 'day lock')
                    add(T[j], 'LOCK', d0, f"DAY LOCK - CLOSE ALL your gold trades now (~{pxc:.2f}): today reached +{st['peak']:.1f}R and fell back to +{tot:.1f}R. No more gold trades today", round(pxc, 2))
                    st['locked'] = True; return

    cur = 0
    for (j, d, kind, p0, tag, t) in ev:
        walk(cur, j); cur = j                    # bars before this event
        if st['locked']: break
        if T[min(j, len(T) - 1)] >= eod: break
        op = openl()
        if op and op[0]['dir'] == d:
            same_min = any(g['t'] == t for g in op)
            win = V215 and len(op) >= NMAX and len(op) < PYRN and all(d * (p0 - g['entry']) / g['sd'] >= PYRX for g in op)
            if (len(op) < NMAX or win) and not same_min:
                g = new_leg(j, d, kind, p0, tag, t)
                add(t, 'ADD', d, f"ADD {side(d)} ({len(op) + 1}{'nd' if len(op) == 1 else 'rd'} trade{', all open trades are up 1.25x their stop' if win else ''}) now ~{g['entry']:.2f} | stop {g['stop']:.2f} | " + (f"close half at {g['half_px']:.2f}" if SPLIT else "no half-close: hold to the stop or the day-end close") + (f" | size x{g['size_x']:g}" if g['size_x'] != 1 else "") + f" | signal {tag}", g['entry'], g)
            else:
                add(t, 'HOLD', d, f"HOLD - new {side(d)} signal ({tag}) but {'a trade was opened this minute' if same_min else (str(len(op)) + ' trades are already open' + (' and not all are up 1.25x their stop' if V215 and len(op) < PYRN else ''))}: do nothing")
            continue
        if op:   # opposite signal against an open (fill) trade: close all, turn round
            px = p0 if op[0]['dir'] > 0 else p0 + SP
            for g in op: close_leg(g, px, t, 'reversed')
            add(t, 'REVERSE', d, f"REVERSE - close ALL your {side(-d)} trades now (~{px:.2f}) and {side(d)} instead", round(px, 2))
        g = new_leg(j, d, kind, p0, tag, t)
        add(t, 'OPEN', d, f"OPEN {side(d)} now ~{g['entry']:.2f} | stop {g['stop']:.2f} ({g['risk']:.1f} away) | " + (f"close half at {g['half_px']:.2f}" if SPLIT else "no half-close: hold to the stop or the day-end close") + (f" | size x{g['size_x']:g}" if g['size_x'] != 1 else "") + f" | signal {tag}", g['entry'], g)
    if not st['locked']: walk(cur, len(T))
    after = np.datetime64(now, 'm') >= eod
    if after:
        op = openl()
        if op:
            k = int(np.searchsorted(T, eod, side='left')); k = min(max(k - 1, 0), len(T) - 1)
            for g in op: close_leg(g, C[k] if g['dir'] > 0 else C[k] + SP, eod, 'day end')
            add(eod, 'CLOSE_ALL', op[0]['dir'], f"END OF DAY - CLOSE ALL your gold trades now ({len(op)} open)")
    act.sort(key=lambda a: a['t'])
    return legs, act
