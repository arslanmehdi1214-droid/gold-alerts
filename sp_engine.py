"""S&P 500 (US500) PAPER engine for the Signal Desk - "version A" (MT4-proven 22 Oct 2026: his run SP500_DAYTRADE v1.00, .US500Cash M1 every
tick, spread 0.8 pt, 2020-01-01..2026-09-30: 2,330 trades, net $16,398 at $100 risk per leg, net/DD 6.23, worst day -$310; Python $16,437).
Broker clock = New York + 7 h (bid prices). One ladder per day:
  EVENTS  (a) Nasdaq desk picks (the Nasdaq engine's day picks: first core signal + a filler before it) copied to the S&P at the NEXT minute,
              same side, only when that S&P minute is in US hours 16:30-21:59 broker;
          (b) S&P book: 16:40 opening move (open 16:40 - open 16:00 beyond 0.05 x range -> follow);
              yesterday high/low sweep by 0.1 x range from 09:00 and from 13:00 broker (scan to 19:00), back inside within 30 min -> reverse,
              entry the next minute;
              day move since the open >= 0.8 x range at the first bar from 17:00 -> follow, entry the next minute (this idea is in the book
              twice - as "follow" and as "reversed fade" - so it adds two legs, exactly as tested).
  LADDER  the day's first event sets the side; later events the same side add a leg (max 3 legs); the other side is ignored.
          Same-minute events are taken in the research order (minute, side, source). No entries in the day-end minute or from 22:25 broker.
  EXIT    stop = 0.75 x the 14-day average daily range (high-low of the 14 previous broker days) from the entry; no half-close;
          everything closes at the open of the first bar at/after 22:30 broker (3:30 pm New York); if no such bar, at the day's last close.
v1.04 (24 Oct 2026, his MT4 run SP500_DAYTRADE v1.04: net $16,896, net/DD 8.83, profit days 44.5%, both halves better than v1.00/v1.02):
  DAY RULES  a 2nd/3rd leg is NOT opened (a) at/after 11:00 am New York (18:00 broker), or (b) when the day's legs taken so far are already
             up >= 0.5 x stop (= $50 at $100 risk) after cost, counting closed + open legs at the entry price. The first leg is never blocked.
  NIGHT LEG  on high-fear nights (last Cboe close before the broker day: VIX > VIX3M, or VIX in its 1-year top 10%, or VVIX in its 1-year
             top 10%) BUY at 6:01 pm New York (01:01 broker), stop 2.0 x range, close at 10:00 am New York (17:00 broker). Not part of the ladder.
v1.08 (3 Nov 2026, "Night V3": his MT4 run SP500_DAYTRADE v1.07 Magic 500114 layered on the 500109 baseline - net $14,518.89 (+$579.68 vs
       500109's $13,939.21), DD $2,213.73/0.22% (improved $163.64), 2445 trades (+83), the 83 new legs alone = 57.8% closed in profit):
  NIGHT LEG V3  a SECOND, independent night trigger (fires only when the regular high-fear night leg above does NOT, so the two never
                double-trade the same night): on broker-day Wed/Thu/Fri only, BUY at 6:01 pm New York (01:01 broker) if gold (GC=F) and
                WTI (CL=F) both had a big daily move 2 calendar days before - the smaller of the two 252-day-rolling percentile-ranked
                |daily % close move|, min(gold_pct, wti_pct) >= 0.70 - same stop (1.0 x range) and close (10:00 am New York) as the
                regular night leg. Found 2 Nov 2026 free-data hunt (gold+WTI combined overnight shock, 21-idea round in the S&P chat),
                MT4-confirmed 3 Nov. Source for gc_pct/wti_pct: Yahoo Finance daily closes (free), cached/refreshed once a day - see
                gw_today() in sp_run.py.
v1.09 (3 Nov 2026, "Night V4": his MT4 run SP500_DAYTRADE v1.08 Magic 500115 layered on 500114 - net $14,896.29 (+$476.75 vs
       500114's $14,419.54), DD $2,188.15/0.22% (tighter, -$25.58), 2471 trades (+25), the 25 new legs ~68% closed in profit):
  NIGHT LEG V4  a THIRD, independent night trigger (fires only when the regular night leg AND V3 above both do NOT - the three
                never double-trade the same night): no weekday restriction, BUY at 6:01 pm New York (01:01 broker) if the broker
                day's own last-hour (15:00-16:00 NY) close was WEAK (252-day rolling percentile of the last-hour % price return
                <= 0.30 - sold off into the close) AND that same last hour's trading volume was a SHORT-TERM SPIKE (z-score vs its
                own trailing 20-day average >= 2.0) - same stop (1.0 x range) and close (10:00 am New York) as the other night
                legs. Found 3 Nov 2026 free-data hunt (Round 30, S&P chat), MT4-confirmed same day. HONEST CAVEATS carried into
                the live card: only 25 historical occurrences behind this number, 91-92% already overlap the VIX stress-night
                gate above (so mostly a refinement on an already-trading population, not an independent new trigger), and 2022 was
                a loss year inside the sample - treat as a watch item still proving itself, not a settled edge.
                Source for lh_pct: a static seed from the MT4 backtest's own last-hour-return history (RoboForex, Sep 2019 on,
                docs/sp_lh_seed.json, committed once) extended day by day with the dashboard's own Capital.com minute closes.
                Source for lhvol_z: the dashboard's own Capital.com lastTradedVolume ONLY (not seeded - Capital.com's volume count
                is on a different scale to the RoboForex data the backtest used, so mixing them into one 20-day rolling z-score
                would be invalid) - needs ~2-4 weeks of live data to accumulate the 10-day minimum before it can fire at all; by
                design, not a bug. See lh_today() in sp_run.py.
v1.10 (3 Nov 2026, "Night V5": his MT4 run SP500_DAYTRADE v1.10 Magic 500116 layered on 500115 - net $15,298.06 (+$401.77 vs
       500115's $14,896.29), DD $2,188.15/0.22% (unchanged), 2489 trades (+18), the 18 new legs alone ~72% closed in profit):
  NIGHT LEG V5  a FOURTH, independent night trigger (fires only when the three night triggers above do NOT - the four
                never double-trade the same night): no weekday restriction, BUY at 6:01 pm New York (01:01 broker) if the US
                Dollar Index weakened over the prior 5 trading days (252-day rolling percentile of the 5-day % change <= 0.20)
                AND the market narrowed on BOTH a 10-day and a 20-day horizon (252-day rolling percentile of the 10-day and
                20-day % change in the RSP/SPY ratio - equal-weight vs cap-weight S&P 500, i.e. mega-caps leading - both
                <= 0.20) - same stop (1.0 x range) and close (10:00 am New York) as the other night legs. Found 3 Nov 2026
                systematic triple-interaction hunt (Rounds 46-47, S&P chat), MT4-confirmed same day. HONEST CAVEATS carried
                into the live card: only 20 historical Python occurrences (18 confirmed in MT4 after excluding nights V2/V3/V4
                already took), thin like Night V4's sample but a cleaner independence profile (70% VIX-gate overlap vs V4's
                91-92%, 0 loss years across 6 calendar years, survives a stricter trim-robustness check than any earlier leg) -
                still a watch item, not a settled edge. Source for dxy_chg5_pct/rs_chg10_pct/rs_chg20_pct: Yahoo Finance daily
                closes (DX-Y.NYB, RSP, SPY - free), cached/refreshed once a day, available from day one (unlike Night V4's
                volume feature, no live warm-up needed) - see dxyrs_today() in sp_run.py.
v1.11 (4 Nov 2026, "Night V6": his MT4 run SP500_DAYTRADE v1.11 Magic 500117 layered on 500116 - net $15,376.13 (+$436.68 vs
       500116's $14,939.45), DD unchanged $2,188.15/0.22%, 2503 trades (+14, OP_BUY only), the 14 new legs alone ~79% closed
       in profit, matching the Python hardening estimate almost exactly):
  NIGHT LEG V6  a FIFTH, independent night trigger (fires only when the four night triggers above do NOT - the five
                never double-trade the same night): no weekday restriction, BUY at 6:01 pm New York (01:01 broker) if the
                broad trade-weighted US Dollar index was broadly weak (252-day rolling percentile of its LEVEL, 26-currency
                FRED basket - wider than DXY's 6 - <= 0.15) AND the pan-European STOXX50E index had a shock move the prior
                session (252-day rolling percentile of its |daily % close move| >= 0.85) - same stop (1.0 x range) and close
                (10:00 am New York) as the other night legs. Found 4 Nov 2026 systematic pairwise hunt over 13 fresh-sourced
                features (Round 56, S&P chat), hardened with the same threshold-neighbourhood + lag-sweep stress test that
                validated Night V5 (whole neighbourhood stays positive, lag-sweep shows the exact V5 signature: same-day dead,
                this 1-day lag a strong pass, one extra day decaying), MT4-confirmed same day. HONEST CAVEATS carried into the
                live card: only 24 historical Python occurrences (14 confirmed in MT4 after excluding nights V2-V5 already
                took), long-only (no short leg tested), moderate date clustering (a 5-night cluster in Apr-May 2026) - treat
                as a watch item still proving itself, not a settled edge. Source for dtwex_lvl_pct/stoxx_shock_pct: FRED
                DTWEXBGS (broad dollar index, free, no key needed) + Yahoo Finance ^STOXX50E daily closes, cached/refreshed
                once a day, available from day one (no live warm-up needed) - see dtwexstoxx_today() in sp_run.py.
v1.12 (4 Nov 2026, "Night V7": his MT4 run SP500_DAYTRADE v1.12 Magic 500119 layered on 500117 - net $16,133.31 (+$757.18 vs
       500117's $15,376.13), DD $2,155.51/0.21% (DOWN, not just unchanged - the first leg where DD actually falls), 2581
       trades (+78, all long - confirmed byte-for-byte to the predicted calendar dates after a recompile fix), 63.16%
       of the 78 new legs closed in profit (48W/28L - a bit below the Python 68.8% estimate, flagged honestly)):
  NIGHT LEG V7  a SIXTH, independent night trigger (fires only when the five night triggers above do NOT - the six
                never double-trade the same night): no weekday restriction, BUY at 6:01 pm New York (01:01 broker) if
                the materials sector (XLB) was relatively WEAK vs SPY (252-day rolling percentile of the XLB/SPY ratio
                LEVEL <= 0.30) AND the communications-services sector (XLC, mega-cap/growth-heavy) was RALLYING sharply
                vs SPY (252-day rolling percentile of the 10-day % change in the XLC/SPY ratio >= 0.85) at once - a
                sector-rotation-into-growth signal - same stop (1.0 x range) and close (10:00 am New York) as the
                other night legs. Found 4 Nov 2026 full 11-GICS-sector grid hunt (Round 58, S&P chat) - the BIGGEST
                Python sample of any night trigger this project (n=93), hardened the same way as V5/V6 (threshold
                neighbourhood, outlier/clustering checks, not VIX-in-disguise: corr with vix_pct ~0), MT4-confirmed
                4 Nov after an initial 0-trade MT4 run traced to a stale/uncompiled .ex4 on his side, not a code bug -
                fixed by a fresh recompile. HONEST CAVEATS carried into the live card: live win rate (63.16%) ran a
                touch below the Python hardening estimate (68.8%), moderate date clustering (a 15-night May 2020
                episode and a 12-night Sep 2025 episode) - treat as a watch item still proving itself, not a settled
                edge. Source for mt_lvl_pct/cm_chg10_pct: Yahoo Finance daily closes (XLB, XLC, SPY - free), cached/
                refreshed once a day, available from day one (no live warm-up needed) - see mt_cm_today() in sp_run.py.
v1.13 (5 Nov 2026, "Night V8": his MT4 run SP500_DAYTRADE v1.13 Magic 500121 layered on 500119 - net $16,213.81 (+$80.50 vs
       500119's $16,133.31), DD $2,122.32/0.21% (down slightly), 2621 trades (+40, all long - confirmed exact 40/40
       date+profit reconciliation, no lot-rounding gap), 60.0% of the 40 new legs closed in profit (24W/16L - a bit
       below the Python 68.6% estimate, flagged honestly - thinner edge than any prior leg)):
  NIGHT LEG V8  a SEVENTH, independent night trigger (fires only when the six night triggers above do NOT - the seven
                never double-trade the same night): no weekday restriction, BUY at 6:01 pm New York (01:01 broker) if
                credit markets were quietly de-risking (252-day rolling percentile of the 10-day % change in the
                HYG/LQD ratio - junk bonds underperforming investment-grade bonds - <= 0.15) AND the industrials
                sector (XLI) was relatively weak vs SPY (252-day rolling percentile of the 10-day % change in the
                XLI/SPY ratio <= 0.30) at once - a credit-quality risk-appetite signal, the first time corporate
                credit spreads/bond-ETF ratios have been tested in this project (every prior leg used equity-only or
                macro-only features) - same stop (1.0 x range) and close (10:00 am New York) as the other night legs.
                Found 4 Nov 2026 credit-quality risk-appetite hunt (Round 59, S&P chat), hardened the same way as
                V5-V7 (threshold neighbourhood, outlier/clustering+episode-exclusion checks, not VIX-in-disguise: corr
                with vix_pct only +0.165), MT4-confirmed 5 Nov with an exact 40/40 date+profit reconciliation (no
                lot-rounding gap, cleaner check than V7's original one). HONEST CAVEATS carried into the live card:
                the THINNEST edge of any leg built so far ($2.01/trade avg vs V7's far larger $9.71/trade), live win
                rate (60.0%) ran 8.6pp below the Python hardening estimate (68.6%, the widest gap of any leg) - treat
                as a genuine WATCH ITEM, more so than any prior leg, not a settled edge. Source for cq_chg10_pct/
                in_chg10_pct: Yahoo Finance daily closes (HYG, LQD, XLI, SPY - free), cached/refreshed once a day,
                available from day one (no live warm-up needed) - see cq_in_today() in sp_run.py.
Results: points per leg after a 0.8 pt cost (never less than Capital.com's live spread)."""
import numpy as np, pandas as pd

SM = 0.75; LEGS = 3; MOM_K = 0.05; SWEEP_X = 0.1; SWEEP_W = 30; K4_X = 0.8
X_MIN = 22 * 60 + 30; LAST_MIN = X_MIN - 5; US_LO = 16 * 60 + 30; US_HI = 22 * 60; END_H = 19
COST = 0.8
LATE_MIN = 18 * 60; GREEN_R = 0.5                                     # v1.04 day rules (rows 17 / 16 of the EA)
NIGHT_IN = 61; NIGHT_OUT = 17 * 60; NIGHT_SM = 1.0                    # v1.04 night leg entry/exit; stop mult 1.0x range from v1.07 row19 (was 2.0x)
NIGHT_DOW_MAX = 2                                                     # v1.07 row18: night leg only broker-day Mon(0)/Tue(1)/Wed(2)
V3_DOW = (2, 3, 4)                                                    # v1.08 Night V3: only broker-day Wed(2)/Thu(3)/Fri(4)
V3_LAG_DAYS = 2                                                       # commodity close used is exactly 2 calendar days before the broker day
V3_COMBO_MIN = 0.70                                                   # min(gold_pct, wti_pct) threshold (MT4-confirmed at this value, Magic 500114)
TOM_IN = 16 * 60 + 30; TOM_DECIDE = 17 * 60; TOM_SM = 0.75            # v1.07 row20: Turn-of-Month day leg (entry price marker 16:30;
                                                                       # opened only once no other S&P leg has fired by 17:00 broker, so it never stacks with an early day/night leg)
V4_LH_MAX = 0.30; V4_VOLZ_MIN = 2.00                                  # v1.09 Night V4: weak-close percentile (<=) / volume z-score (>=) thresholds
V5_DXY_MAX = 0.20; V5_RS10_MAX = 0.20; V5_RS20_MAX = 0.20             # v1.10 Night V5: dollar-weakening 5d / breadth-narrowing 10d AND 20d thresholds (all <=)
V6_DTWEX_MAX = 0.15; V6_STOXX_MIN = 0.85                              # v1.11 Night V6: broad-dollar-basket-weak (level, <=) / Europe-shock (|move|, >=) thresholds
V7_MT_MAX = 0.30; V7_CM_MIN = 0.85                                    # v1.12 Night V7: materials-weak (level, <=) / communications-rally (10d change, >=) thresholds
V8_CQ_MAX = 0.15; V8_IN_MAX = 0.30                                    # v1.13 Night V8: credit-de-risking (HYG/LQD 10d change, <=) / industrials-weak (XLI/SPY 10d change, <=) thresholds

def eod_minutes(day): return 22 * 60 + 50 if pd.Timestamp(day).dayofweek == 4 else 23 * 60

def day_ctx(hist, day):
    """hist: minute bars (index broker time, o h l c) BEFORE `day`. Returns (A, prev high, prev low) like the research base:
    A = mean high-low of the 14 previous broker days (weekdays with bars)."""
    h = hist[hist.index < day]; h = h[h.index.dayofweek < 5]
    g = h.groupby(h.index.normalize()); hi = g.h.max(); lo = g.l.min()
    rng = (hi - lo).iloc[-14:]
    if len(rng) < 14: return np.nan, np.nan, np.nan
    return float(rng.mean()), float(hi.iloc[-1]), float(lo.iloc[-1])

def _first_bar(hm, minute):
    p = int(np.searchsorted(hm, minute)); return p if p < len(hm) else -1
def _exact(hm, minute):
    p = int(np.searchsorted(hm, minute)); return p if p < len(hm) and hm[p] == minute else -1

def book_events(b, A, pH, pL):
    """S&P book events of one day. b: today's bars. Returns list of (entry_index, side, name)."""
    O, H, L, C = (b[c].values.astype(float) for c in 'ohlc'); hm = (b.index.hour * 60 + b.index.minute).values; n = len(O); E = []
    if n == 0 or not np.isfinite(A): return E
    i0, i1 = _exact(hm, 960), _exact(hm, 1000)                                   # 16:00 and 16:40 bars
    ref = O[i0] if i0 >= 0 else None
    if ref is None:                                                              # no 16:00 bar: the research's filler bar = last close before it
        p = int(np.searchsorted(hm, 960)) - 1
        if p >= 0 and hm[p] >= 960 - 90: ref = C[p]
    if i1 < 0:                                                                   # no 16:40 bar (no ticks): enter at the first bar within 5 min after
        p = int(np.searchsorted(hm, 1000))
        if p < n and hm[p] <= 1005: i1 = p
    if ref is not None and i1 >= 0:
        mv = O[i1] - ref
        if mv != 0 and abs(mv) > MOM_K * A: E.append((i1, int(np.sign(mv)), 'S&P 9:40 am New York opening move'))
    for tb, lab in ((9, '10am'), (13, '2pm')):                                   # yesterday high/low sweep -> reverse
        i = _first_bar(hm, tb * 60)
        if i < 0 or not np.isfinite(pH): continue
        ie = _first_bar(hm, END_H * 60); ie = n if ie < 0 else ie
        up, dn = pH + SWEEP_X * A, pL - SWEEP_X * A; j = -1; sd = 0
        for q in range(i, ie):
            hu, hd = H[q] >= up, L[q] <= dn
            if hu and hd: j = q; sd = 0; break
            if hu: j = q; sd = 1; break
            if hd: j = q; sd = -1; break
        if j < 0 or sd == 0: continue
        lvl = pH if sd > 0 else pL
        for jj in range(j + 1, min(j + SWEEP_W, ie)):
            if (sd > 0 and C[jj] < lvl) or (sd < 0 and C[jj] > lvl):
                if jj + 1 < n: E.append((jj + 1, -sd, f'S&P yesterday {"high" if sd > 0 else "low"} swept ({lab} scan), back inside -> reverse'))
                break
    i = _first_bar(hm, 17 * 60)
    if i >= 0 and abs(O[i] - O[0]) >= K4_X * A and i + 1 < n:                   # day move since the open at 17:00 -> follow (twice, as tested)
        s = int(np.sign(O[i] - O[0]))
        E.append((i + 1, s, 'S&P big day move by 10 am New York -> follow')); E.append((i + 1, s, 'S&P big day move by 10 am New York -> follow (2nd leg)'))
    return E

def nasdaq_events(b, picks):
    """picks: [(nasdaq minute Timestamp, side), ...] -> S&P entry at the NEXT minute (must exist), US hours only."""
    idx = b.index; hm = (idx.hour * 60 + idx.minute).values; E = []
    for t, s in picks:
        p = int(idx.searchsorted(pd.Timestamp(t) + pd.Timedelta(minutes=1)))
        if p < len(idx) and idx[p] == pd.Timestamp(t) + pd.Timedelta(minutes=1) and US_LO <= hm[p] < US_HI:
            E.append((p, int(s), 'Nasdaq signal copied'))
    return E

def legs_of_day(b, A, pH, pL, picks, day, day_done=True, sp=COST, late_min=LATE_MIN, green_r=GREEN_R):
    """The day's ladder: list of dict(j, dir, src, name, leg). day_done=False (live, 22 Oct fix): until a bar at/after the close time
    exists, the latest closed bar is not the day-end bar (a signal on it is no longer held back a minute). Full days: unchanged."""
    hm = (b.index.hour * 60 + b.index.minute).values; n = len(b)
    eodm = eod_minutes(day); eod_i = _first_bar(hm, eodm); eod_i = (n - 1 if day_done else n) if eod_i < 0 else eod_i
    O, H, L = (b[c].values.astype(float) for c in 'ohl'); sd = SM * A
    ev = [(j, s, 1, nm) for j, s, nm in book_events(b, A, pH, pL)] + [(j, s, 0, nm) for j, s, nm in nasdaq_events(b, picks)]
    ev.sort(key=lambda x: (x[0], x[1], x[2]))
    out = []; side = 0
    for j, s, src, nm in ev:
        if j >= eod_i or hm[j] >= LAST_MIN: continue
        if side == 0: side = s
        if s != side or len(out) >= LEGS: continue
        if out and late_min is not None and hm[j] >= late_min: continue          # v1.04 row 17: no 2nd/3rd leg from 11:00 am New York
        if out and green_r is not None and day_green(O, H, L, out, j, sd, sp) >= green_r: continue   # v1.04 row 16: day already up >= 0.5 x stop
        out.append(dict(j=j, dir=s, src=src, name=nm, leg=len(out) + 1))
    return out

def day_green(O, H, L, legs, j, sd, sp):
    """v1.04: the day's legs so far, in units of the stop after cost, at the open of bar j (closed legs at -1 if stopped, open at O[j])."""
    tot = 0.0
    for g in legs:
        gj, gs = g['j'], g['dir']; en = float(g.get('entry', O[gj])); stp = en - gs * sd
        hit = (L[gj:j] <= stp).any() if gs > 0 else (H[gj:j] >= stp).any()
        tot += (-1.0 - sp / sd) if hit else (gs * (O[j] - en) - sp) / sd
    return tot

def stress_flag(V, day):
    """V: DataFrame (index date) with vix, v3m, vvix closes. High-fear = last close BEFORE the broker day `day`: VIX > VIX3M,
    or VIX 1-year pct > 0.9, or VVIX 1-year pct > 0.9 (252-day rank, >= 120 days). Returns (flag, detail dict)."""
    V = V.sort_index(); V = V[~V.index.duplicated(keep='last')]
    vp = V.vix.rolling(252, min_periods=120).rank(pct=True); vvp = V.vvix.rolling(252, min_periods=120).rank(pct=True)
    k = int(V.index.searchsorted(pd.Timestamp(day).normalize(), side='left')) - 1
    if k < 0: return False, {}
    d = dict(date=str(V.index[k].date()), vix=float(V.vix.iloc[k]), vix3m=float(V.v3m.iloc[k]), vvix=float(V.vvix.iloc[k]),
             vix_pct=float(vp.iloc[k]), vvix_pct=float(vvp.iloc[k]))
    f = bool(d['vix'] > d['vix3m'] or d['vix_pct'] > 0.9 or d['vvix_pct'] > 0.9)
    return f, d

def combo_flag(G, day):
    """v1.08 Night V3 trigger. G: DataFrame indexed by date with columns gc_pct/cl_pct (252-day rolling percentile rank of each
    commodity's |daily % close move|, Yahoo GC=F/CL=F, built by gw_today() in sp_run.py - no look-ahead, each day's own rank only
    uses closes up to and including that day). Fires only on broker-day Wed/Thu/Fri when the commodity data from exactly
    V3_LAG_DAYS (2) calendar days before `day` has min(gc_pct, cl_pct) >= V3_COMBO_MIN. Formula validated 3 Nov 2026 against the
    EA's own baked NV3P array (SP500_DAYTRADE_v107_TOM4.mq4): 1356/1382 dates match to <0.001, rest are early-window rounding."""
    d = pd.Timestamp(day).normalize()
    if d.dayofweek not in V3_DOW: return False, {}
    if G is None or not len(G): return False, {}
    k = d - pd.Timedelta(days=V3_LAG_DAYS)
    if k not in G.index: return False, {}
    row = G.loc[k]
    if not (np.isfinite(row.gc_pct) and np.isfinite(row.cl_pct)): return False, {}
    combo = float(min(row.gc_pct, row.cl_pct))
    dd = dict(date=str(k.date()), gc_pct=float(row.gc_pct), cl_pct=float(row.cl_pct), combo_min=combo)
    return bool(combo >= V3_COMBO_MIN), dd

def v4_flag(S, day):
    """v1.09 Night V4 trigger. S: DataFrame indexed by date (built by lh_today() in sp_run.py) with columns lh_pct (252-day
    rolling percentile of the broker day's own last-hour (15:00-16:00 NY) % price return - low = sold off into the close) and
    lhvol_z (that same last hour's traded volume, z-scored against its own trailing 20-day average). The broker day `day`'s own
    NY session closed just hours earlier at NY date = day - 1 calendar day (same relationship proven for the EA's baked NV2T/
    NV4 arrays: d = ny_date + 1), so that is the row looked up. No weekday restriction (unlike V3) - the Python research found no
    weekday pattern. Fires when lh_pct <= V4_LH_MAX and lhvol_z >= V4_VOLZ_MIN; either value missing (not enough rolling history
    yet, or no data that day) means it simply never fires that night."""
    d = pd.Timestamp(day).normalize(); k = d - pd.Timedelta(days=1)
    if S is None or not len(S) or k not in S.index: return False, {}
    row = S.loc[k]
    if not (np.isfinite(row.lh_pct) and np.isfinite(row.lhvol_z)): return False, {}
    dd = dict(date=str(k.date()), lh_pct=float(row.lh_pct), lhvol_z=float(row.lhvol_z))
    return bool(row.lh_pct <= V4_LH_MAX and row.lhvol_z >= V4_VOLZ_MIN), dd

def v5_flag(X, day):
    """v1.10 Night V5 trigger. X: DataFrame indexed by date (built by dxyrs_today() in sp_run.py) with columns dxy_chg5_pct
    (252-day rolling percentile of the 5-day % change in the US Dollar Index, DX-Y.NYB - low = dollar weakening), rs_chg10_pct
    and rs_chg20_pct (252-day rolling percentile of the 10-day and 20-day % change in the RSP/SPY ratio, equal-weight vs
    cap-weight S&P 500 - low = breadth narrowing, mega-caps leading). The broker day `day`'s own NY-date row is day - 1 calendar
    day (same relationship as V3/V4's baked arrays: d = ny_date + 1). Fires when ALL THREE are <= their threshold at once
    (dollar weakening AND breadth narrowing on both horizons - a soft-dollar, narrow-market regime, 85% of its 20 historical
    occurrences genuinely new coverage beyond V2/V3/V4). Missing values (not enough rolling history yet, or no data that day)
    mean it simply never fires that night."""
    d = pd.Timestamp(day).normalize(); k = d - pd.Timedelta(days=1)
    if X is None or not len(X) or k not in X.index: return False, {}
    row = X.loc[k]
    if not (np.isfinite(row.dxy_chg5_pct) and np.isfinite(row.rs_chg10_pct) and np.isfinite(row.rs_chg20_pct)): return False, {}
    dd = dict(date=str(k.date()), dxy_chg5_pct=float(row.dxy_chg5_pct), rs_chg10_pct=float(row.rs_chg10_pct), rs_chg20_pct=float(row.rs_chg20_pct))
    return bool(row.dxy_chg5_pct <= V5_DXY_MAX and row.rs_chg10_pct <= V5_RS10_MAX and row.rs_chg20_pct <= V5_RS20_MAX), dd

def v6_flag(Y, day):
    """v1.11 Night V6 trigger. Y: DataFrame indexed by date (built by dtwexstoxx_today() in sp_run.py) with columns dtwex_lvl_pct
    (252-day rolling percentile of the FRED broad trade-weighted dollar index DTWEXBGS LEVEL - 26-currency basket, wider than
    DXY's 6 - low = dollar broadly weak) and stoxx_shock_pct (252-day rolling percentile of the pan-European STOXX50E index's
    |daily % close move| - high = a European equity shock). The broker day `day`'s own NY-date row is day - 1 calendar day
    (same relationship as V4/V5's lookup: d = ny_date + 1) - confirmed the correct lag by a lag-sweep stress test (same-day
    dead, this lag a strong pass, one extra day decaying - the signature of a real short-lived regime effect, not noise).
    Fires when the dollar basket is broadly weak (dtwex_lvl_pct <= V6_DTWEX_MAX) AND Europe had a shock move
    (stoxx_shock_pct >= V6_STOXX_MIN) at once. Missing values (not enough rolling history yet, or no data that day) mean it
    simply never fires that night."""
    d = pd.Timestamp(day).normalize(); k = d - pd.Timedelta(days=1)
    if Y is None or not len(Y) or k not in Y.index: return False, {}
    row = Y.loc[k]
    if not (np.isfinite(row.dtwex_lvl_pct) and np.isfinite(row.stoxx_shock_pct)): return False, {}
    dd = dict(date=str(k.date()), dtwex_lvl_pct=float(row.dtwex_lvl_pct), stoxx_shock_pct=float(row.stoxx_shock_pct))
    return bool(row.dtwex_lvl_pct <= V6_DTWEX_MAX and row.stoxx_shock_pct >= V6_STOXX_MIN), dd

def v7_flag(Z, day):
    """v1.12 Night V7 trigger. Z: DataFrame indexed by date (built by mt_cm_today() in sp_run.py) with columns mt_lvl_pct
    (252-day rolling percentile of the materials sector ETF (XLB) relative to SPY, LEVEL - low = materials/cyclicals
    relatively weak) and cm_chg10_pct (252-day rolling percentile of the 10-day % change in the communications-services
    sector ETF (XLC) relative to SPY - high = communications rallying sharply, a mega-cap/growth-heavy sector). The
    broker day `day`'s own NY-date row is day - 1 calendar day (same lag relationship as V4/V5/V6's lookup: d = ny_date
    + 1). Fires when materials are weak (mt_lvl_pct <= V7_MT_MAX) AND communications are rallying (cm_chg10_pct >=
    V7_CM_MIN) at once - a sector-rotation-into-growth signal, the biggest Python sample (n=93) of any night trigger
    found this project. Missing values (not enough rolling history yet, or no data that day) mean it simply never
    fires that night."""
    d = pd.Timestamp(day).normalize(); k = d - pd.Timedelta(days=1)
    if Z is None or not len(Z) or k not in Z.index: return False, {}
    row = Z.loc[k]
    if not (np.isfinite(row.mt_lvl_pct) and np.isfinite(row.cm_chg10_pct)): return False, {}
    dd = dict(date=str(k.date()), mt_lvl_pct=float(row.mt_lvl_pct), cm_chg10_pct=float(row.cm_chg10_pct))
    return bool(row.mt_lvl_pct <= V7_MT_MAX and row.cm_chg10_pct >= V7_CM_MIN), dd

def v8_flag(W, day):
    """v1.13 Night V8 trigger. W: DataFrame indexed by date (built by cq_in_today() in sp_run.py) with columns cq_chg10_pct
    (252-day rolling percentile of the 10-day % change in the HYG/LQD ratio - junk bonds vs investment-grade bonds - low =
    credit markets quietly de-risking) and in_chg10_pct (252-day rolling percentile of the 10-day % change in the XLI/SPY
    ratio - low = industrials/cyclicals relatively weak). The broker day `day`'s own NY-date row is day - 1 calendar day
    (same lag relationship as V4-V7's lookup: d = ny_date + 1). Fires when credit is de-risking (cq_chg10_pct <= V8_CQ_MAX)
    AND industrials are weak (in_chg10_pct <= V8_IN_MAX) at once - a credit-quality risk-appetite signal, the first time
    corporate credit spreads/bond-ETF ratios have been tested in this project (every prior leg used equity-only or
    macro-only features). Missing values (not enough rolling history yet, or no data that day) mean it simply never
    fires that night."""
    d = pd.Timestamp(day).normalize(); k = d - pd.Timedelta(days=1)
    if W is None or not len(W) or k not in W.index: return False, {}
    row = W.loc[k]
    if not (np.isfinite(row.cq_chg10_pct) and np.isfinite(row.in_chg10_pct)): return False, {}
    dd = dict(date=str(k.date()), cq_chg10_pct=float(row.cq_chg10_pct), in_chg10_pct=float(row.in_chg10_pct))
    return bool(row.cq_chg10_pct <= V8_CQ_MAX and row.in_chg10_pct <= V8_IN_MAX), dd

def night_leg(b, A, day, sp=COST, entry_min=NIGHT_IN, exit_min=NIGHT_OUT, now_done=False,
              name='Night long (high-fear night: VIX / VVIX)', src=1):
    """v1.04 night leg (call only on high-fear days, or - v1.08, name/src overridden - on a Night V3 gold+WTI combo night): BUY at
    the first bar at/after 01:01 broker (within 5 min), stop 2.0 x range (v1.07: 1.0x, NIGHT_SM), exit at the open of the first bar
    at/after 17:00 broker. Returns [] or [managed leg dict] (same keys as manage, night=True)."""
    if not len(b) or not np.isfinite(A): return []
    O, H, L, C = (b[c].values.astype(float) for c in 'ohlc'); hm = (b.index.hour * 60 + b.index.minute).values; n = len(O)
    j = _first_bar(hm, entry_min)
    if j < 0 or hm[j] > entry_min + 5 or hm[j] >= exit_min: return []
    en = O[j]; sd = NIGHT_SM * A; stp = en - sd; st = 'open'; ex = None; ext = None
    for m in range(j, n):
        if m > j and hm[m] >= exit_min: st, ex, ext = 'eod', O[m], m; break
        if L[m] <= stp: st, ex, ext = 'stopped', stp, m; break
    if st == 'open' and now_done: st, ex, ext = 'eod', C[n - 1], n - 1
    pts = None if ex is None else (ex - en) - sp
    return [dict(j=j, dir=1, src=src, name=name, leg=0, night=True, t=b.index[j], entry=float(en), stop=float(stp),
                 stop0=float(stp), sd=float(sd), A=float(A), status=st, exit=None if ex is None else float(ex), exit_t=None if ext is None else b.index[ext],
                 pts=pts, r=None if pts is None else pts / sd, r_now=((C[n - 1] - en) - sp) / sd if n else None)]

def tom_window(day):
    """v1.07 row20: True if `day` (a weekday) is the last broker weekday of its month, or one of the first 3 broker weekdays of its month -
    the classic turn-of-month window (Ariel 1987 / Lakonishok-Smidt 1988), applied per calendar month."""
    d = pd.Timestamp(day).normalize()
    if d.dayofweek >= 5: return False
    month_start = d.replace(day=1); next_month_start = month_start + pd.offsets.MonthBegin(1)
    if d == pd.bdate_range(end=next_month_start - pd.Timedelta(days=1), periods=1)[0]: return True
    return d in pd.bdate_range(start=month_start, periods=3)

def tom_leg(b, A, day, sp=COST, entry_min=TOM_IN, exit_min=X_MIN, now_done=False):
    """v1.07 row20 Turn-of-Month day leg (call only in tom_window(day), and only once no other S&P leg has fired today by TOM_DECIDE -
    see compute() in sp_run.py): BUY at the first bar at/after 16:30 broker, stop 0.75 x 14-day range, exit at the open of the first bar
    at/after 22:30 broker (or day end). One leg per day, no half-close - same shape as night_leg()."""
    if not len(b) or not np.isfinite(A): return []
    O, H, L, C = (b[c].values.astype(float) for c in 'ohlc'); hm = (b.index.hour * 60 + b.index.minute).values; n = len(O)
    j = _first_bar(hm, entry_min)
    if j < 0: return []
    en = O[j]; sd = TOM_SM * A; stp = en - sd; st = 'open'; ex = None; ext = None
    for m in range(j, n):
        if m > j and hm[m] >= exit_min: st, ex, ext = 'eod', O[m], m; break
        if L[m] <= stp: st, ex, ext = 'stopped', stp, m; break
    if st == 'open' and now_done: st, ex, ext = 'eod', C[n - 1], n - 1
    pts = None if ex is None else (ex - en) - sp
    return [dict(j=j, dir=1, src=2, name='Turn-of-month long (last/first broker days of the month)', leg=0, night=False, tom=True, t=b.index[j],
                 entry=float(en), stop=float(stp), stop0=float(stp), sd=float(sd), A=float(A), status=st, exit=None if ex is None else float(ex),
                 exit_t=None if ext is None else b.index[ext], pts=pts, r=None if pts is None else pts / sd,
                 r_now=((C[n - 1] - en) - sp) / sd if n else None)]

def manage(b, legs, A, day, sp=COST, now_done=True):
    """Walk each leg through today's closed bars. status: open / stopped / eod. r = result in units of the stop after the cost."""
    O, H, L, C = (b[c].values.astype(float) for c in 'ohlc'); hm = (b.index.hour * 60 + b.index.minute).values; n = len(O)
    eodm = eod_minutes(day); out = []
    for g in legs:
        j, s = g['j'], g['dir']; en = float(g.get('entry', O[j])); sd = float(g.get('sd', SM * A)); stp = en - s * sd; st = 'open'; ex = None; ext = None   # frozen legs keep entry/stop
        for m in range(j, n):
            if m > j and hm[m] >= X_MIN: st, ex, ext = 'eod', O[m], m; break
            if hm[m] >= eodm and m > j: st, ex, ext = 'eod', O[m], m; break
            if s > 0 and L[m] <= stp: st, ex, ext = 'stopped', stp, m; break
            if s < 0 and H[m] >= stp: st, ex, ext = 'stopped', stp, m; break
        if st == 'open' and now_done and n: st, ex, ext = 'eod', C[n - 1], n - 1
        pts = None if ex is None else s * (ex - en) - sp
        out.append(dict(g, t=g.get('t', b.index[j]), entry=float(en), stop=float(stp), stop0=float(stp), sd=float(sd), A=float(g.get('A', A)), status=st,
                        exit=None if ex is None else float(ex), exit_t=None if ext is None else b.index[ext], pts=pts,
                        r=None if pts is None else pts / sd, r_now=(s * (C[n - 1] - en) - sp) / sd if n else None))
    return out

def run_day(hist, today, day, picks, sp=COST, day_over=False):
    """hist: bars before `day` (>= 15 days); today: today's CLOSED bars; picks: Nasdaq desk picks of `day`. Returns managed legs."""
    A, pH, pL = day_ctx(hist, day)
    if not np.isfinite(A) or not len(today): return []
    legs = legs_of_day(today, A, pH, pL, picks, day, day_done=day_over, sp=sp)
    return manage(today, legs, A, day, sp, now_done=day_over)
