"""WTI PAPER signals for the page (no phone alerts, no real money). Called by run.py after gold and USDJPY, every minute.
Replays today's Capital.com US Crude (OIL_CRUDE) minutes through the WTI_DAYTRADE v1.02 rules (wti_engine.py; checked against the EA's
Python port on 2020-2026: 4,476 of 4,476 trades, same minute, direction, price, exit and right-way-first) and keeps a paper journal,
judged after ~3 months (pass = right way first >= 53% and profit factor >= 1.10 with v1.02 sizes after Capital.com's spread).
Files: docs/wti_hist.json (finished broker days: date, open, high, low, close, settle; seeded from HistData to 2026-10-02, then extended
with Capital.com minutes), docs/journal_wti.json (every paper trade), docs/data.json -> markets.OIL (the page)."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, wti_engine as W
DEADLINE = time.time() + 240          # loop.py resets this every minute; the WTI part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, 'docs', 'wti_hist.json'); JOUR = os.path.join(HERE, 'docs', 'journal_wti.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
EPIC = os.environ.get('CAPITAL_EPIC_WTI', 'OIL_CRUDE')
MIN_SPREAD = 0.02                     # the paper result never uses less than 2 cents a barrel
PASS = dict(direction=53.0, pf=1.10, months=3)
BACKTEST = dict(direction='53.0%', days='95.5%', perday='2.55', win='37.2% / 36.0%', pf='1.20 / 1.08', net='+$49,700 / +$22,076 at 0.30 + 0.10 lots',
                source='MT4 v1.02, 2020-01 to 2026-06, 4,300 trades; spread 2 (Prime-like) / spread 6 (Pro-like)')

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

def minutes(feed, start_b, end_b):
    """Capital.com OIL_CRUDE minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('WTI time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code not in (400, 404):
            r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def day_bars(b, day):
    b = b[(b.index >= day) & (b.index < day + pd.Timedelta(days=1))]
    return b.index, b.o.values, b.h.values, b.l.values, b.c.values

def catch_up(feed, H, day, get=None):
    """Add every finished weekday after H['through'] and before `day` (Capital.com minutes). Saves after each day."""
    get = get or minutes; last = pd.Timestamp(H['through']); added = []
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1)
        if nxt.dayofweek < 5:
            t, o, h, l, c = day_bars(get(feed, nxt, nxt + pd.Timedelta(days=1)), nxt)
            if len(t) >= 60:
                H['days'].append([str(nxt.date()), *W.daily_from_minutes(t, o, h, l, c)]); added.append(str(nxt.date()))
            else: added.append(str(nxt.date()) + ' (no prices - holiday)')
        last = nxt; H['through'] = str(last.date()); H['days'] = H['days'][-W.KEEP_DAYS:]
        json.dump(H, open(HIST, 'w'), separators=(',', ':'))
    return added

def row(t, now, day_over):
    st = t['status']
    if st == 'open' and day_over: st = 'close_now'
    sp = max(MIN_SPREAD, t['spread'] or 0.0)
    res = None if t['exit'] is None else round((t['exit'] - t['px']) * t['dir'] - sp, 3)
    w = 1.0 if t['size'] == 'full' else 1 / 3
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], price=round(t['px'], 2), stop=round(t['stop'], 2),
                stop_usd=round(abs(t['px'] - t['stop']), 2), size=t['size'], first=t['first'], status=st,
                exit=None if t['exit'] is None else round(t['exit'], 2), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=None if res is None else round(res * w, 3), rwf=t['rwf'], spread=round(sp, 3))

def summary(J, day=None):
    allt = [t for d in J.get('days', []) for t in d['trades']]
    if not J.get('start'): return dict(since=None, trades=0)
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]; rr = [t['res_sized'] for t in allt if t.get('res_sized') is not None]
    end = str((day or pd.Timestamp(J['days'][-1]['date'])).date()) if J.get('days') else J['start']
    wd = max(1, len(pd.bdate_range(J['start'], end))); tdays = sum(1 for d in J['days'] if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), decided=len(dec),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 2) if rr else None)

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None):
    note = ('14-day range ' + ('—' if A is None else f'${A:.2f}') + ' · stop ¼ range · no target · close 11:00 pm broker (Fri 10:50 pm) = '
            '12:00 am Dubai, 1:00 am in winter · size: sells from the day\'s 2nd trade full, the rest ⅓')
    return dict(code='OIL', name='Oil (WTI)', symbol='WTI · Capital.com US Crude', live=False, paper=True, status='Paper', version='v1.02',
                unit='usd', dp=2, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='This page tracks whether live WTI signals do as well as the backtest. Decision after about 3 months.',
                cost_note="Results are $ per barrel (v1.02 sizes: full or ⅓), from the signal price with the backtest's slip, minus Capital.com's spread (at least 2 cents).",
                net_label='Net $ per barrel (v1.02 sizes)')

def main(feed=None, get=None, now=None):
    now = now or F.broker_now(); day = now.normalize()
    H = loadj(HIST, None)
    if H is None: raise RuntimeError('docs/wti_hist.json missing')
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    if now.dayofweek >= 5:
        prev = mk.get('OIL') or {}
        mk['OIL'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(), state='closed', message='Market closed for the weekend.',
                         entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        json.dump(old, open(PORTAL, 'w'), indent=1); print('WTI: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('WTI paper needs the Capital.com prices')
        feed = F.Capital()
    added = catch_up(feed, H, day, get)
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]       # today's closed minute bars only
    P = W.prep(H['days'], day)
    hm = W.close_hm(day); eod = day + pd.Timedelta(minutes=hm); day_over = now >= eod
    trades = W.run_day(P, b.index, b.o.values, b.h.values, b.l.values, b.c.values, spread=b.sp.values) if (P and len(b)) else []
    rows = [row(t, now, day_over) for t in trades]
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             range_usd=(None if P is None else round(P['A'], 2)), traded=bool(P), final=bool(day_over))], key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    json.dump(J, open(JOUR, 'w'), indent=1)
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    last_sig = now >= eod
    if P is None: state, msg = 'none', 'No trading today (not enough history or the day after a long break - same rule as the EA).'
    elif rows:
        side = rows[0]['side']; state = side.lower()
        msg = f"PAPER {side} day — later signals today are {side} only. Each trade holds until its stop or the {dubai(eod)} Dubai close. No target."
    elif last_sig: state, msg = 'none', 'No paper trade today.'
    else: state, msg = 'waiting', 'Waiting for the first signal.'
    spark = []
    if len(b):
        c5 = b.c.resample('5min').last().dropna(); spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(v), 2)] for t, v in c5.items()]
    mk['OIL'] = dict(base_card(None if P is None else P['A']), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 2)),
                     entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC,
                     history_note=f"history to {H['through']} ({len(H['days'])} days)" + (f" · added {', '.join(added)}" if added else ''))
    json.dump(old, open(PORTAL, 'w'), indent=1)
    print(f'WTI paper: {now} broker | trades today {len(rows)} | bars {len(b)} | history to {H["through"]} | added {added}')

def fail(e):
    """Keep the last good WTI card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('OIL') or {}
    c = {k: v for k, v in c.items() if k not in ('status', 'note')} if c.get('paper') is None else c
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"WTI paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['OIL'] = c; json.dump(old, open(PORTAL, 'w'), indent=1)
