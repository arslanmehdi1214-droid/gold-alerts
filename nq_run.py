"""NASDAQ 100 PAPER signals for the page - ONE version since 18 Oct 2026: US100 = simple signals (Nasdaq prices only, nq_set.json) with the
v1.02 EXITS since 19 Oct (nq_engine.manage_v102; MT4-proven on these signals' trades, his run 19 Oct; v1.01 exits from 18 Oct before that). The full version (US100F) was removed from the page
(same trades so far, worse with the v1.01 exits); its old journal docs/journal_nqf.json is left untouched.
Original note: (no phone alerts, no real money). Called by run.py after gold, USDJPY and WTI, every minute.
Replays today's Capital.com US Tech 100 minutes through the Nasdaq walk-forward set (nq_engine.py + nq_set.json = the 2026 set,
re-picked each January on all earlier years; parity with the research trades: 194 of 194 days of 2026, same minute, side and price)
and keeps a paper journal, judged after ~3 months (pass = right way first >= 52.5% and profit factor >= 1.10 after the spread).
Files: docs/nq_min/YYYY-MM.npz (finished days of minute bars, broker clock, bid; seeded from HistData to 2026-09-30, then extended with
Capital.com minutes), docs/journal_nq.json (every paper trade), docs/data.json -> markets.US100 (the page)."""
import os, glob, json, time, requests, numpy as np, pandas as pd
import feeds as F, nq_engine as N
DEADLINE = time.time() + 240          # loop.py resets this every minute; the Nasdaq part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = os.path.join(HERE, 'docs', 'nq_min'); JOUR = os.path.join(HERE, 'docs', 'journal_nq.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json'); STATE = os.path.join(HERE, 'docs', 'nq_state.json')   # data-check memory (22 Oct)
FOMC_JOUR = os.path.join(HERE, 'docs', 'journal_nq_fomc.json')   # 8 Nov: FOMC-overnight's own small journal, separate from v1.02's
CPI_JOUR = os.path.join(HERE, 'docs', 'journal_nq_cpi.json')         # 8 Nov: CPI-overnight's own small journal
TUESDAY_JOUR = os.path.join(HERE, 'docs', 'journal_nq_tuesday.json') # 8 Nov: Turnaround Tuesday's own small journal
BIGUP_JOUR = os.path.join(HERE, 'docs', 'journal_nq_bigup.json')     # 8 Nov: Big Up Continuation's own small journal
EPIC = os.environ.get('CAPITAL_EPIC_NQ', 'US100')
MIN_SPREAD = 1.8                      # 22 Oct fix: the paper levels and results use exactly 1.8 index points (as the MT4 v1.02 test);
                                      # the live Capital.com spread is shown only (spread_live)
PASS = dict(green=55.0, pf=1.10, months=3)
RULES = 'v1.02'                       # journal days are tagged; the card's record counts only the current rules (v1.01 days kept, not mixed)
BACKTEST = dict(direction='—', days='59.2% green / 94.5% traded', perday='1.29', win='66.2%', pf='1.28', net='+$126,676 at $1,000 risk per full trade',
                source='MT4 replay with the v1.02 exits (his run 19 Oct, spread 1.8 pts), 2020-01-01..2026-09-30, 2,272 trades; worst day -$2,046; net/DD 13.90')
BACKTEST_F = dict(direction='53.2%', days='97%', perday='1.33', win='—', pf='1.17', net='+10.1 pts per weekday',
                  source='Python walk-forward 2020-2026 (signals re-picked each January, never seen when picked), 1.8 pt spread; '
                         'MT4 replay of the same trades (his run): 2,308 trades, PF 1.16, net +17,109 pts')
VARIANTS = [dict(code='US100', name='Nasdaq 100', S=N.SET, jour=JOUR, stats=BACKTEST,
                 what='Tracks whether live Nasdaq signals do as well as the v1.02 backtest. Decision after about 3 months.')]
REMOVED = ['US100F']                  # cards taken off the page on 18 Oct 2026

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

# ---------------- data checks (22 Oct fix) ----------------
# Finished days: saved only when reasonably complete (>= 85% of the usual minute count for that weekday in the stored history); otherwise
# retried next run without moving on. A day is called a holiday (or a short day, saved as it is) only after 3 tries at least 30 min apart.
# Today: newest closed bar older than 3 min, or a hole of more than 3 missing minutes (during market hours) = feed error
# (the card keeps the last good update). A hole that is still there 5 min after it was first seen is taken as a hole in the source itself.
FULL_SHARE, TRIES, TRY_GAP, LATE, HOLE_OK = 0.85, 3, pd.Timedelta(minutes=30), pd.Timedelta(minutes=3), pd.Timedelta(minutes=5)
OPEN_HM = 75                          # market hours checked: 01:15 broker .. the day end (23:00, Fri 22:50)

class FeedError(RuntimeError):
    pass

def load_state(): return loadj(STATE, {})
def save_state(st): dumpj(st, STATE, indent=1)

def usual_count(hist, d):
    """usual number of minute bars of a stored day on d's weekday (median of the last 8 such days; else of the last 20 days)."""
    if hist is None or not len(hist): return None
    c = hist.groupby(hist.index.normalize()).size()
    same = c[c.index.dayofweek == d.dayofweek].iloc[-8:]
    if len(same) >= 2: return float(same.median())
    return float(c.iloc[-20:].median()) if len(c) >= 3 else None

def judge_day(st, key, n, usual, now):
    """-> 'save' (complete), 'short' (still partial after 3 tries: saved as it is), 'holiday' (< 60 bars after 3 tries) or 'wait'."""
    tries = st.setdefault('tries', {})
    if n >= (60 if usual is None else max(60, FULL_SHARE * usual)):
        tries.pop(key, None); return 'save'
    t = tries.setdefault(key, [])
    if not t or pd.Timestamp(now) - pd.Timestamp(t[-1]) >= TRY_GAP: t.append(str(now))
    if len(t) < TRIES: return 'wait'
    tries.pop(key, None)
    return 'holiday' if n < 60 else 'short'

def feed_check(b, now, eod, st, key):
    """None if today's closed bars look complete, else the reason (market hours only)."""
    hm = now.hour * 60 + now.minute
    if now >= eod or hm < OPEN_HM: return None
    if not len(b): return 'no price bars received for today'
    age = now - (b.index[-1] + pd.Timedelta(minutes=1))
    if age > LATE: return f'newest closed price bar ({dubai(b.index[-1])} Dubai) is {age.total_seconds() / 60:.0f} min old'
    w = b.index                                          # holes anywhere today (a missing 900-minute chunk too), not only the last hour
    gaps = [(a, c) for a, c in zip(w[:-1], w[1:]) if c - a - pd.Timedelta(minutes=1) > LATE]
    st0 = now.normalize() + pd.Timedelta(minutes=OPEN_HM)
    if w[0] > st0: gaps = [(st0, w[0])] + gaps             # first bar of the day missing
    day = str(now.normalize().date()); seen = st.setdefault('holes', {}).setdefault(key, {})
    for k in [k for k in seen if not k.startswith(day)]: seen.pop(k)
    bad = []
    for a, c in gaps:
        k = str(a); seen.setdefault(k, str(now))
        if now - pd.Timestamp(seen[k]) < HOLE_OK: bad.append(f'{dubai(a)}-{dubai(c)}')
    return f'price bars missing between {", ".join(bad)} Dubai' if bad else None

def load_hist():
    fr = []
    for f in sorted(glob.glob(os.path.join(MIN, '*.npz'))):
        z = np.load(f); fr.append(pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c']}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]'))))
    if not fr: raise RuntimeError('docs/nq_min history missing')
    return pd.concat(fr).sort_index()

def save_day(bars):
    """Add one finished broker day of minute bars to its month file."""
    per = bars.index[0].strftime('%Y-%m'); f = os.path.join(MIN, per + '.npz')
    old = load_month(f); d = pd.concat([old, bars[['o', 'h', 'l', 'c']]]) if old is not None else bars[['o', 'h', 'l', 'c']]
    d = d[~d.index.duplicated(keep='last')].sort_index()
    tmp = f + '.part'
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, t=d.index.values.astype('datetime64[m]').astype(np.int64), o=d.o.values, h=d.h.values, l=d.l.values, c=d.c.values)
    os.replace(tmp, f)
def load_month(f):
    if not os.path.exists(f): return None
    z = np.load(f); return pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c']}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]')))

EPIC_NOW = [EPIC]; _TRIED = [False]
def find_epic(feed):
    """Look up the US Tech 100 epic in Capital.com's market list (used only if the default name is refused)."""
    r = requests.get(f'{feed.base}/api/v1/markets', headers=feed.h, timeout=20, params={'searchTerm': 'US Tech 100'})
    r.raise_for_status()
    for mkt in r.json().get('markets', []):
        if 'tech 100' in str(mkt.get('instrumentName', '')).lower() and 'future' not in str(mkt.get('instrumentName', '')).lower():
            EPIC_NOW[0] = mkt['epic']; print('Nasdaq epic found:', EPIC_NOW[0]); return
    raise RuntimeError('US Tech 100 not found in Capital.com markets - set CAPITAL_EPIC_NQ')

def minutes(feed, start_b, end_b):
    """Capital.com US Tech 100 minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('Nasdaq time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC_NOW[0]}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code == 404 and 'epic' in r.text.lower() and not _TRIED[0]:
            _TRIED[0] = True; find_epic(feed); continue                  # wrong epic name: look it up once, then retry
        elif r.status_code not in (400, 404):
            r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def catch_up(feed, hist, day, get=None, now=None, st=None):
    """Add every finished weekday after the last stored day and before `day` (Capital.com minutes), only when complete (judge_day).
    Returns (added, pending): pending = the day still being retried (nothing after it is added yet)."""
    get = get or minutes; now = now or F.broker_now(); st = {} if st is None else st
    last = hist.index[-1].normalize(); added = []; hol = st.setdefault('holidays', [])
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1)
        if nxt.dayofweek < 5 and str(nxt.date()) not in hol:
            b = get(feed, nxt, nxt + pd.Timedelta(days=1)); b = b[(b.index >= nxt) & (b.index < nxt + pd.Timedelta(days=1))]
            u = usual_count(hist.iloc[-60 * 1500:], nxt); v = judge_day(st, str(nxt.date()), len(b), u, now)
            if v in ('save', 'short'):
                save_day(b); hist = pd.concat([hist, b[['o', 'h', 'l', 'c']]]); added.append(str(nxt.date()) + (' (short day)' if v == 'short' else ''))
            elif v == 'holiday': hol.append(str(nxt.date())); added.append(str(nxt.date()) + ' (no prices - holiday)')
            else: return added, [f'{nxt.date()}: {len(b)} of ~{u or 60:.0f} minute bars so far - retrying']
        last = nxt
    hol[:] = [h for h in hol if h >= str((day - pd.Timedelta(days=90)).date())]
    return added, []

def rwf(b, j, d, px, A):
    """Right way first: +0.3 x range before -0.3 x range, until the day end (None = not decided yet / never)."""
    a = 0.3 * A
    for k in range(j + 1, len(b)):
        up = (b.h.values[k] - px) if d > 0 else (px - b.l.values[k]); dn = (px - b.l.values[k]) if d > 0 else (b.h.values[k] - px)
        if up >= a and dn >= a: return None
        if up >= a: return 1
        if dn >= a: return 0
    return None

def row(t, b, now, eod, spread):
    """One trade for the page. res = index points of the WHOLE trade at its size (sells 1/3, the part close included), after the 1.8 pt spread.
    spread = today's live median spread (shown only, 22 Oct fix)."""
    st = t['status']; sp = MIN_SPREAD; pt = t.get('part', N.V101['part'])
    part_pts = pt * t['dir'] * (t['half_px'] - t['entry']) if t['half'] else 0.0; rem = 1 - pt if t['half'] else 1.0
    if st == 'open' and now >= eod and len(b):                  # day over without a close-time bar: close at the last price
        ex = float(b.c.values[-1]) + (0 if t['dir'] > 0 else sp)
        t = dict(t, status='eod', exit=ex, exit_t=b.index[-1], pts=t['w'] * (part_pts + rem * t['dir'] * (ex - t['entry']))); st = 'eod'
    res = None if t['pts'] is None else round(t['pts'], 1)
    j = int(np.searchsorted(b.index.values, np.datetime64(t['t'])))
    live = None
    if st == 'open' and len(b):
        pxn = float(b.c.values[-1]) + (0 if t['dir'] > 0 else sp); live = round(t['w'] * (part_pts + rem * t['dir'] * (pxn - t['entry'])), 1)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], role=t['role'], price=round(t['px'], 1), entry=round(t['entry'], 1),
                stop=round(t['stop'], 1), stop0=round(t['stop0'], 1), stop_pts=round(t['sd'], 1), half_px=round(t['half_px'], 1), half=bool(t['half']),
                half_time=None if t['half_t'] is None else dubai(t['half_t']), size=t['size'], status=st, part=round(pt, 2),
                trail_pts=round(N.V102['trail'] * t['A'], 1),
                exit=None if t['exit'] is None else round(t['exit'], 1), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=res, r=None if t['r'] is None else round(t['r'], 3), r_sized=None if t['r'] is None else round(t['r'] * t['w'], 3),
                live=live, rwf=rwf(b, j, t['dir'], t['px'], t['A']), spread=round(sp, 2), spread_live=None if spread is None else round(spread, 2))

def summary(J, day=None):
    """Paper record of the CURRENT rules only (v1.02 days); older days (12-16 Oct old exits, 19 Oct v1.01) stay in the journal but are not mixed in."""
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    J = dict(start=D3[0]['date'], days=D3)
    allt = [t for d in J.get('days', []) for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]; rr = [t['res'] for t in allt if t.get('res') is not None]
    end = str((day or pd.Timestamp(J['days'][-1]['date'])).date()) if J.get('days') else J['start']
    wd = max(1, len(pd.bdate_range(J['start'], end))); tdays = sum(1 for d in J['days'] if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), decided=len(dec),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES,
                green=round(100 * sum(1 for d in J['days'] if sum(t.get('res') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

# ---------------- FOMC-overnight (8 Nov 2026 port) ----------------
# Its own low-frequency signal (~8x/year), kept entirely separate from v1.02: own journal file (FOMC_JOUR), own
# entry/exit check (nq_engine.fomc_r/fomc_check_exit), never touches journal_nq.json's RULES='v1.02' days or the
# card's pass-bar summary. Shown as mk['US100']['fomc'] alongside the existing card, not merged into entries[].
def fomc_run(hist, day, now, b, spread_live):
    """Check/advance the FOMC-overnight position (if any) and look for a new entry; returns the small journal dict."""
    J = loadj(FOMC_JOUR, dict(open=None, closed=[])); changed = False
    allm = pd.concat([hist[hist.index < day], b]) if len(b) else hist[hist.index < day]
    if J['open']:
        o = J['open']
        status, ex, ext = N.fomc_check_exit(allm, o['entry_time'], o['entry'], o['sl'], o['tp'], o['decision_date'], now)
        if status == 'open':
            o['live'] = None if not len(allm) else round(float(allm.c.iloc[-1]) - o['entry'], 1)
        else:
            closed = dict(o, status=status, exit=round(ex, 1), exit_time=str(ext), pts=round(ex - o['entry'], 1))
            J['closed'] = ([closed] + J['closed'])[:20]; J['open'] = None; changed = True
    elif now >= day + pd.Timedelta(minutes=N.eod_minutes(day)):           # only once today's own EOD bar has actually printed
        emap = N.fomc_entry_map(); key = str(day.date())
        if key in emap and not any(c.get('entry_day') == key for c in J['closed']):
            eod_bar = b[b.index < day + pd.Timedelta(minutes=N.eod_minutes(day))]
            if len(eod_bar):
                DB = N.daily_range_atr(pd.concat([hist[hist.index < day], eod_bar]))
                R = N.fomc_r(DB, day)
                if R:
                    entry = round(float(eod_bar.c.iloc[-1]) + spread_live, 1)        # buy: pays the ask (close + spread), same as manage_v102's buy entries
                    J['open'] = dict(entry_day=key, decision_date=str(emap[key].date()), entry_time=str(eod_bar.index[-1]),
                                      entry=entry, sl=round(entry - R, 1), tp=round(entry + N.FOMC_TP_MULT * R, 1), r=R, live=0.0)
                    changed = True
    if changed: dumpj(J, FOMC_JOUR, indent=1)
    return J

def fomc_card(J):
    """None when there is nothing to show (the overwhelming majority of runs - fires ~8x/year); otherwise a small
    note for the US100 card: the open position, or today's just-closed one (so a same-day close isn't missed)."""
    o = J.get('open')
    if o:
        return dict(state='open', decision_date=o['decision_date'], entry_time=o['entry_time'], entry=o['entry'],
                     stop=o['sl'], target=o['tp'], r=o['r'], live=o.get('live'),
                     note=f"FOMC overnight: long from {o['entry_time']}, stop {o['sl']} / target {o['tp']} (R={o['r']}), "
                          f"force-closes at the {o['decision_date']} RTH open if neither hits first.")
    c = J['closed'][0] if J.get('closed') else None
    if c:
        why = {'target': 'hit target', 'stopped': 'hit stop', 'eod': 'force-closed at the RTH open'}.get(c['status'], c['status'])
        return dict(state='closed', decision_date=c['decision_date'], entry_time=c['entry_time'], entry=c['entry'],
                     exit=c['exit'], exit_time=c['exit_time'], pts=c['pts'], r=c['r'],
                     note=f"FOMC overnight ({c['decision_date']}): {why}, {c['pts']:+.1f} pts.")
    return None

# ---------------- CPI-overnight / Turnaround Tuesday / Big Up Continuation (8 Nov 2026 port) ----------------
# Same independent-additive pattern as FOMC above: each kept entirely separate from v1.02 (own journal, own
# entry/exit check, never touches journal_nq.json's RULES='v1.02' days or the card's pass-bar summary). Shown
# as mk['US100']['cpi']/['tuesday']/['bigup'] alongside the existing card, not merged into entries[].

def cpi_run(hist, day, now, b, spread_live):
    """Same exit mechanic as fomc_run (fixed future deadline = RTH open on a known release day) - reuses
    N.fomc_check_exit and N.fomc_r as-is, only the entry-day source (N.cpi_entry_map) differs."""
    J = loadj(CPI_JOUR, dict(open=None, closed=[])); changed = False
    allm = pd.concat([hist[hist.index < day], b]) if len(b) else hist[hist.index < day]
    if J['open']:
        o = J['open']
        status, ex, ext = N.fomc_check_exit(allm, o['entry_time'], o['entry'], o['sl'], o['tp'], o['decision_date'], now)
        if status == 'open':
            o['live'] = None if not len(allm) else round(float(allm.c.iloc[-1]) - o['entry'], 1)
        else:
            closed = dict(o, status=status, exit=round(ex, 1), exit_time=str(ext), pts=round(ex - o['entry'], 1))
            J['closed'] = ([closed] + J['closed'])[:20]; J['open'] = None; changed = True
    elif now >= day + pd.Timedelta(minutes=N.eod_minutes(day)):
        emap = N.cpi_entry_map(); key = str(day.date())
        if key in emap and not any(c.get('entry_day') == key for c in J['closed']):
            eod_bar = b[b.index < day + pd.Timedelta(minutes=N.eod_minutes(day))]
            if len(eod_bar):
                DB = N.daily_range_atr(pd.concat([hist[hist.index < day], eod_bar]))
                R = N.fomc_r(DB, day)
                if R:
                    entry = round(float(eod_bar.c.iloc[-1]) + spread_live, 1)
                    J['open'] = dict(entry_day=key, decision_date=str(emap[key].date()), entry_time=str(eod_bar.index[-1]),
                                      entry=entry, sl=round(entry - R, 1), tp=round(entry + N.FOMC_TP_MULT * R, 1), r=R, live=0.0)
                    changed = True
    if changed: dumpj(J, CPI_JOUR, indent=1)
    return J

def cpi_card(J):
    o = J.get('open')
    if o:
        return dict(state='open', decision_date=o['decision_date'], entry_time=o['entry_time'], entry=o['entry'],
                     stop=o['sl'], target=o['tp'], r=o['r'], live=o.get('live'),
                     note=f"CPI overnight: long from {o['entry_time']}, stop {o['sl']} / target {o['tp']} (R={o['r']}), "
                          f"force-closes at the {o['decision_date']} RTH open if neither hits first.")
    c = J['closed'][0] if J.get('closed') else None
    if c:
        why = {'target': 'hit target', 'stopped': 'hit stop', 'eod': 'force-closed at the RTH open'}.get(c['status'], c['status'])
        return dict(state='closed', decision_date=c['decision_date'], entry_time=c['entry_time'], entry=c['entry'],
                     exit=c['exit'], exit_time=c['exit_time'], pts=c['pts'], r=c['r'],
                     note=f"CPI overnight ({c['decision_date']}): {why}, {c['pts']:+.1f} pts.")
    return None

def tuesday_run(hist, day, now, b, spread_live):
    """Exit deadline is dynamic (next trading day's RTH close, not a known future date) - uses
    N.hold_day_check_exit; entry checked only on a Tuesday whose prior trading day (Monday) closed down."""
    J = loadj(TUESDAY_JOUR, dict(open=None, closed=[])); changed = False
    allm = pd.concat([hist[hist.index < day], b]) if len(b) else hist[hist.index < day]
    if J['open']:
        o = J['open']; entry_day = pd.Timestamp(o['entry_day'])
        if day > entry_day:
            status, ex, ext = N.hold_day_check_exit(allm, o['entry_time'], o['entry'], o['sl'], o['tp'], day, now)
            if status == 'open':
                o['live'] = None if not len(allm) else round(float(allm.c.iloc[-1]) - o['entry'], 1)
            else:
                closed = dict(o, status=status, exit=round(ex, 1), exit_time=str(ext), pts=round(ex - o['entry'], 1))
                J['closed'] = ([closed] + J['closed'])[:20]; J['open'] = None; changed = True
        else:
            o['live'] = None if not len(allm) else round(float(allm.c.iloc[-1]) - o['entry'], 1)
    elif now >= day + pd.Timedelta(minutes=N.eod_minutes(day)) and day >= N.TUESDAY_FROM:
        key = str(day.date())
        if not any(c.get('entry_day') == key for c in J['closed']):
            eod_bar = b[b.index < day + pd.Timedelta(minutes=N.eod_minutes(day))]
            if len(eod_bar):
                DB = N.daily_range_atr(pd.concat([hist[hist.index < day], eod_bar]))
                if N.turnaround_tuesday_signal(DB, day):
                    R = N.fomc_r(DB, day)
                    if R:
                        entry = round(float(eod_bar.c.iloc[-1]) + spread_live, 1)
                        J['open'] = dict(entry_day=key, entry_time=str(eod_bar.index[-1]), entry=entry,
                                          sl=round(entry - R, 1), tp=round(entry + N.FOMC_TP_MULT * R, 1), r=R, live=0.0)
                        changed = True
    if changed: dumpj(J, TUESDAY_JOUR, indent=1)
    return J

def tuesday_card(J):
    o = J.get('open')
    if o:
        return dict(state='open', entry_day=o['entry_day'], entry_time=o['entry_time'], entry=o['entry'],
                     stop=o['sl'], target=o['tp'], r=o['r'], live=o.get('live'),
                     note=f"Turnaround Tuesday: long from {o['entry_time']}, stop {o['sl']} / target {o['tp']} (R={o['r']}), "
                          f"force-closes at the next trading day's RTH close if neither hits first.")
    c = J['closed'][0] if J.get('closed') else None
    if c:
        why = {'target': 'hit target', 'stopped': 'hit stop', 'eod': 'force-closed at next-day close'}.get(c['status'], c['status'])
        return dict(state='closed', entry_day=c['entry_day'], entry_time=c['entry_time'], entry=c['entry'],
                     exit=c['exit'], exit_time=c['exit_time'], pts=c['pts'], r=c['r'],
                     note=f"Turnaround Tuesday ({c['entry_day']}): {why}, {c['pts']:+.1f} pts.")
    return None

def bigup_run(hist, day, now, b, spread_live):
    """Same dynamic-deadline exit as Turnaround Tuesday; entry checked every day (today's own full-day
    Close-Open > BIGUP_MULT x the raw lagged avg range)."""
    J = loadj(BIGUP_JOUR, dict(open=None, closed=[])); changed = False
    allm = pd.concat([hist[hist.index < day], b]) if len(b) else hist[hist.index < day]
    if J['open']:
        o = J['open']; entry_day = pd.Timestamp(o['entry_day'])
        if day > entry_day:
            status, ex, ext = N.hold_day_check_exit(allm, o['entry_time'], o['entry'], o['sl'], o['tp'], day, now)
            if status == 'open':
                o['live'] = None if not len(allm) else round(float(allm.c.iloc[-1]) - o['entry'], 1)
            else:
                closed = dict(o, status=status, exit=round(ex, 1), exit_time=str(ext), pts=round(ex - o['entry'], 1))
                J['closed'] = ([closed] + J['closed'])[:20]; J['open'] = None; changed = True
        else:
            o['live'] = None if not len(allm) else round(float(allm.c.iloc[-1]) - o['entry'], 1)
    elif now >= day + pd.Timedelta(minutes=N.eod_minutes(day)) and day >= N.BIGUP_FROM:
        key = str(day.date())
        if not any(c.get('entry_day') == key for c in J['closed']):
            eod_bar = b[b.index < day + pd.Timedelta(minutes=N.eod_minutes(day))]
            if len(eod_bar):
                DB = N.daily_range_atr(pd.concat([hist[hist.index < day], eod_bar]))
                if N.bigup_continuation_signal(DB, day):
                    avg = N.lagged_avg_range(DB, day)
                    R = round(N.FOMC_R_MULT * avg, 2) if avg else None
                    if R:
                        entry = round(float(eod_bar.c.iloc[-1]) + spread_live, 1)
                        J['open'] = dict(entry_day=key, entry_time=str(eod_bar.index[-1]), entry=entry,
                                          sl=round(entry - R, 1), tp=round(entry + N.FOMC_TP_MULT * R, 1), r=R, live=0.0)
                        changed = True
    if changed: dumpj(J, BIGUP_JOUR, indent=1)
    return J

def bigup_card(J):
    o = J.get('open')
    if o:
        return dict(state='open', entry_day=o['entry_day'], entry_time=o['entry_time'], entry=o['entry'],
                     stop=o['sl'], target=o['tp'], r=o['r'], live=o.get('live'),
                     note=f"Big Up Continuation: long from {o['entry_time']}, stop {o['sl']} / target {o['tp']} (R={o['r']}), "
                          f"force-closes at the next trading day's RTH close if neither hits first.")
    c = J['closed'][0] if J.get('closed') else None
    if c:
        why = {'target': 'hit target', 'stopped': 'hit stop', 'eod': 'force-closed at next-day close'}.get(c['status'], c['status'])
        return dict(state='closed', entry_day=c['entry_day'], entry_time=c['entry_time'], entry=c['entry'],
                     exit=c['exit'], exit_time=c['exit_time'], pts=c['pts'], r=c['r'],
                     note=f"Big Up Continuation ({c['entry_day']}): {why}, {c['pts']:+.1f} pts.")
    return None

def base_card(A=None, V=None):
    V = V or VARIANTS[0]
    note = ('14-day range ' + ('—' if A is None else f'{A:,.0f} pts') + ' · stop: buys 0.4 x range, sells ¼ range · sells ⅓ size · at +0.5 x risk close 25% (buys) / 15% (sells), '
            'stop to entry, then trail the rest 0.45 x range' + ('' if A is None else f' (= {0.45 * A:,.0f} pts)') + ' behind its best price · no new trades from 10:00 pm broker '
            '(Fri 8:00 pm) · day lock +3R/+1.5R · max 2 trades a day · close 11:00 pm broker (Fri 10:50 pm) = 12:00 am Dubai, 1:00 am in winter')
    return dict(code=V['code'], name=V['name'], symbol='US100 · Capital.com US Tech 100', live=False, paper=True, status='Paper', version=V['S'].get('version', ''),
                unit='pts', dp=1, stats=V['stats'], pass_bar=PASS, day_note=note,
                what_note=V['what'],
                cost_note="Results are index points for the whole trade at its v1.02 size (sells ⅓, the 25% / 15% part included), after a fixed 1.8-point spread "
                          "(as in the MT4 test; entry, stop and part levels use it too). Capital.com's live spread is shown for reference only.",
                net_label='Net points (v1.02 rules)')

def main(feed=None, get=None, now=None):
    global DEADLINE; DEADLINE = time.time() + 75     # 22 Oct fix: own 75 s time budget per market (no shared window)
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    for c in REMOVED: mk.pop(c, None)
    if now.dayofweek >= 5:
        for V in VARIANTS:
            J = loadj(V['jour'], dict(start=None, days=[])); prev = mk.get(V['code']) or {}
            mk[V['code']] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(None, V), state='closed', message='Market closed for the weekend.',
                                 entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('Nasdaq: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('Nasdaq paper needs the Capital.com prices')
        feed = F.Capital()
    hist = load_hist(); st = load_state()
    added, pend = catch_up(feed, hist, day, get, now, st); save_state(st)
    if pend: raise FeedError('minute history not complete yet (' + '; '.join(pend) + ')')
    if added: hist = load_hist()
    fin = finish_old_days(hist, day, st)
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]      # today's closed minute bars only
    eod = day + pd.Timedelta(minutes=N.eod_minutes(day))
    bad = feed_check(b, now, eod, st, 'US100'); save_state(st)
    if bad: raise FeedError(bad)
    allm = pd.concat([hist[hist.index < day].iloc[-N.KEEP_DAYS * 1500:], b[['o', 'h', 'l', 'c']]])
    spread = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else None
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()   # 5-min candles for the page: [time, close, open, high, low]
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 1), round(float(r.o), 1), round(float(r.h), 1), round(float(r.l), 1)] for t, r in g5.iterrows()]
    errs = []
    for V in VARIANTS:                                   # each version on its own: one failing never stops the other
        try:
            mk[V['code']] = variant(V, allm, b, day, now, eod, spread, last, first, spark, hist, added + [f'finished {x}' for x in fin])
        except Exception as e:
            errs.append((V, e))
    for V, e in errs: mark_failed(mk, V, e)
    try:                                           # FOMC-overnight (8 Nov): its own check, never allowed to break the v1.02 card above
        if 'US100' in mk: mk['US100']['fomc'] = fomc_card(fomc_run(hist, day, now, b, MIN_SPREAD))
    except Exception as e:
        print('Nasdaq FOMC-overnight check failed (non-fatal):', type(e).__name__, str(e)[:160])
    try:                                           # CPI-overnight (8 Nov): same non-fatal isolation
        if 'US100' in mk: mk['US100']['cpi'] = cpi_card(cpi_run(hist, day, now, b, MIN_SPREAD))
    except Exception as e:
        print('Nasdaq CPI-overnight check failed (non-fatal):', type(e).__name__, str(e)[:160])
    try:                                           # Turnaround Tuesday (8 Nov): same non-fatal isolation
        if 'US100' in mk: mk['US100']['tuesday'] = tuesday_card(tuesday_run(hist, day, now, b, MIN_SPREAD))
    except Exception as e:
        print('Nasdaq Turnaround-Tuesday check failed (non-fatal):', type(e).__name__, str(e)[:160])
    try:                                           # Big Up Continuation (8 Nov): same non-fatal isolation
        if 'US100' in mk: mk['US100']['bigup'] = bigup_card(bigup_run(hist, day, now, b, MIN_SPREAD))
    except Exception as e:
        print('Nasdaq BigUp-Continuation check failed (non-fatal):', type(e).__name__, str(e)[:160])
    dumpj(old, PORTAL, indent=1)
    print(f'Nasdaq paper: {now} broker | bars {len(b)} | history to {hist.index[-1].date()} | added {added} | finished {fin} | failed {[V["code"] for V, _ in errs]}')

def finish_old_days(hist, day, st):
    """22 Oct fix: a journal day left non-final (the desk stopped before its close) is re-run on its stored full day and closed."""
    done = []
    for V in VARIANTS:
        J = loadj(V['jour'], dict(start=None, days=[])); ch = False
        for jd in J.get('days', []):
            if jd.get('final') or jd.get('rules') != RULES or jd['date'] >= str(day.date()): continue
            d = pd.Timestamp(jd['date']); nd = d + pd.Timedelta(days=1)
            if jd['date'] in st.get('holidays', []): jd['final'] = True; ch = True; done.append(jd['date']); continue
            b = hist[(hist.index >= d) & (hist.index < nd)]
            if not len(b) or d < day - pd.Timedelta(days=10): continue        # not stored yet (catch-up retries) / too old to redo
            allm = pd.concat([hist[hist.index < d].iloc[-N.KEEP_DAYS * 1500:], b])
            trades = N.run_day(allm, d, nd, S=V['S'], exits=RULES, sp=MIN_SPREAD)
            rows = [row(t, b, nd, d + pd.Timedelta(minutes=N.eod_minutes(d)), None) for t in trades]
            jd.update(trades=rows, side=(rows[0]['side'] if rows else None), final=True, finished_late=True); ch = True; done.append(jd['date'])
        if ch: J['summary'] = summary(J, day); dumpj(J, V['jour'], indent=1)
    return done

def variant(V, allm, b, day, now, eod, spread, last, first, spark, hist, added):
    J = loadj(V['jour'], dict(start=None, days=[]))
    if not len(b) and any(d['date'] == str(day.date()) and d.get('trades') for d in J.get('days', [])):
        raise FeedError('no price bars for a day that already has trades')
    N.LAST_PICKS.clear()
    trades = N.run_day(allm, day, now, S=V['S'], exits=RULES, sp=MIN_SPREAD) if len(b) else []     # 22 Oct fix: fixed 1.8 pt levels
    if V['code'] == 'US100':                             # 22 Oct: the day's Nasdaq picks for the S&P page (it copies them in US hours)
        dumpj(dict(day=str(day.date()), picks=N.LAST_PICKS.get('picks', []) if N.LAST_PICKS.get('day') == str(day.date()) else [],
                   at=str(now)), os.path.join(HERE, 'docs', 'nq_picks.json'), indent=1)
    rows = [row(t, b, now, eod, spread) for t in trades]
    if J.get('start') is None: J['start'] = str(day.date())
    A = trades[0]['A'] if trades else None
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             final=bool(now >= eod))], key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    dumpj(J, V['jour'], indent=1)
    if rows:
        op = [r for r in rows if r['status'] == 'open']; state = rows[-1]['side'].lower()
        locked = bool(trades and trades[-1].get('locked_day'))
        msg = (f"{len(rows)} paper trade{'s' if len(rows) > 1 else ''} today ({len(op)} running). Each closes 25% (buys) / 15% (sells) at its part level, then the stop "
               f"goes to the entry and trails 0.45 x range behind the best price; "
               f"everything closes at the {dubai(eod)} Dubai close. At most 2 trades a day." + (" Day lock hit: no more trades today." if locked else ''))
    elif now >= eod: state, msg = 'none', 'No paper trade today.'
    else: state, msg = 'waiting', 'Waiting for the first signal.'
    return dict(base_card(A, V), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 1)),
                entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC_NOW[0], close_at=dubai(eod),
                history_note=f"history to {hist.index[-1].date()} ({hist.index.normalize().nunique()} days)" + (f" · added {', '.join(added)}" if added else ''))

def mark_failed(mk, V, e):
    c = mk.get(V['code']) or {}
    c.update(base_card(None, V)); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"Nasdaq paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk[V['code']] = c

def fail(e):
    """Keep the last good Nasdaq cards and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    for c in REMOVED: mk.pop(c, None)
    for V in VARIANTS: mark_failed(mk, V, e)
    dumpj(old, PORTAL, indent=1)
