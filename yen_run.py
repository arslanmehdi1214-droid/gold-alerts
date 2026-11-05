"""USDJPY PAPER signals for the page (no phone alerts, no real money). Called by run.py after gold, every 5 minutes.
Replays today's Capital.com USDJPY minutes through the USDJPY_DAYTRADE rules (yen_engine.py; v1.07 from broker day 2026-11-05
- adds the 13th "WGAP" signal, fades the Friday-close-to-Monday-open gap once a week with its own stop/tiny-target, and
critically EXEMPTS WGAP's own open leg from the day-side breakout-flip, MT4-confirmed as EA build v1.11 WGAP, real MT4
run 5 Nov 2026, PASSED (win rate hit-target +0.15pt FULL/+0.23pt 2023-26, flip-protected count >0 in both "on" runs - the
fix engaged for real, net/DD/worst-day/green-days all flat or improved) - see day-trading-usdjpy-2; v1.06 from broker day
2026-11-03 - adds the 12th "HAM" signal, same Heikin-Ashi 7am scalp fired again at hour 7, MT4-confirmed as EA build v1.09
HAM(hour7), real MT4 run 3 Nov 2026, PASSED all 12 pass-bar criteria (win rate +1.39pt FULL/+1.28pt 2023-26, trades/day +23%,
every P&L guardrail milder than predicted) - see day-trading-usdjpy-2; v1.05 from broker day 2026-10-23, checked trade by
trade against his MT4 v1.05 run 22 Oct; v1.03 before) and keeps a paper journal, judged after ~3 months (pass = green days >= 60% and profit factor >= 1.10).
Journal days are tagged with the rules they ran; the record counts only the current rules (v1.01 days 5-16 Oct 2026 stay but are not mixed in).
Files: docs/usdjpy_hist.json (the EA's finished daily + hourly bars; seeded from his MT4 data to 2026-09-25, then extended with
Capital.com minutes), docs/journal_usdjpy.json (every paper trade), docs/data.json -> markets.USDJPY (the page)."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, yen_engine as Y
DEADLINE = time.time() + 240          # yen gets at most 4 minutes per run, so the gold save step always runs (workflow limit 8 min)

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, 'docs', 'usdjpy_hist.json'); JOUR = os.path.join(HERE, 'docs', 'journal_usdjpy.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
EPIC = os.environ.get('CAPITAL_EPIC_USDJPY', 'USDJPY'); LOTS = 0.10
PASS = dict(green=60.0, pf=1.10, months=3)
V104_FROM = '2026-10-23'                 # broker day the new rules start = v1.05 (HA 7am tiny target + breakout flip, max 1 flip a day); earlier days = v1.03
V106_FROM = '2026-11-03'                 # broker day v1.06 starts = v1.05 + the 12th "HAM" signal (Heikin-Ashi 7am scalp, fired again at hour 7)
V107_FROM = '2026-11-05'                 # broker day v1.07 starts = v1.06 + the 13th "WGAP" signal (weekend-gap fade, flip-exempt)
RULES = 'v1.07'
BT103 = dict(direction='—', days='68.7% green / 99.5% traded', perday='1.86', win='78.2%', pf='1.38', net='+$13,048 at $100 risk per trade',
             source='MT4 backtest v1.03 2020-01-02 to 2026-06-12, 3,132 trades')
BT104 = dict(direction='—', days='70.2% green / 99.5% traded', perday='2.18', win='79.0%', pf='1.41', net='+$18,414 at $100 risk per trade',
             source='MT4 backtest v1.04 (his run 22 Oct) 2020-01-02 to 2026-06-12, 3,673 trades')
BT105 = dict(direction='—', days='70.3% green / 99.5% traded', perday='2.18', win='79.1%', pf='1.42', net='+$18,595 at $100 risk per trade',
             source='MT4 backtest v1.05 (his run 22 Oct) 2020-01-02 to 2026-06-12, 3,668 trades')
BT106 = dict(direction='—', days='68.9% green / 99.5% traded', perday='3.78', win='86.3%', pf='1.40', net='+$19,269 at $100 risk per trade',
             source='MT4 backtest v1.09 HAM(hour7) (his run 3 Nov) 2020-01-02 to 2026-10-09, 6,656 trades')
BT107 = dict(direction='—', days='68.9% green / 99.5% traded', perday='3.78', win='86.4%', pf='1.42', net='+$20,021 at $100 risk per trade',
             source='MT4 backtest v1.11 WGAP (his run 5 Nov) 2020-01-02 to 2026-10-09, 6,680 trades')
BACKTEST = BT107
def set_rules(day):
    """v1.07 from V107_FROM, v1.06 from V106_FROM, v1.05 from V104_FROM, v1.03 before (engine switches + card labels)."""
    global RULES, BACKTEST
    d = str(pd.Timestamp(day).date())
    Y.HA_TARGET = 0.03 if d >= V104_FROM else 0.0; Y.FLIP = d >= V104_FROM; Y.FLIP_MAX = 1; Y.HAM_HOUR = 7 if d >= V106_FROM else -1
    Y.WGAP_ON = d >= V107_FROM
    RULES = 'v1.07' if d >= V107_FROM else ('v1.06' if d >= V106_FROM else ('v1.05' if d >= V104_FROM else 'v1.03'))
    BACKTEST = BT107 if d >= V107_FROM else (BT106 if d >= V106_FROM else (BT105 if d >= V104_FROM else BT103))

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
    global SKIPPED
    t0, end = to_utc(start_b), to_utc(end_b); out = []; SKIPPED = 0
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
        else: SKIPPED += 1                    # 400/404 = no prices in that chunk (weekend - or a Capital.com hiccup): counted for the log
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

SKIPPED = 0                           # chunks the last minutes() call got no prices for (400/404)

def arrays(b):
    return b.index.values.astype('datetime64[s]').astype(np.int64), b.o.values, b.h.values, b.l.values, b.c.values

# 23 Oct fix: a finished day is saved only when it is reasonably complete; otherwise the history does not advance and the next run retries
EXP_MIN = 1373                        # window minutes 01:05-23:57 on a full weekday (his MT4 data 2025-26: median 1,373 every weekday)
COMPLETE = 0.85                       # a day counts as complete at >= 85% of that weekday's usual minute count
TRIES, TRY_SECS = 3, 1800             # an empty / short download is accepted (holiday / short day) only after 3 tries spread over >= 30 min
STALE_SECS, GAP_MIN, LOOK_MIN = 180, 3, 60   # today: newest closed minute older than 3 min, or > 3 missing minutes in the last 60 = feed error

def usual_minutes(H, wd):
    """Usual window-minute count for weekday `wd` (0 = Monday): median of the last 10 complete days stored, else EXP_MIN."""
    v = [n for d, n in sorted((H.get('nmin') or {}).items()) if pd.Timestamp(d).dayofweek == wd][-10:]
    return float(np.median(v)) if len(v) >= 3 else float(EXP_MIN)

def tried_enough(H, key):
    """Counts one more try for day `key`; True once there were >= TRIES tries spread over >= TRY_SECS."""
    t = H.setdefault('tries', {}).setdefault(key, [0, time.time()]); t[0] += 1
    return t[0] >= TRIES and time.time() - t[1] >= TRY_SECS

def catch_up(feed, H, day):
    """Add every finished broker day after H['through'] and before `day` to the history, from Capital.com minutes - but only when the
    day has >= 85% of its usual window minutes. A short or empty download does NOT advance the history: the next run retries. After
    3 tries over >= 30 min the day is taken as it is: from Capital.com hourly bars if they cover more hours, else the minutes
    (short day), or - with no prices at all - as a holiday. Returns (added, waiting) - waiting = why the history is not up to date yet."""
    last = pd.Timestamp(H['through']); added = []; H.setdefault('nmin', {})
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1); key = str(nxt.date())
        if nxt.dayofweek < 5:
            b = minutes(feed, nxt, nxt + pd.Timedelta(days=1)); b = b[(b.index >= nxt) & (b.index < nxt + pd.Timedelta(days=1))]
            dd, hh = Y.history(*arrays(b)); how = 'minutes'
            nwin = int(sum(Y.inwin(x) for x in arrays(b)[0])); usual = usual_minutes(H, nxt.dayofweek)
            if nwin >= COMPLETE * usual: H['nmin'][key] = nwin
            elif not tried_enough(H, key):
                return added, f"{key}: {nwin} of ~{usual:.0f} minutes so far - retrying (try {H['tries'][key][0]} of {TRIES})"
            else:
                h1 = feed.bars('HOUR', *(pd.Timestamp(x) for x in ((nxt - pd.Timedelta(hours=7)).tz_localize(F.NY).tz_convert('UTC').tz_localize(None),
                                                                     (nxt + pd.Timedelta(hours=17)).tz_localize(F.NY).tz_convert('UTC').tz_localize(None))),
                               pd.Timedelta(hours=30), EPIC)
                h1 = h1[(h1.index >= nxt + pd.Timedelta(hours=1)) & (h1.index < nxt + pd.Timedelta(days=1))]
                if len(h1) > len(hh):
                    hh = [(secs(t), float(r.o), float(r.h), float(r.l), float(r.c)) for t, r in h1.iterrows()]
                    dd = [(secs(nxt), hh[0][1], max(x[2] for x in hh), min(x[3] for x in hh), hh[-1][4])]; how = 'hourly bars'
                elif dd: how = f'short day, {nwin} minutes'
            if dd:
                H['days'].append([key, *dd[0][1:]]); H['hours'] += [[str(ts(x[0]))[:16], *x[1:]] for x in hh]
                added.append(key + ('' if how == 'minutes' else f' ({how})'))
            else:
                added.append(key + f' (no prices after {TRIES} tries over {TRY_SECS // 60} min - holiday)')
            H.get('tries', {}).pop(key, None)
        last = nxt; H['through'] = key
    H['days'] = H['days'][-Y.KEEP_DAYS:]; H['hours'] = H['hours'][-Y.KEEP_HOURS:]
    H['nmin'] = dict(sorted(H['nmin'].items())[-40:])
    return added, None

def feed_health(b, now, day):
    """Today's minutes good enough to trade on? (ok, why). Checked only inside the window (01:05-23:57 broker, Mon-Fri):
    newest closed minute older than 3 min, > 3 missing minutes in the last 60, or < 85% of today's window minutes so far = not ok."""
    n = secs(now); d0 = secs(day)
    if not (Y.inwin(n) and Y.inwin(n - 240) and n - 240 >= d0): return True, ''
    T = arrays(b)[0]; tw = np.array([x for x in T if x >= d0 and Y.inwin(int(x))], np.int64)
    if not len(tw): return False, 'no USDJPY prices yet today (market closed?)'
    age = n - (int(tw[-1]) + 60)
    if age > STALE_SECS: return False, f'newest closed minute is {age // 60} min old'
    x = tw[tw >= n - LOOK_MIN * 60 - 60]
    if len(x) > 1 and np.diff(x).max() > (GAP_MIN + 1) * 60:
        return False, f'{int(np.diff(x).max()) // 60 - 1} minutes missing in the last {LOOK_MIN} min'
    want = (int(tw[-1]) - (d0 + 65 * 60)) // 60 + 1
    if want >= 30 and len(tw) < COMPLETE * want: return False, f'only {len(tw)} of {want} minutes today'
    return True, ''

def hold(why):
    """Keep the last good USDJPY card, with feed_error=True so the auto-trader leaves USDJPY alone this minute; journal untouched."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('USDJPY') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = (f"USDJPY prices not complete at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({why}) "
                    "— shows the last good update; checks again next minute.")
    mk['USDJPY'] = c; json.dump(old, open(PORTAL, 'w'), indent=1); print('USDJPY held:', why)

def main():
    global DEADLINE; DEADLINE = time.time() + 75                       # 22 Oct: own time budget per market (set when this market starts)
    now = F.broker_now(); day = now.normalize(); set_rules(day)
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
    try: added, wait = catch_up(feed, H, day)
    finally: json.dump(H, open(HIST, 'w'), separators=(',', ':'))     # retry counts are kept even if the run stops half way
    if wait: return hold('history not complete: ' + wait)
    b = minutes(feed, day - pd.Timedelta(hours=8), now); b = b[b.index + pd.Timedelta(minutes=1) <= now]      # closed minute bars only
    ok, why = feed_health(b, now, day)
    if not ok: return hold(why)
    T, O, Hh, L, C = arrays(b)
    eng = Y.Yen([[secs(d[0]), *d[1:]] for d in H['days']], [[secs(x[0]), *x[1:]] for x in H['hours']])
    d0, n0 = secs(day), secs(now)
    trades = eng.run_day(d0, T, O, Hh, L, C, now=n0) if len(b) else []          # 22 Oct: fixed 1.0-pip spread inside the engine (MT4 v1.05 test)
    hm = Y.FRI_CLOSE_HHMM if now.dayofweek == 4 else Y.CLOSE_HHMM
    eod = day + pd.Timedelta(hours=hm // 100, minutes=hm % 100)      # day-end close (6 pm broker since 2026-10-04)
    rows = [row(t, now >= eod) for t in trades]
    locked = bool(trades and trades[-1].get('locked_day'))
    # ---- journal: one record per broker day, replaced on every run of that day
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             atr_pips=round(eng.atr() * 100, 1), final=bool(now >= eod))], key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    json.dump(J, open(JOUR, 'w'), indent=1)
    # ---- page card
    tod = b[b.index >= day]; inw = tod[[Y.inwin(secs(t)) for t in tod.index]]
    last = float(tod.c.iloc[-1]) if len(tod) else None; first = float(inw.o.iloc[0]) if len(inw) else None
    sig_end = min(day + pd.Timedelta(hours=19), eod); last_sig = now >= sig_end
    if rows:
        side = rows[0]['side']; state = side.lower()
        side = rows[-1]['side'] if RULES != 'v1.03' else side
        msg = ((f"PAPER {side} day now. The 7am Heikin-Ashi trade closes whole at its tiny target; other trades close half at the ½ level, then the rest's stop "
                f"moves to the entry. A quiet breakout the other way closes open trades and switches the side (once a day). Everything closes at the {dubai(secs(eod))} Dubai close.")
               if RULES != 'v1.03' else
               (f"PAPER {side} day — later signals today are {side} only. Each trade closes half at its ½ level, then the rest's stop moves to the entry; "
                f"everything closes at the {dubai(secs(eod))} Dubai close.")) + (" Day lock hit: no more trades today." if locked else '')
    elif last_sig: state, msg = 'none', f"No paper trade today (new signals stop at {dubai(secs(sig_end))} Dubai)."
    else: state, msg = 'waiting', 'Waiting for the first signal.'
    spark = []
    if len(inw):
        g5 = inw[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()   # 5-min candles for the page: [time, close, open, high, low]
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 3), round(float(r.o), 3), round(float(r.h), 3), round(float(r.l), 3)] for t, r in g5.iterrows()]
    mk['USDJPY'] = dict(base_card(), state=state, message=msg, price=last, change_pips=(None if last is None or first is None else round((last - first) * 100, 1)),
                        atr_pips=round(eng.atr() * 100, 1), entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False,
                        live_spread_pips=(round(float(np.nanmedian(tod.sp.values[-30:])) * 100, 1) if len(tod) and np.isfinite(tod.sp.values[-30:]).any() else None),
                        history_note=f"history to {H['through']} ({len(H['days'])} days)" + (f" · added {', '.join(added)}" if added else ''))
    json.dump(old, open(PORTAL, 'w'), indent=1)
    print(f'USDJPY paper: {now} broker | trades today {len(rows)} | bars {len(b)} (empty chunks {SKIPPED}) | history to {H["through"]} | added {added}')

def base_card():
    if RULES == 'v1.07':
        note = ('stop: quiet signals ¼ of the 14-day range, others ¾ · Heikin-Ashi 7am (⅓ size) closes WHOLE at +0.03 x risk, and fires again at '
                'broker hour 7 (same ⅓-size tiny target, added v1.06) · others close half at +0.5 x risk (quiet) / +0.1 x risk, then the rest closes at the entry · '
                'a quiet breakout against the day closes open trades and switches the side (max once a day) · weekend-gap fade (full size, added v1.07): fades the '
                'Friday-close-to-Monday-open gap once a week, own stop (0.60 x range) and own tiny target (+0.03 x risk, closes WHOLE), and is EXEMPT from the '
                "breakout-flip above - it only ever exits via its own stop, its own target, or the day's close · "
                'day lock: once the day reaches +2R, close all at +1R, no more trades · one trade per minute · close 6:00 pm broker (Fridays 2:00 pm)')
    elif RULES == 'v1.06':
        note = ('stop: quiet signals ¼ of the 14-day range, others ¾ · Heikin-Ashi 7am (⅓ size) closes WHOLE at +0.03 x risk, and fires again at '
                'broker hour 7 (same ⅓-size tiny target, added v1.06) · others close half at +0.5 x risk (quiet) / +0.1 x risk, then the rest closes at the entry · '
                'a quiet breakout against the day closes open trades and switches the side (max once a day) · '
                'day lock: once the day reaches +2R, close all at +1R, no more trades · one trade per minute · close 6:00 pm broker (Fridays 2:00 pm)')
    elif RULES != 'v1.03':
        note = ('stop: quiet signals ¼ of the 14-day range, others ¾ · Heikin-Ashi 7am (⅓ size) closes WHOLE at +0.03 x risk · others close half at +0.5 x risk (quiet) / '
                '+0.1 x risk, then the rest closes at the entry · a quiet breakout against the day closes open trades and switches the side (max once a day) · '
                'day lock: once the day reaches +2R, close all at +1R, no more trades · one trade per minute · close 6:00 pm broker (Fridays 2:00 pm)')
    else: note = ('stop: quiet signals ¼ of the 14-day range, others ¾ · close half at +0.5 x risk (quiet) / +0.1 x risk (others), then the rest closes at the entry · '
            'day lock: once the day reaches +2R, close all at +1R, no more trades · one trade per minute · Heikin-Ashi 7am at ⅓ size · '
            'close 6:00 pm broker (Fridays 2:00 pm)')
    return dict(code='USDJPY', name='USD/JPY', symbol='USD/JPY', live=False, paper=True, status='Paper', version=RULES, lots=LOTS,
                stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note=f'This page tracks whether live USD/JPY signals do as well as the {RULES} backtest. Decision after about 3 months.',
                cost_note="Pips are for the whole trade (⅓-size trades count one third), after a fixed 1.0-pip spread (as in the MT4 test; fixed so shown levels never change). $ = at $100 risk per full-size trade, like the MT4 test.",
                net_label=f'Net R / $ at $100 risk ({RULES} sizes)')

def row(t, day_over):
    st = t['status']
    if st == 'open' and day_over: st = 'close_now'
    rs = None if t['r'] is None else round(t['r'] * t['w'], 3)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', sig=t['sig'], name=t['name'], price=t['px'], entry=t['entry'],
                stop=t['stop'], stop0=t['stop0'], stop_pips=t['stop_pips'], half_px=t['half_px'], half=t['half'], part=t.get('part', 0.5),
                half_time=None if t['half_t'] is None else dubai(t['half_t']), size=t['size'], quiet=t['quiet'], first=t['first'], status=st,
                exit=t['exit'], exit_time=None if t['exit_t'] is None else dubai(t['exit_t']), pips=t['pips'],
                usd=None if t['pips'] is None else round(t['pips'] * LOTS * 1000 / t['px'], 2), r=t['r'], r_sized=rs,
                usd_risk=None if rs is None else round(rs * Y.RISK_USD, 2), r_now=t['r_now'], rwf=t['rwf'], spread=t['spread_pips'])

def summary(J, day=None):
    """Paper record of the CURRENT rules only; days of older rules (v1.01, v1.03) stay in the journal but are not mixed in."""
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    J = dict(start=D3[0]['date'], days=D3)
    allt = [t for d in J.get('days', []) for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]; pp = [t['pips'] for t in allt if t.get('pips') is not None]
    usd = [t['usd'] for t in allt if t.get('usd') is not None]; rr = [t['r_sized'] for t in allt if t.get('r_sized') is not None]
    end = str((day or pd.Timestamp(J['days'][-1]['date'])).date()) if J.get('days') else J['start']
    wd = max(1, len(pd.bdate_range(J['start'], end))); tdays = sum(1 for d in J['days'] if d['trades'])
    gp, gl = sum(p for p in pp if p > 0), -sum(p for p in pp if p < 0)
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), decided=len(dec),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(pp), win=(round(100 * sum(p > 0 for p in pp) / len(pp), 1) if pp else None), pf=(round(sum(x for x in rr if x > 0) / -sum(x for x in rr if x < 0), 2) if any(x < 0 for x in rr) else None), pf_pips=(round(gp / gl, 2) if gl > 0 else None),
                net_pips=round(sum(pp), 1) if pp else None, net_usd=round(sum(usd), 2) if usd else None, rules=RULES,
                net_r=round(sum(rr), 2) if rr else None, net_usd_risk=round(sum(rr) * Y.RISK_USD, 2) if rr else None,
                green=round(100 * sum(1 for d in J['days'] if sum(t.get('r_sized') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J):
    return J.get('days', [])[-30:][::-1]

def fail(e):
    """Keep the last good USDJPY card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('USDJPY') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting')
    c['feed_error'] = True
    c['message'] = f"USDJPY paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every 5 minutes."
    mk['USDJPY'] = c; json.dump(old, open(PORTAL, 'w'), indent=1)
