"""Brent Oil PAPER signals for the page - BRENT v1.04 rules (brent_engine.py; MT4-proven 6 Nov 2026, his run: 754
trades 2018-01..2026-10, +$44,702 at 0.30 lot, PF 1.47, max DD $8,162, 56% closed in profit, spread 8 = $0.08/bbl).
SIGNALS ONLY: his standing instruction 6 Nov "don't focus on auto trading we are building this for trading dashboard
not for auto trading the EA is only for back testing" - never copied to the Capital.com demo (not in autotrade.py).
Called by run.py every minute, after the other markets. Each run: (1) a rolling ~95-day Capital.com HOUR-bar history
(docs/brent_daily.json: per broker day h, l, and the 10:00->14:00 move for rule A's 60-day spread) is kept up to date,
fetched once a day; (2) today's Capital.com minute bars (bid + spread) feed brent_engine.run_day() - 0 to 3 independent
trades a day (rules A/B/C/D, same stop, same 21:30 exit); (3) docs/journal_brent.json (every paper trade) and
docs/data.json -> markets.BRENT (the page). Source of truth: Archive Trading/BRENT/BRENT_v104_DASHBOARD_SPEC.txt."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, brent_engine as E
DEADLINE = time.time() + 240          # loop.py resets this every minute; Brent never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
JOUR = os.path.join(HERE, 'docs', 'journal_brent.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
HIST = os.path.join(HERE, 'docs', 'brent_daily.json'); HIST_KEEP = 150     # days kept (rule A's 60-day spread + headroom)
EPIC = os.environ.get('CAPITAL_EPIC_BRENT', 'OIL_BRENT')                  # NOT yet confirmed live - see brent_run.fail() note
MIN_SPREAD = 0.02                     # the paper result never uses less than 2 cents a barrel
RULES = 'v1.04'
PASS = dict(pf=1.10, months=3)
BACKTEST = dict(direction='—', days='~30% of days (~1.5/week), 1.1 trades/trading day', perday='1.1', win='56% closed in profit', pf='1.47',
                net='+$44,702 at 0.30 lot (max drawdown $8,162)',
                source='MT4 BRENT_WED_HOL v1.04, his run 6 Nov 2026, 2018-01-01..2026-10-31, 754 trades, spread 8 ($0.08/bbl, RoboForex live spread); years 2018 +6,652 .. 2026 +974')

class FeedError(RuntimeError):
    pass

_DAILY = {}                            # today's daily history table (kept between minutes inside one desk job)

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

# ---------------- prices (same Capital.com pattern every market uses) ----------------
def to_utc(b): return (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)

def prices(feed, res, start_b, end_b, step):
    if feed.h is None: feed.login()
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('Brent time budget used up - next run continues')
        t1 = min(end, t0 + step)
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC}', headers=feed.h, timeout=20,
                         params={'resolution': res, 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid']))
        elif r.status_code not in (400, 404): r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def minutes(feed, start_b, end_b): return prices(feed, 'MINUTE', start_b, end_b, pd.Timedelta(minutes=900))
def daily(feed, day):
    """Per-broker-day h/l + the 10:00->14:00 move (rule A), from the last ~95 days of HOUR bars (days before today)."""
    h = prices(feed, 'HOUR', day - pd.Timedelta(days=95), day, pd.Timedelta(hours=900))
    h = h[h.index < day]
    if not len(h): return pd.DataFrame(columns=['h', 'l', 'm1014'])
    d = h.groupby(h.index.normalize()).agg(h=('h', 'max'), l=('l', 'min'))
    o10 = h[(h.index.hour == 10) & (h.index.minute == 0)].o; o10.index = o10.index.normalize()
    o14 = h[(h.index.hour == 14) & (h.index.minute == 0)].o; o14.index = o14.index.normalize()
    d['m1014'] = (o14.reindex(d.index) - o10.reindex(d.index)); return d

def hist_merge(fresh, day):
    """docs/brent_daily.json rows + the freshly fetched days (fresh wins) -> DataFrame h, l, m1014 (days before today).
    Saved back once a day so the file keeps growing (same pattern as gbp_daily.json)."""
    H = loadj(HIST, {}); rows = {r[0]: r for r in H.get('days', [])}
    if fresh is not None and len(fresh):
        for t, r in fresh.dropna(subset=['h', 'l']).iterrows():
            if pd.Timestamp(t) < day:
                m = r.get('m1014'); rows[str(pd.Timestamp(t).date())] = [str(pd.Timestamp(t).date()), round(float(r.h), 3), round(float(r.l), 3), (None if pd.isna(m) else round(float(m), 3))]
    R = sorted(rows.values())[-HIST_KEEP:]
    if H.get('saved') != str(day.date()) and fresh is not None and len(fresh):
        H['days'] = R; H['saved'] = str(day.date()); dumpj(H, HIST)
    d = pd.DataFrame([r[1:] for r in R], index=pd.to_datetime([r[0] for r in R]), columns=['h', 'l', 'm1014'], dtype=float)
    return d[d.index < day]

def feed_check(b, now):
    """None if today's closed bars look fresh, else the reason (01:00-23:30 broker only, same window as gbp_run)."""
    hm = now.hour * 60 + now.minute
    if hm < 60 or hm > 23 * 60 + 30: return None
    if not len(b): return 'no price bars received for today'
    age = now - (b.index[-1] + pd.Timedelta(minutes=1))
    if age > pd.Timedelta(minutes=5): return f'newest closed price bar ({dubai(b.index[-1])} Dubai) is {age.total_seconds() / 60:.0f} min old'
    return None

# ---------------- page rows / journal ----------------
def row(t):
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], rule=t['rule'],
                price=round(t['entry'], 2), entry=round(t['entry'], 2), stop=round(t['stop'], 2), stop0=round(t.get('stop0', t['stop']), 2),
                stop_usd=round(abs(t['entry'] - t.get('stop0', t['stop'])), 2), status=t['status'], size='full', part=1.0, half=False,
                exit=None if t['exit'] is None else round(t['exit'], 2), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=None if t.get('res') is None else round(t['res'], 3), res_sized=None if t.get('res') is None else round(t['res'], 3))

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t['res'] for t in allt if t.get('res') is not None]
    start = D3[0]['date']; end = str((day or pd.Timestamp(D3[-1]['date'])).date())
    wd = max(1, len(pd.bdate_range(start, end))); tdays = sum(1 for d in D3 if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(start).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 2) if rr else None, rules=RULES, direction=None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('res') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card():
    note = ('STOP 1.0 x 20-day average daily range, no target · exit 21:30 broker (Dubai: see the trade times) if not stopped first · '
            'rules can fire together the same day (separate trades, same stop/exit): A) Wednesday - 10:00→14:00 move > 0.5x its own 60-day spread, trade that '
            'direction at 14:00 · B) SELL 10:00 the first trading day after a US federal holiday · C) 20-day range break - price inside the range at 10:00, '
            'first 1-min close beyond it 10:00-19:00, follow · D) BUY 10:00 on a UK bank holiday the market trades, SELL 10:00 the next trading day')
    return dict(code='BRENT', name='Brent Oil', symbol='BRENT · Capital.com Brent Oil Future', live=False, paper=True, status='Paper', version=RULES,
                unit='usd', dp=2, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live Brent signals do as well as the v1.04 MT4 test. Copied to the Capital.com DEMO account by the auto-trader, same as Gold/USDJPY/Oil/Nasdaq/S&P (his 6 Nov go-ahead, reversing his earlier same-day "signals only" instruction). Decision after about 3 months.',
                cost_note='Results are $ per barrel (0.30-lot backtest scale), from the signal price after the live Capital.com spread (at least 2 cents).',
                net_label=f'Net $ per barrel ({RULES})')

def main(feed=None, get=None, getd=None, now=None):
    global DEADLINE; DEADLINE = time.time() + 75           # own 75s time budget per market
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    dt = E.day_type(day)
    if now.dayofweek >= 5:
        prev = mk.get('BRENT') or {}
        mk['BRENT'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(), state='closed', message='Market closed for the weekend.',
                           entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('Brent: weekend'); return
    get = get or minutes; getd = getd or daily
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('Brent paper needs the Capital.com prices')
        feed = F.Capital()
    if _DAILY.get('day') != str(day.date()):               # daily history fetched once a day (hourly bars)
        _DAILY.update(day=str(day.date()), d=getd(feed, day))
    dd = hist_merge(_DAILY['d'], day)
    A = E.adr(dd, day); hi, lo = E.channel(dd, day)
    sd = E.move_std(dd['m1014'], day) if 'm1014' in dd else float('nan')
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]
    bad = feed_check(b, now)
    if bad: raise FeedError(bad)
    sp = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else 0.0
    cost = max(MIN_SPREAD, sp)
    trades = E.run_day(b, day, dt, A, hi, lo, sd, cost=cost) if (len(b) and np.isfinite(A)) else []
    rows = [row(t) for t in trades]
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             range_usd=(None if not np.isfinite(A) else round(A, 2)), ruleB=dt['ruleB'], ruleD_buy=dt['ruleD_buy'], ruleD_sell=dt['ruleD_sell'], wed=dt['wed'])],
                       key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    rule_tags = [t['rule'] for t in trades]
    if not np.isfinite(A): state, msg = 'none', 'No trade: fewer than 20 days of price history for the average range yet.'
    elif rows:
        sides = ', '.join(f"{r['side']} ({r['rule']})" for r in rows)
        state = 'mixed' if len(set(r['side'] for r in rows)) > 1 else rows[0]['side'].lower()
        msg = f"Today's signals: {sides}. Stop at 1.0 x the 20-day range, no target; closes at 9:30 pm Dubai winter (8:30 pm summer) if not stopped first."
    elif dt['wed']: state, msg = 'waiting', "Wednesday - checking the 10:00→14:00 move against its 60-day spread at 2:00 pm broker."
    else: state, msg = 'none', 'No Brent signal today (not a Wednesday, US-holiday day-after, UK bank holiday, or 20-day range break).'
    if dt.get('list_expiring'): msg += ' (Rule B/D holiday dates run out soon - the Brent chat needs to extend the EA\'s baked-in lists.)'
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 2), round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2)] for t, r in g5.iterrows()]
    mk['BRENT'] = dict(base_card(), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 2)),
                       entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC,
                       range_usd=(None if not np.isfinite(A) else round(A, 2)), rule_today=dict(wed=dt['wed'], ruleB=dt['ruleB'], ruleD_buy=dt['ruleD_buy'], ruleD_sell=dt['ruleD_sell']))
    dumpj(old, PORTAL, indent=1)
    print(f'Brent paper: {now} broker | bars {len(b)} | A {round(A,2) if np.isfinite(A) else None} | trades today {len(rows)} | rules {rule_tags}')

def fail(e):
    """Keep the last good Brent card and say what failed. NOTE: EPIC='OIL_BRENT' (env CAPITAL_EPIC_BRENT overrides it)
    is the WTI-style naming guess (matches OIL_CRUDE's convention) - not yet confirmed against the live Capital.com
    account (no API access from the build session); a wrong epic shows up here as a 400/404 feed error, not silently
    wrong prices - check this message once live and fix the epic (one line) if it names the wrong instrument."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('BRENT') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"Brent paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute. (If this persists, the Capital.com epic '{EPIC}' may be wrong - tell the Trading Dashboard chat.)"
    mk['BRENT'] = c; dumpj(old, PORTAL, indent=1)
