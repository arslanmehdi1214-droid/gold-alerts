"""USDJPY PAPER signals for the page (no phone alerts, no real money). Called by run.py after gold, every 5 minutes.
Replays today's Capital.com USDJPY minutes through the USDJPY_DAYTRADE v1.01 rules (yen_engine.py; checked against his MT4 run:
3,321 of 3,321 trades 2020-2026, same minute and direction) and keeps a paper journal, judged after ~3 months
(pass = right way first >= 53% and profit factor >= 1.10).
Files: docs/usdjpy_hist.json (the EA's finished daily + hourly bars; seeded from his MT4 data to 2026-09-25, then extended with
Capital.com minutes), docs/journal_usdjpy.json (every paper trade), docs/data.json -> markets.USDJPY (the page)."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, yen_engine as Y
DEADLINE = time.time() + 240          # yen gets at most 4 minutes per run, so the gold save step always runs (workflow limit 8 min)

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, 'docs', 'usdjpy_hist.json'); JOUR = os.path.join(HERE, 'docs', 'journal_usdjpy.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
EPIC = os.environ.get('CAPITAL_EPIC_USDJPY', 'USDJPY'); LOTS = 0.10
PASS = dict(direction=53.0, pf=1.10, months=3)
BACKTEST = dict(direction='53.6%', days='99.5%', perday='1.97', win='37.4%', pf='1.17', net='+$6,879 at 0.10 lots',
                source='MT4 backtest 2020-01-02 to 2026-06-12, 3,321 trades')

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def secs(ts): return int(pd.Timestamp(ts).value // 10**9)
def ts(s): return pd.Timestamp(int(s), unit='s')
def dubai(s): return F.broker_to_dubai(ts(s)).strftime('%-I:%M %p').lower()

def minutes(feed, start_b, end_b):
    """Capital.com USDJPY minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('USDJPY time budget used up (4 min) - next run continues')
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

def arrays(b):
    return b.index.values.astype('datetime64[s]').astype(np.int64), b.o.values, b.h.values, b.l.values, b.c.values

def catch_up(feed, H, day):
    """Add every finished broker day after H['through'] and before `day` to the history. Uses Capital.com minutes; if a weekday has
    fewer than 10 hours of window minutes, uses Capital.com hourly bars for that day instead (hours 01-23) when they cover more."""
    last = pd.Timestamp(H['through']); added = []
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1)
        if nxt.dayofweek < 5:
            b = minutes(feed, nxt, nxt + pd.Timedelta(days=1)); b = b[(b.index >= nxt) & (b.index < nxt + pd.Timedelta(days=1))]
            dd, hh = Y.history(*arrays(b)); how = 'minutes'
            if sum(Y.inwin(x) for x in arrays(b)[0]) < 600:
                h1 = feed.bars('HOUR', *(pd.Timestamp(x) for x in ((nxt - pd.Timedelta(hours=7)).tz_localize(F.NY).tz_convert('UTC').tz_localize(None),
                                                                     (nxt + pd.Timedelta(hours=17)).tz_localize(F.NY).tz_convert('UTC').tz_localize(None))),
                               pd.Timedelta(hours=30), EPIC)
                h1 = h1[(h1.index >= nxt + pd.Timedelta(hours=1)) & (h1.index < nxt + pd.Timedelta(days=1))]
                if len(h1) > len(hh):
                    hh = [(secs(t), float(r.o), float(r.h), float(r.l), float(r.c)) for t, r in h1.iterrows()]
                    dd = [(secs(nxt), hh[0][1], max(x[2] for x in hh), min(x[3] for x in hh), hh[-1][4])]; how = 'hourly bars'
            if dd:
                H['days'].append([str(nxt.date()), *dd[0][1:]]); H['hours'] += [[str(ts(x[0]))[:16], *x[1:]] for x in hh]
                added.append(str(nxt.date()) + ('' if how == 'minutes' else ' (from hourly bars)'))
            else:
                added.append(str(nxt.date()) + ' (no prices - holiday)')
        last = nxt; H['through'] = str(last.date())
    H['days'] = H['days'][-Y.KEEP_DAYS:]; H['hours'] = H['hours'][-Y.KEEP_HOURS:]
    return added

def main():
    now = F.broker_now(); day = now.normalize()
    H = loadj(HIST, None)
    if H is None: raise RuntimeError('docs/usdjpy_hist.json missing')
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    if now.dayofweek >= 5:
        prev = mk.get('USDJPY') or {}
        mk['USDJPY'] = dict(prev, **base_card(), state='closed', message='Market closed for the weekend.', entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        json.dump(old, open(PORTAL, 'w'), indent=1); print('USDJPY: weekend'); return
    if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('USDJPY paper needs the Capital.com prices')
    feed = F.Capital()
    added = catch_up(feed, H, day)
    json.dump(H, open(HIST, 'w'), separators=(',', ':'))
    b = minutes(feed, day - pd.Timedelta(hours=8), now); b = b[b.index + pd.Timedelta(minutes=1) <= now]      # closed minute bars only
    T, O, Hh, L, C = arrays(b)
    eng = Y.Yen([[secs(d[0]), *d[1:]] for d in H['days']], [[secs(x[0]), *x[1:]] for x in H['hours']])
    d0, n0 = secs(day), secs(now)
    trades = eng.run_day(d0, T, O, Hh, L, C, now=n0, spread=b.sp.values) if len(b) else []
    hm = Y.FRI_CLOSE_HHMM if now.dayofweek == 4 else Y.CLOSE_HHMM
    eod = day + pd.Timedelta(hours=hm // 100, minutes=hm % 100)      # day-end close (6 pm broker since 2026-10-04)
    rows = [row(t, now >= eod) for t in trades]
    # ---- journal: one record per broker day, replaced on every run of that day
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             atr_pips=round(eng.atr() * 100, 1), final=bool(now >= eod))], key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    json.dump(J, open(JOUR, 'w'), indent=1)
    # ---- page card
    tod = b[b.index >= day]; inw = tod[[Y.inwin(secs(t)) for t in tod.index]]
    last = float(tod.c.iloc[-1]) if len(tod) else None; first = float(inw.o.iloc[0]) if len(inw) else None
    last_sig = now >= day + pd.Timedelta(hours=19)
    if rows:
        side = rows[0]['side']; state = side.lower()
        msg = f"PAPER {side} day — later signals today are {side} only. Each trade holds until its stop or the {dubai(secs(eod))} Dubai close. No target."
    elif last_sig: state, msg = 'none', f"No paper trade today (new signals stop at {dubai(secs(day + pd.Timedelta(hours=19)))} Dubai)."
    else: state, msg = 'waiting', 'Waiting for the first signal.'
    spark = []
    if len(inw):
        c5 = inw.c.resample('5min').last().dropna(); spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(v), 3)] for t, v in c5.items()]
    mk['USDJPY'] = dict(base_card(), state=state, message=msg, price=last, change_pips=(None if last is None or first is None else round((last - first) * 100, 1)),
                        atr_pips=round(eng.atr() * 100, 1), entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False,
                        history_note=f"history to {H['through']} ({len(H['days'])} days)" + (f" · added {', '.join(added)}" if added else ''))
    json.dump(old, open(PORTAL, 'w'), indent=1)
    print(f'USDJPY paper: {now} broker | trades today {len(rows)} | bars {len(b)} | history to {H["through"]} | added {added}')

def base_card():
    return dict(code='USDJPY', name='USD/JPY', symbol='USD/JPY', live=False, paper=True, status='Paper', version='v1.01', lots=LOTS,
                stats=BACKTEST, pass_bar=PASS)

def row(t, day_over):
    st = t['status']
    if st == 'open' and day_over: st = 'close_now'
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', sig=t['sig'], name=t['name'], price=t['px'], stop=t['stop'],
                stop_pips=t['stop_pips'], first=t['first'], status=st, exit=t['exit'], exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                pips=t['pips'], usd=None if t['pips'] is None else round(t['pips'] * LOTS * 1000 / t['px'], 2), rwf=t['rwf'], spread=t['spread_pips'])

def summary(J, day=None):
    allt = [t for d in J.get('days', []) for t in d['trades']]
    if not J.get('start'): return dict(since=None, trades=0)
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]; pp = [t['pips'] for t in allt if t.get('pips') is not None]
    usd = [t['usd'] for t in allt if t.get('usd') is not None]
    end = str((day or pd.Timestamp(J['days'][-1]['date'])).date()) if J.get('days') else J['start']
    wd = max(1, len(pd.bdate_range(J['start'], end))); tdays = sum(1 for d in J['days'] if d['trades'])
    gp, gl = sum(p for p in pp if p > 0), -sum(p for p in pp if p < 0)
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), decided=len(dec),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(pp), win=(round(100 * sum(p > 0 for p in pp) / len(pp), 1) if pp else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net_pips=round(sum(pp), 1) if pp else None, net_usd=round(sum(usd), 2) if usd else None)

def jdays(J):
    return J.get('days', [])[-30:][::-1]

def fail(e):
    """Keep the last good USDJPY card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('USDJPY') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting')
    c['feed_error'] = True
    c['message'] = f"USDJPY paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every 5 minutes."
    mk['USDJPY'] = c; json.dump(old, open(PORTAL, 'w'), indent=1)
