"""S&P 500 (US500) PAPER signals for the page - version A (sp_engine.py; MT4-proven 22 Oct 2026, his run SP500_DAYTRADE v1.00:
2,330 trades 2020-01..2026-09, net $16,398 at $100 risk per leg, net/DD 6.23, worst day -$310). No phone alerts, no real money.
Called by run.py after the Nasdaq page, every minute. The day's Nasdaq picks come from docs/nq_picks.json (written by nq_run the same minute).
Files: docs/sp_min/YYYY-MM.npz (finished days of minute bars, broker clock, bid; if missing, the first run seeds the last 4 weeks from
Capital.com minutes, then each new day is added), docs/journal_sp.json (every paper trade), docs/data.json -> markets.US500 (the page)."""
import os, glob, json, time, requests, numpy as np, pandas as pd
import feeds as F, sp_engine as S
DEADLINE = time.time() + 240          # loop.py resets this every minute; the S&P part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = os.path.join(HERE, 'docs', 'sp_min'); JOUR = os.path.join(HERE, 'docs', 'journal_sp.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json'); PICKS = os.path.join(HERE, 'docs', 'nq_picks.json')
STATE = os.path.join(HERE, 'docs', 'sp_state.json')                    # data-check memory (22 Oct)
PICK_LATE = pd.Timedelta(minutes=3)   # 22 Oct fix: a Nasdaq pick first seen more than 3 min after its own minute is ignored
EPIC = os.environ.get('CAPITAL_EPIC_SP', 'US500')
MIN_SPREAD = S.COST                   # the paper result never uses less than 0.8 index points per leg (as in the MT4 test)
PASS = dict(green=40.0, pf=1.15, months=3)
RULES = 'v1.09'
BACKTEST_104 = dict(direction='—', days='44.5% profit days / 87% traded', perday='1.37', win='53.4%', pf='1.32', net='+$16,896 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.04 (his run 24 Oct, spread 0.8 pt), 2020-01-01..2026-09-30, 2,416 trades (2,135 day + 281 night); '
                       'worst day -$315; net/DD 8.83; max DD $1,914')
BACKTEST_107 = dict(direction='—', days='49.87% profit days (n=1,554 days)', perday='—', win='—', pf='—', net='+$13,939.21 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.07 (his run 1 Nov, Magic 500109, spread 18, Every tick), 2019.10.12-2026.10.10, 2,362 trades; '
                       'max DD $2,377.37 (0.24%); net/DD 5.86; row18=1 (night leg Mon/Tue/Wed only), row19=1.0 (night stop mult, was 2.0), row20=true (Turn-of-Month day leg)')
BACKTEST = dict(direction='—', days='—', perday='—', win='~68% of the 25 new Night V4 legs closed in profit', pf='—', net='+$14,896.29 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.08 (his run 3 Nov, Magic 500115, spread 18, Every tick), 2019.10.12-2026.10.31, 2,471 trades (+25 vs the '
                       '500114 baseline\'s 2,446); max DD $2,188.15 (0.22%, improved from 500114\'s $2,213.73); same 500114 rules (row18/19/20/23/24) PLUS '
                       'Night V4 (rows 25-27): a 3rd night trigger, no weekday restriction, on a weak last-hour close (252-day percentile of the 15:00-16:00 '
                       'NY return <= 0.30) combined with a last-hour volume spike (z-score vs its own trailing 20-day average >= 2.0) - isolating the 25 new '
                       'legs alone: net +$476.75, DD improved $25.58 vs 500114, ~68% closed in profit. WATCH ITEM: only 25 historical occurrences, 91-92% '
                       'already overlap the Night V2 VIX gate (row 21), 2022 a loss year inside the sample - treat as a refinement still proving itself, not '
                       'a settled edge; on the live page it needs ~2-4 weeks of its own Capital.com volume history before it can fire at all (see sp_run.py)')
CBOE = os.path.join(HERE, 'docs', 'cboe_sp.json')          # v1.04: the day's high-fear flag (decided once per broker day)
CBOE_URL = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv'
CBOE_Q = 'https://cdn.cboe.com/api/global/delayed_quotes/quotes/_{}.json'
GW = os.path.join(HERE, 'docs', 'gw_sp.json')              # v1.08: cached gold (GC=F) + WTI (CL=F) daily closes for the Night V3 combo trigger
LH_SEED = os.path.join(HERE, 'docs', 'sp_lh_seed.json')     # v1.09: static seed, last-hour % return per date from the MT4 backtest (RoboForex,
                                                             # Sep 2019 on) - committed once, never changes; no volume (see lh_today())
LH_LIVE = os.path.join(HERE, 'docs', 'sp_lh_live.json')     # v1.09: one row per finished day since Night V4 went live - return AND volume,
                                                             # both computed from the dashboard's own stored Capital.com minute history

def _cboe_series(sym, col):
    import io
    r = requests.get(CBOE_URL.format(sym), timeout=20); r.raise_for_status()
    x = pd.read_csv(io.StringIO(r.text)); x['DATE'] = pd.to_datetime(x.DATE, format='%m/%d/%Y')
    return x.set_index('DATE')[col if col in x.columns else x.columns[-1]].astype(float)

def _yahoo_daily_close(sym, period='2y'):
    import yfinance as yf
    d = yf.download(sym, period=period, interval='1d', progress=False, auto_adjust=False)
    if isinstance(d.columns, pd.MultiIndex): d.columns = [c[0] for c in d.columns]
    s = d['Close'].dropna().astype(float); s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize(); return s

def gw_today(day):
    """v1.08 Night V3: gold+WTI daily closes (cached in docs/gw_sp.json, refreshed once per broker day - same once-a-day shape as
    stress_today()'s Cboe cache). Returns a DataFrame indexed by date with gc_pct/cl_pct (each commodity's 252-day rolling
    percentile rank of |daily % close move|, >= 120 days warm-up) for combo_flag() in sp_engine.py, or None on a fetch failure
    (Night V3 then simply does not fire that night - same fail-safe shape as the Cboe fetch for the existing night leg)."""
    c = loadj(GW, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        gc = pd.Series([np.nan if x is None else x for x in c['gc']], index=idx)
        cl = pd.Series([np.nan if x is None else x for x in c['cl']], index=idx)
    else:
        try:
            gc = _yahoo_daily_close('GC=F'); cl = _yahoo_daily_close('CL=F')
            idx = gc.index.union(cl.index); gc = gc.reindex(idx); cl = cl.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     gc=[None if pd.isna(x) else float(x) for x in gc], cl=[None if pd.isna(x) else float(x) for x in cl], at=str(pd.Timestamp.utcnow()))
            dumpj(c, GW, indent=1)
        except Exception:
            return None
    gc_pct = gc.pct_change().abs().rolling(252, min_periods=120).rank(pct=True)
    cl_pct = cl.pct_change().abs().rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(gc_pct=gc_pct, cl_pct=cl_pct))

def lasthour_stats(b):
    """v1.09 Night V4: b = one finished broker day's minute bars (o h l c v). Returns (ret, vol) for the 22:00-23:00 broker window
    (= 15:00-16:00 NY, the same window the backtest's lh_pct/lhvol_z were built from), or (None, None) if that window has no bars.
    ret = % price return, open of the window's first bar -> close of its last bar. vol = sum of lastTradedVolume over the window
    (NaN bars treated as 0; None if the whole window has no volume data, e.g. months saved before this went live)."""
    hm = b.index.hour * 60 + b.index.minute
    w = b[(hm >= 22 * 60) & (hm < 23 * 60)]
    if not len(w) or not w.o.iloc[0]: return None, None
    ret = float(w.c.iloc[-1] / w.o.iloc[0] - 1)
    vol = float(np.nansum(w.v.values)) if w.v.notna().any() else None
    return ret, vol

def lh_today(day, hist):
    """v1.09 Night V4: extends docs/sp_lh_live.json with every newly-finished day's own last-hour return+volume (from `hist`, the
    dashboard's stored minute history - cheap, only new days since the last call are computed), merges the return series onto the
    static backtest seed (docs/sp_lh_seed.json), and returns a DataFrame indexed by date with lh_pct (252-day rolling percentile
    of the return, >=120 days warm-up - active from day one via the seed) and lhvol_z (z-score of the last hour's volume vs its
    own trailing 20-day average, >=10 days warm-up - starts with nothing and fills in naturally over the dashboard's own first
    ~2-4 live weeks, since Capital.com's volume count is a different scale to the RoboForex data the seed uses, so it is
    deliberately NOT seeded - see the v1.09 header note in sp_engine.py)."""
    seed = loadj(LH_SEED, {'dates': [], 'ret': []})
    live = loadj(LH_LIVE, {'dates': [], 'ret': [], 'vol': []})
    last_live = pd.Timestamp(live['dates'][-1]) if live['dates'] else None
    days = sorted(set(hist.index.normalize()))
    changed = False
    for d in days:
        if d >= day: continue                                                        # only finished days strictly before the one being decided
        if last_live is not None and d <= last_live: continue
        b = hist[(hist.index >= d) & (hist.index < d + pd.Timedelta(days=1))]
        ret, vol = lasthour_stats(b)
        if ret is None: continue
        live['dates'].append(str(d.date())); live['ret'].append(ret); live['vol'].append(vol); changed = True
    if changed: dumpj(live, LH_LIVE, indent=1)
    if not live['dates']: return None
    idx_s = pd.to_datetime(seed['dates']); idx_l = pd.to_datetime(live['dates'])
    ret = pd.concat([pd.Series(seed.get('ret', []), index=idx_s), pd.Series(live['ret'], index=idx_l)])
    ret = ret[~ret.index.duplicated(keep='last')].sort_index()
    vol = pd.Series(live['vol'], index=idx_l).sort_index()
    lh_pct = ret.rolling(252, min_periods=120).rank(pct=True)
    vmean = vol.rolling(20, min_periods=10).mean(); vstd = vol.rolling(20, min_periods=10).std()
    lhvol_z = (vol - vmean) / vstd
    return pd.DataFrame(dict(lh_pct=lh_pct, lhvol_z=lhvol_z))

def stress_today(day, now):
    """v1.04 night-leg flag for broker day `day` (cached in docs/cboe_sp.json). The last close before the day must be the previous NY
    weekday; if the Cboe file does not have it yet, today's delayed quote (the 4:15 pm close) is used for that date."""
    c = loadj(CBOE, {})
    if c.get('day') == str(day.date()) and 'stress' in c: return c['stress'], c
    try:
        V = pd.DataFrame(dict(vix=_cboe_series('VIX', 'CLOSE'), v3m=_cboe_series('VIX3M', 'CLOSE'), vvix=_cboe_series('VVIX', 'VVIX'))).dropna()
        prev = (pd.Timestamp(day) - pd.offsets.BDay(1)).normalize(); added = False
        if V.index.max() < prev:
            q = {}
            for sym, k in (('VIX', 'vix'), ('VIX3M', 'v3m'), ('VVIX', 'vvix')):
                r = requests.get(CBOE_Q.format(sym), timeout=20); r.raise_for_status(); q[k] = float(r.json()['data']['current_price'])
            V.loc[prev] = [q['vix'], q['v3m'], q['vvix']]; added = True
        f, d = S.stress_flag(V, day)
        c = dict(day=str(day.date()), stress=bool(f), detail=d, quote_used=added, at=str(now))
        dumpj(c, CBOE, indent=1); return c['stress'], c
    except Exception as e:
        return None, dict(error=f'{type(e).__name__}: {str(e)[:100]}')

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

def load_month(f):
    if not os.path.exists(f): return None
    z = np.load(f)
    v = z['v'] if 'v' in z.files else np.full(len(z['t']), np.nan)   # v1.09: months saved before Night V4 have no volume column - NaN, not a crash
    return pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c'], 'v': v}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]')))
def load_hist():
    fr = [load_month(f) for f in sorted(glob.glob(os.path.join(MIN, '*.npz')))]
    fr = [x for x in fr if x is not None]
    if not fr: raise RuntimeError('docs/sp_min history missing')
    return pd.concat(fr).sort_index()
def save_day(bars):
    os.makedirs(MIN, exist_ok=True); per = bars.index[0].strftime('%Y-%m'); f = os.path.join(MIN, per + '.npz')
    b = bars.copy()
    if 'v' not in b.columns: b['v'] = np.nan                          # v1.09: callers that still pass o/h/l/c only still work
    old = load_month(f); d = pd.concat([old, b[['o', 'h', 'l', 'c', 'v']]]) if old is not None else b[['o', 'h', 'l', 'c', 'v']]
    d = d[~d.index.duplicated(keep='last')].sort_index(); tmp = f + '.part'
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, t=d.index.values.astype('datetime64[m]').astype(np.int64), o=d.o.values, h=d.h.values, l=d.l.values, c=d.c.values, v=d.v.values)
    os.replace(tmp, f)

EPIC_NOW = [EPIC]; _TRIED = [False]
def find_epic(feed):
    """Look up the US 500 epic in Capital.com's market list (used only if the default name is refused)."""
    r = requests.get(f'{feed.base}/api/v1/markets', headers=feed.h, timeout=20, params={'searchTerm': 'US 500'}); r.raise_for_status()
    for mkt in r.json().get('markets', []):
        nm = str(mkt.get('instrumentName', '')).lower()
        if ('us 500' in nm or 's&p' in nm) and 'future' not in nm:
            EPIC_NOW[0] = mkt['epic']; print('S&P epic found:', EPIC_NOW[0]); return
    raise RuntimeError('US 500 not found in Capital.com markets - set CAPITAL_EPIC_SP')

def minutes(feed, start_b, end_b):
    """Capital.com US 500 minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('S&P time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC_NOW[0]}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid'], p.get('lastTradedVolume')))   # v1.09: volume, for Night V4's lhvol_z
        elif r.status_code == 404 and 'epic' in r.text.lower() and not _TRIED[0]:
            _TRIED[0] = True; find_epic(feed); continue
        elif r.status_code not in (400, 404):
            r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp', 'v'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp', 'v']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp', 'v']].astype(float).sort_index()

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

def seed(feed, day, get):
    """No stored history yet: fetch the last 4 weeks of finished weekdays from Capital.com and keep the reasonably complete ones
    (>= 85% of the median minute count of the fetched days; 22 Oct fix). Later days come through catch_up."""
    got = []
    for d in pd.bdate_range(day - pd.Timedelta(days=28), day - pd.Timedelta(days=1)):
        b = get(feed, d, d + pd.Timedelta(days=1)); b = b[(b.index >= d) & (b.index < d + pd.Timedelta(days=1))]
        if len(b) >= 60: got.append(b)
    if not got: return
    med = float(np.median([len(b) for b in got]))
    for b in got:
        if len(b) >= FULL_SHARE * med: save_day(b)

def row(t, b, now, sp):
    st = t['status']; nite = bool(t.get('night'))
    res = None if t['pts'] is None else round(t['pts'], 1)
    live = None
    if st == 'open' and len(b):
        pxn = float(b.c.values[-1]); live = round(t['dir'] * (pxn - t['entry']) - sp, 1)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], src='Night' if nite else ('TOM' if t['src'] == 2 else ('Nasdaq' if t['src'] == 0 else 'S&P')), leg=t['leg'], night=nite,
                price=round(t['entry'], 1), entry=round(t['entry'], 1), stop=round(t['stop'], 1), stop0=round(t['stop0'], 1), stop_pts=round(t['sd'], 1),
                half_px=None, half=False, size='full', status=st,
                exit=None if t['exit'] is None else round(t['exit'], 1), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=res, r=None if t['r'] is None else round(t['r'], 3), r_sized=None if t['r'] is None else round(t['r'], 3),
                live=live, spread=round(sp, 2))

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t['res'] for t in allt if t.get('res') is not None]
    start = D3[0]['date']; end = str((day or pd.Timestamp(D3[-1]['date'])).date())
    wd = max(1, len(pd.bdate_range(start, end))); tdays = sum(1 for d in D3 if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(start).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES, direction=None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('res') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None):
    note = ('14-day range ' + ('—' if A is None else f'{A:,.0f} pts') + ' · stop 0.75 x range' + ('' if A is None else f' (= {0.75 * A:,.0f} pts)') +
            ' · no half-close · the day\'s first signal sets BUY or SELL, later signals the same way add (max 3 trades) · v1.04: no 2nd/3rd trade from '
            '11:00 am New York or once the day is up half a stop · signals: Nasdaq desk signals copied in US hours + S&P 9:40 am New York move, yesterday '
            'high/low sweep, big move by 10 am New York · close 3:30 pm New York · NIGHT trade on high-fear nights (VIX above VIX3M, or VIX / VVIX in '
            'their 1-year top 10%): BUY 6:01 pm New York (v1.07: Mon/Tue/Wed broker-days only), stop 1 x range (v1.07, was 2x), close 10:00 am New York · '
            'v1.07 TURN-OF-MONTH: on the last broker weekday of the month and the first 3 of the next, BUY 9:30 am New York, stop 0.75 x range, close 3:30 pm '
            'New York - only on a day with no other S&P trade · v1.08 NIGHT V3: a 2nd, independent night trigger (only fires when the night trade above does '
            'not - never both), broker-day Wed/Thu/Fri only, on a gold+WTI combined overnight shock (the smaller of gold\'s and WTI\'s own 252-day-percentile '
            '|daily move|, from 2 days before, >= 0.70): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as the night leg '
            'above · v1.09 NIGHT V4: a 3rd, independent night trigger (only fires when the two night trades above do not - never more than one a night), no '
            'weekday restriction, on a weak last-hour close (252-day percentile of the 15:00-16:00 New York return <= 0.30) combined with a last-hour volume '
            'spike (z-score vs its own trailing 20-day average >= 2.0): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as the '
            'other night trades. WATCH ITEM (only 25 historical occurrences, mostly overlapping the VIX night trade above) - needs ~2-4 weeks of its own '
            'live volume history before it can fire at all')
    return dict(code='US500', name='S&P 500', symbol='US500 · Capital.com US 500', live=False, paper=True, status='Paper', version=RULES,
                unit='pts', dp=1, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live S&P signals do as well as the v1.09 MT4 test (500109 + Night V3 + Night V4). Decision after about 3 months.',
                cost_note='Results are index points per trade after 0.8 points of cost (Capital.com spread + slippage).',
                net_label='Net points (v1.09 rules)')

def picks_for(day, now, jd, record=True):
    """Today's Nasdaq desk picks [(nasdaq minute, side)] (22 Oct fix). Each pick's FIRST-SEEN time is kept in the journal day (picks_seen);
    a pick first seen more than 3 minutes after its own minute is ignored (a late Nasdaq pick can no longer flip the day).
    Returns (accepted picks, note or None, stale: the picks file is older than 3 minutes in US hours)."""
    seen = jd.setdefault('picks_seen', {}); note = None; stale = False
    if record:
        p = loadj(PICKS, {})
        if p.get('day') == str(day.date()):
            for t, s in p.get('picks', []): seen.setdefault(f'{pd.Timestamp(t)}|{int(s)}', str(now))
        else: note = 'Nasdaq picks for today not written yet'
        hm = now.hour * 60 + now.minute
        if S.US_LO <= hm < S.US_HI:
            try: age = now - pd.Timestamp(p.get('at'))
            except Exception: age = None
            if p.get('day') != str(day.date()) or age is None or age > PICK_LATE:
                stale = True; note = 'Nasdaq picks file ' + ('missing' if age is None else f'{age.total_seconds() / 60:.0f} min old') + ' - Nasdaq signals may be missed'
    acc, late = [], []
    for k, fs in seen.items():
        t, s = k.rsplit('|', 1); t = pd.Timestamp(t)
        (acc if pd.Timestamp(fs) - t <= PICK_LATE else late).append((t, int(s)))
    if late: note = (note + '; ' if note else '') + f'{len(late)} late Nasdaq pick(s) ignored'
    return sorted(acc), note, stale

def legs_now(b, A, pH, pL, picks, day, day_done, jd):
    """The day's legs (22 Oct fix): legs already shown stay exactly as shown (legs_frozen: time, side, entry, stop distance), even if a
    recompute would not make them; a new leg is added only on the side of the shown legs and while there are fewer than 3."""
    fz = jd.get('legs_frozen', []); out = []; keys = set()
    for f in fz:
        t = pd.Timestamp(f['t']); j = int(b.index.searchsorted(t, side='right')) - 1
        if j < 0: continue
        out.append(dict(j=j, t=t, dir=int(f['dir']), src=int(f['src']), name=f['name'], leg=int(f['leg']), entry=float(f['entry']), sd=float(f['sd']),
                        A=float(f['sd']) / S.SM)); keys.add((str(t), int(f['dir']), f['name']))
    side = out[0]['dir'] if out else 0
    for g in S.legs_of_day(b, A, pH, pL, picks, day, day_done=day_done) if np.isfinite(A) else []:
        if (str(b.index[g['j']]), g['dir'], g['name']) in keys: continue
        if side == 0: side = g['dir']
        if g['dir'] != side or len(out) >= S.LEGS: continue
        out.append(dict(g, leg=len(out) + 1))
    return out

def freeze_legs(jd, trades):
    jd['legs_frozen'] = [dict(t=str(t['t']), dir=int(t['dir']), src=int(t['src']), name=t['name'], leg=int(t['leg']), entry=float(t['entry']), sd=float(t['sd']))
                         for t in trades if not t.get('night')]          # v1.04: the night leg is rebuilt each run from the day's stress flag

def compute(hist, b, day, now, picks, sp, jd):
    """One broker day: b = its closed bars (o h l c). Returns the managed legs (frozen ones kept)."""
    eod = day + pd.Timedelta(minutes=S.eod_minutes(day)); xt = day + pd.Timedelta(minutes=S.X_MIN)
    if not len(b):
        if jd.get('legs_frozen'): raise FeedError('no price bars for a day that already has trades')
        return []
    A, pH, pL = S.day_ctx(hist[hist.index < day].iloc[-40 * 1500:], day)
    legs = legs_now(b[['o', 'h', 'l', 'c']], A, pH, pL, picks, day, bool(now >= eod), jd)
    trades = S.manage(b[['o', 'h', 'l', 'c']], legs, A, day, sp, now_done=bool(now >= eod))
    if jd.get('stress'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod)) + trades     # v1.04 night leg (v1.07: Mon/Tue/Wed only, stop 1.0x range - gated above)
    elif jd.get('v3'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.08 Night V3: gold+WTI combo night (Wed/Thu/Fri only, gated below) -
                                            name='Night long (gold+WTI overnight shock)', src=3) + trades                 # never both: only fires when the regular stress-night leg above did NOT
    elif jd.get('v4'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.09 Night V4: weak-close + volume-spike night (gated below) -
                                            name='Night long (weak-close + volume-spike)', src=4) + trades                # never with the other two: only fires when stress AND v3 above did NOT
    if not trades and S.tom_window(day) and np.isfinite(A) and now.hour * 60 + now.minute >= S.TOM_DECIDE:
        trades = S.tom_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod)) + trades                        # v1.07 row20: only once no other S&P leg has fired by 17:00 broker
    for t in trades:                                     # past the close time but no bar there yet: close at the last price
        xt_ = day + pd.Timedelta(minutes=S.NIGHT_OUT) if t.get('night') else xt
        if t['status'] == 'open' and now >= xt_ + pd.Timedelta(minutes=1) and len(b):
            ex = float(b.c.values[-1]); t.update(status='eod', exit=ex, exit_t=b.index[-1], pts=t['dir'] * (ex - t['entry']) - sp)
            t['r'] = t['pts'] / t['sd']
    return trades

def finish_old_days(J, hist, day, st):
    """22 Oct fix: a journal day left non-final (the desk stopped before its close) is re-run on its stored full day and closed
    (shown legs kept, only the picks it had accepted)."""
    done = []
    for jd in J.get('days', []):
        if jd.get('final') or jd.get('rules') != RULES or jd['date'] >= str(day.date()): continue
        d = pd.Timestamp(jd['date']); nd = d + pd.Timedelta(days=1)
        if jd['date'] in st.get('holidays', []): jd['final'] = True; done.append(jd['date']); continue
        b = hist[(hist.index >= d) & (hist.index < nd)]
        if not len(b) or d < day - pd.Timedelta(days=10): continue            # not stored yet (catch-up retries) / too old to redo
        picks, _, _ = picks_for(d, nd, jd, record=False)
        sp = max([MIN_SPREAD] + [float(t.get('spread') or 0) for t in jd.get('trades', [])])
        trades = compute(hist, b, d, nd, picks, sp, jd); freeze_legs(jd, trades)
        rows = [row(t, b, nd, sp) for t in trades]
        dr = [r for r in rows if not r.get('night')]
        jd.update(trades=rows, side=(dr[0]['side'] if dr else None), final=True, finished_late=True); done.append(jd['date'])
    return done

def main(feed=None, get=None, now=None):
    global DEADLINE; DEADLINE = time.time() + 75     # 22 Oct fix: own 75 s time budget per market (no shared window)
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    if now.dayofweek >= 5:
        prev = mk.get('US500') or {}
        mk['US500'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(), state='closed', message='Market closed for the weekend.',
                           entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('S&P: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('S&P paper needs the Capital.com prices')
        feed = F.Capital()
    st = load_state()
    try: hist = load_hist()
    except RuntimeError: seed(feed, day, get); hist = load_hist()
    added, pend = catch_up(feed, hist, day, get, now, st); save_state(st)
    if pend: raise FeedError('minute history not complete yet (' + '; '.join(pend) + ')')
    if added: hist = load_hist()
    fin = finish_old_days(J, hist, day, st)
    if fin: J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]
    eod = day + pd.Timedelta(minutes=S.eod_minutes(day)); xt = day + pd.Timedelta(minutes=S.X_MIN)
    bad = feed_check(b, now, eod, st, 'US500'); save_state(st)
    if bad: raise FeedError(bad)                         # 22 Oct fix: an empty / stale fetch is a feed error (last good card kept), not 'no trades'
    spread = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else None
    sp = max(MIN_SPREAD, spread or 0.0)
    jd = next((d for d in J['days'] if d['date'] == str(day.date())), None) or {}
    picks, pnote, pstale = picks_for(day, now, jd)
    stress, cinfo = stress_today(day, now)               # v1.04: decided once per day; only a decision made by 01:06 broker can open the night leg
    if 'stress' not in jd and stress is not None:
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        ok_day = day.dayofweek <= S.NIGHT_DOW_MAX                      # v1.07 row18: night leg only Mon/Tue/Wed
        jd['stress'] = bool(stress) and ok_time and ok_day
        if stress and not jd['stress']:
            jd['stress_note'] = ('high-fear night, but the check ran after 6:06 pm New York - no night trade' if not ok_time
                                 else 'high-fear night, but v1.07 only trades the night leg Mon/Tue/Wed - no night trade')
    if 'v3' not in jd and 'stress' in jd:                 # v1.08 Night V3: decided once per day, only once stress is already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        G = None if jd['stress'] else gw_today(day)       # don't even fetch gold/WTI on a night the stress leg already took
        fired, ginfo = S.combo_flag(G, day) if G is not None else (False, {})
        jd['v3'] = bool(fired) and ok_time and not jd['stress']
        if ginfo: jd['v3_detail'] = ginfo
        if G is None and not jd['stress'] and day.dayofweek in S.V3_DOW:
            jd['v3_note'] = 'gold/WTI data unavailable this run - no Night V3 check'
    if 'v4' not in jd and 'v3' in jd:                      # v1.09 Night V4: decided once per day, only once stress+v3 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Sdf = None if (jd['stress'] or jd['v3']) else lh_today(day, hist)
        fired, linfo = S.v4_flag(Sdf, day) if Sdf is not None else (False, {})
        jd['v4'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3']
        if linfo: jd['v4_detail'] = linfo
        if Sdf is None and not jd['stress'] and not jd['v3']:
            jd['v4_note'] = 'no Night V4 check (volume history still warming up, or data unavailable)'
    trades = compute(hist, b, day, now, picks, sp, jd)
    freeze_legs(jd, trades)
    rows = [row(t, b, now, sp) for t in trades]; drows = [r for r in rows if not r.get('night')]; nrow = [r for r in rows if r.get('night')]
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 1), round(float(r.o), 1), round(float(r.h), 1), round(float(r.l), 1)] for t, r in g5.iterrows()]
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict({k: jd[k] for k in ('picks_seen', 'legs_frozen', 'stress', 'stress_note', 'v3', 'v3_note', 'v3_detail', 'v4', 'v4_note', 'v4_detail') if k in jd}, date=str(day.date()), rules=RULES,
                             label=day.strftime('%a %d %b'), side=(drows[0]['side'] if drows else None), trades=rows, final=bool(now >= eod))],
                      key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    A = trades[0]['A'] if trades else S.day_ctx(hist[hist.index < day].iloc[-40 * 1500:], day)[0]
    if drows:
        op = [r for r in drows if r['status'] == 'open']; state = drows[0]['side'].lower()
        msg = (f"PAPER {drows[0]['side']} day: {len(drows)} trade{'s' if len(drows) > 1 else ''} today ({len(op)} running). Only {drows[0]['side']} signals count "
               f"today (max 3; no 2nd/3rd trade from 11:00 am New York or once the day is up half a stop). Each trade keeps its stop, no half-close; everything "
               f"closes at {dubai(xt)} Dubai (3:30 pm New York).")
    elif now >= xt: state, msg = 'none', 'No paper day trade today.'
    else: state, msg = 'waiting', (f'Waiting for the first day signal (from {dubai(day + pd.Timedelta(minutes=16 * 60 + 40))} Dubai: 9:40 am New York move, '
                                   'Nasdaq signals; earlier: yesterday high/low sweep).')
    if nrow:                                             # v1.04 night leg (v1.08: or Night V3, gold+WTI combo - jd['v3']; v1.09: or Night V4 - jd['v4'])
        n_ = nrow[0]; label = 'weak-close + volume-spike' if jd.get('v4') else ('gold+WTI shock' if jd.get('v3') else 'high-fear night')
        msg = (f"NIGHT BUY ({label}) at {n_['time']} Dubai, stop {n_['stop']}, " +
               (f"closes at {dubai(day + pd.Timedelta(minutes=S.NIGHT_OUT))} Dubai (10:00 am New York). " if n_['status'] == 'open' else f"closed ({n_['status']}). ") + msg)
        if state in ('none', 'waiting') and n_['status'] == 'open': state = 'buy'
    elif jd.get('stress_note'): msg += ' (' + jd['stress_note'] + '.)'
    elif jd.get('stress') is False and jd.get('v3') is False and jd.get('v4') is False: msg += ' No night trade today (not a high-fear night, no gold+WTI shock, no weak-close + volume spike).'
    elif jd.get('v3_note'): msg += ' (' + jd['v3_note'] + '.)'
    elif jd.get('v4_note'): msg += ' (' + jd['v4_note'] + '.)'
    elif stress is None: msg += f" (Night-trade check: Cboe data not available - {cinfo.get('error', '')}.)"
    if pnote and now.hour * 60 + now.minute >= S.US_LO: msg += f' ({pnote}.)'
    mk['US500'] = dict(base_card(A if A == A else None), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 1)),
                       entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, picks_stale=pstale, epic=EPIC_NOW[0], close_at=dubai(xt),
                       history_note=f"history to {hist.index[-1].date()} ({hist.index.normalize().nunique()} days)" + (f" · added {', '.join(added)}" if added else '')
                       + (f" · finished {', '.join(fin)}" if fin else ''))
    dumpj(old, PORTAL, indent=1)
    print(f'S&P paper: {now} broker | bars {len(b)} | picks {len(picks)} | legs {len(rows)} | history to {hist.index[-1].date()} | added {added} | finished {fin}')

def fail(e):
    """Keep the last good S&P card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('US500') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"S&P paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['US500'] = c; dumpj(old, PORTAL, indent=1)
