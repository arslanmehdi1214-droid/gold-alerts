"""v1.12W (19 Nov 2026): + WATCH rules W1-W4, DEMO / FORWARD TEST ONLY, live v1.10 rules untouched (his instruction "Add Brent watch
rules W1-W4 ... Demo only, keep live v1.10 unchanged"; source BRENT_v112W_DASHBOARD_SPEC.txt + BRENT_WED_HOL_v112W.mq4, md5
54564281efc512dbe26015fd353aa326). Watch trades live in their OWN journal (docs/journal_brent_watch.json, history entry 'Brent watch
(demo)') so the live Brent journal/totals never mix with them; they ARE in markets.BRENT.entries so the page shows them and the demo
auto-trader copies them like any other Brent trade (own tags WM4/WM1/WEU/WN150, same-day, closed 21:30 broker). W4 needs 150 daily
21:29 broker closes: built from the same Capital.com minute feed into docs/brent_close.json (a few days per run until complete; W4
sits out and the card says "warming up" until then). RULES below stays 'v1.10' on purpose: it tags the LIVE journal days.
Brent Oil PAPER signals for the page - BRENT v1.10 rules: live v1.07a (A-F unchanged, brent_engine.py; rule G
dropped - his 8 Nov decision: "drop rule G completely... push v1.06 with rules A-F only... no changes to
autotrade.py" - PLUS rule K+ added 9 Nov 2026 on top) PLUS two more new rules added 9 Nov 2026 on top of THAT, his
explicit request ("keep A-F and K+ exactly as they are"): AW (Wednesday re-entry) and K2 (K+ add-on fade at HALF
size). Source: BRENT_v110_DASHBOARD_SPEC.txt + BRENT_WED_HOL_v110.mq4 (AW lines 508-516, K2 lines 482-488),
Archive Trading/BRENT. MT4 proof 9 Nov, full v1.10 EA: net +$81,158, PF 1.43, max drawdown $10,241, 1,492 trades
(v1.07a baseline +$67,704, DD $9,199, 1,241 trades, PF 1.43 - net per $1 of drawdown 7.92 vs 7.36, at equal
drawdown ~+7.7% net; v1.10 technically misses the strict $10,000 max-DD cap by $241 but wins on the equal-drawdown
rule, his go-ahead 9 Nov 2026). AW+K2 add 251 trades (AW 210 at full size, K2 41 at half size) = +$13,453, shown on
the card as "new, 2022-heavy" (see AWK2_BACKTEST / awk2Block() below) - A-F and K+ themselves are UNCHANGED; see
their own backtest numbers below, carried over as-is.
MT4 proof for the FULL v1.06 bundle (A-F + G), his run 7 Nov 2026: 949 trades 2018-01..2026-10 on 851 days
(~1.9/week), +$58,856 at 0.30 lot, PF 1.46, max DD $9,529, 55.2% closed in profit, spread 8 = $0.08/bbl. That
number is NOT this build's (G added real trades/profit) - the closer like-for-like reference is v1.05's own A-F
result: 911 trades, +$50,198, DD $7,979, PF 1.47, 55% closed in profit (same window, same spread; only losing year
2019 -$2,598). By simple subtraction (not a separate MT4 run) G alone accounted for ~38 trades / ~$8,658 of the
v1.06 bundle total. The v1.06 changes THIS build does carry - B/D entry 11:00 broker (was 10:00), rule C watching
from 09:00 broker (was 10:00) with its own 2.0x stop (was 1.0x, shared with the others), and the new conflict-close
rule - were only ever MT4-tested bundled together with G, never in isolation; the live paper journal is the first
real read of them alone. Rule K+ (v1.07a, new): own MT4 run, isolated - 9 Nov 2026, 2018.01.02-2026.10.30, spread 8,
0.30 lot: 285 trades, 0 stop hits, 52% closed in profit, net +$7,716 (full v1.07a EA incl. K+: +$67,704, 1,241
trades vs v1.06 full EA +$58,856/949). K+ by year ($): 2018 -90, 2019 -798, 2020 -657, 2021 +1578, 2022 -1581,
2023 +1971, 2024 +1254, 2025 -1017, 2026 +7056 - most of the edge is 2026: shown on the card as "new, thin before
2026", see KPLUS_BACKTEST/kfade_card() below. Source: BRENT_v107a_DASHBOARD_SPEC.txt + BRENT_WED_HOL_v107a.mq4
(K+ block lines 423-441), Archive Trading/BRENT.
Copied to the Capital.com DEMO account by autotrade.py (his 6 Nov go-ahead, given later the same day as his earlier
"signals only, EA is backtest only" instruction - the go-ahead is what stands; autotrade.py's own MARKETS['BRENT']
entry confirms it, verified against live main 8 Nov when this v1.06 port was built). Dropping rule G avoided a real
problem found while building this: autotrade.py's watchdog force-closes any demo position held past one broker day
("left over from an earlier day") plus its own fixed 21:30 day-end close - incompatible with a multi-day hold like
G would have been, so G would have been wrongly closed early on the demo the day after opening. A-F all still close
same-day (21:30 broker), so none of that applies to this build; autotrade.py itself is untouched.
Called by run.py every minute, after the other markets. Each run: (1) a rolling ~95-day Capital.com HOUR-bar history
(docs/brent_daily.json: per broker day h, l, and the 10:00->14:00 move for rule A's 60-day spread) is kept up to date,
fetched once a day; (2) today's Capital.com minute bars (bid + spread) feed brent_engine.run_day() - 0 to N
independent trades a day (rules A-F, conflict-closed - an opposite signal closes an already-open trade and is
itself skipped); (3) docs/journal_brent.json (every paper trade) and docs/data.json -> markets.BRENT (the page).
Source of truth: Archive Trading/BRENT/BRENT_v106_DASHBOARD_SPEC.txt."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, brent_engine as E
DEADLINE = time.time() + 240          # loop.py resets this every minute; Brent never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
JOUR = os.path.join(HERE, 'docs', 'journal_brent.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
HIST = os.path.join(HERE, 'docs', 'brent_daily.json'); HIST_KEEP = 150     # days kept (rule A's 60-day spread + headroom)
EPIC = os.environ.get('CAPITAL_EPIC_BRENT', 'OIL_BRENT')                  # NOT yet confirmed live - see brent_run.fail() note
MIN_SPREAD = 0.02                     # the paper result never uses less than 2 cents a barrel
RULES = 'v1.10'                       # LIVE rule version: tags the live journal days (watch rules do NOT change it)
VERSION_LABEL = 'v1.10 + watch v1.13W'  # shown on the card
WRULES = 'v1.13W'
JOURW = os.path.join(HERE, 'docs', 'journal_brent_watch.json')       # watch trades only (DEMO forward test)
CLOSEF = os.path.join(HERE, 'docs', 'brent_close.json')              # daily 21:29 broker closes for W4
CLOSE_BACK_DAYS = 240; CLOSE_MAX_NONE = 12   # calendar days of closes kept/required; more empty weekdays than this = minute history unusable
PASS = dict(pf=1.10, months=3)
BACKTEST = dict(direction='—', days='~35% of days (~1.7/week)', perday='1.3', win='55% closed in profit', pf='1.47',
                net='+$50,198 at 0.30 lot (max drawdown $7,979) - v1.05\'s A-F result (last MT4 number for A-F alone)',
                source='MT4 BRENT_WED_HOL v1.05 (A-F only), his run 7 Nov 2026, 2018-01-02..2026-10-30, 911 trades, spread 8 ($0.08/bbl, RoboForex live spread); only losing year 2019 (-$2,598). '
                       'The v1.06 MT4 run (same window) tested the FULL bundle incl. dropped rule G: 949 trades, +$58,856, DD $9,529 - by subtraction (not a separate run) G alone was ~38 trades / '
                       '~$8,658 of that. This build\'s own v1.06 deltas (B/D entry 11:00, rule C from 09:00 with its own 2.0x stop, conflict-close) were only MT4-tested bundled with G, never alone.')
# v1.07a, new 9 Nov 2026: rule K+ (overextension fade) added on top of the live A-F build above (A-F unchanged).
# Its own isolated MT4 proof - shown on the card as "new, thin before 2026" per his explicit instruction, since
# almost all of the net comes from 2026 and six of the eight prior years are flat-to-negative.
KPLUS_BACKTEST = dict(trades=285, stops=0, win=52, net=7716,
                      by_year=[['2018', -90], ['2019', -798], ['2020', -657], ['2021', 1578], ['2022', -1581],
                               ['2023', 1971], ['2024', 1254], ['2025', -1017], ['2026', 7056]],
                      note='New, thin before 2026 - most of the edge is 2026; 2018-2025 net is -$324 (6 of 8 years negative).',
                      source='MT4 BRENT_WED_HOL_v107a.mq4, his run 9 Nov 2026, 2018.01.02-2026.10.30, spread 8 ($0.08/bbl), 0.30 lot - K+ alone: 285 trades, '
                             '0 stop hits, all closed 19:00 broker, 52% closed in profit, net +$7,716. Full v1.07a EA incl. K+: +$67,704, 1,241 trades (v1.06 full EA was +$58,856, 949). '
                             'Python mirror predicted the same 285 trades.')
# v1.10, new 9 Nov 2026: rules AW (Wednesday re-entry) + K2 (K+ add-on fade at HALF size) added on top of the live
# v1.07a build above (A-F and K+ themselves unchanged - see BACKTEST/KPLUS_BACKTEST above, carried over as-is).
# Shown together on the card as "new, 2022-heavy" per his explicit instruction, since $5,596 of the combined
# $13,453 extra (42%) is 2022 alone. No separate win%/stop-hit count was given for the combined pair, so none is
# shown here (never guess a number that wasn't MT4-confirmed).
AWK2_BACKTEST = dict(trades=251, aw_trades=210, k2_trades=41, net=13453,
                     by_year=[['2018', 1863], ['2019', -860], ['2020', 2999], ['2021', 753], ['2022', 5596],
                              ['2023', -632], ['2024', 1071], ['2025', -551], ['2026', 3213]],
                     note='New, 2022-heavy - $5,596 of the $13,453 extra (42%) is 2022 alone; 6 of 9 years positive.',
                     source='MT4 BRENT_WED_HOL_v110.mq4, his run 9 Nov 2026, 2018.01.02-2026.10.30, spread 8 ($0.08/bbl) - AW+K2 together: 251 trades '
                            '(AW 210 at full 0.30 lot, K2 41 at half 0.15 lot), net +$13,453. Full v1.10 EA (A-F+K++AW+K2): +$81,158, PF 1.43, max '
                            'drawdown $10,241, 1,492 trades vs the v1.07a baseline +$67,704, DD $9,199, 1,241 trades, PF 1.43 (net per $1 of drawdown '
                            '7.92 vs 7.36 - at equal drawdown ~+7.7% net). v1.10 technically misses the strict $10,000 max-DD cap by $241 but wins on '
                            'the equal-drawdown rule - his go-ahead 9 Nov 2026.')

# v1.13W, 21 Nov 2026: W5 added (tag WLTD4, BUY 10:00 broker the day before ICE Brent options expiry, stop 1.0x, close 21:30; see brent_engine.py).
# v1.12W, 19 Nov 2026: WATCH rules W1-W4 (demo forward test only). MT4 proof = his run 19 Nov (BRENT M1 every tick, spread 8, 0.30 lot,
# 2018-01-02..2026-10-30, order fails 0). None of the four has a target - they close on time -> show "% closed in profit", never "% hit target".
# Python replay of the same window on his M1 file (my check 19 Nov, not MT4): W1 106 trades +$1,442; W2 105 +$4,842; W3 44 +$2,922;
# W4 76 incl. 11 trades in the first 150 days of 2018 that the MT4 run could not take (its tester has no warm-up) - from Jul 2018: 65 trades +$4,015.
WATCH_BACKTEST = dict(
    full=dict(net=94121, pf=1.41, maxdd=9527, trades=1811, win=54.45), v110_part=dict(net=80891, trades=1491),
    rules=[dict(code='W1', tag='WM4', name='M4 month-end', side='BUY', trades=106, net=1441, win=52, y1=577, y2=864, note='weakest of the four'),
           dict(code='W2', tag='WM1', name='M1 first day of month', side='SELL', trades=104, net=4739, win=55, y1=2619, y2=2120),
           dict(code='W3', tag='WEU', name='EU-only holiday', side='SELL', trades=44, net=3187, win=53, y1=1273, y2=1914),
           dict(code='W4', tag='WN150', name='150-day close break', side='FOLLOW', trades=65, net=3863, win=55, y1=1270, y2=2594),
           dict(code='W5', tag='WLTD4', name='day before Brent options expiry', side='BUY', trades=106, net=4322, win=None, y1=None, y2=None,
                note='added 21 Nov 2026 - his MT4 run: +$4,322 on 106 trades, positive in both 2018-21 and 2022-26 (split not given)')],
    source='MT4 BRENT_WED_HOL_v112W.mq4 (md5 54564281efc512dbe26015fd353aa326), his run 19 Nov 2026, BRENT M1 every tick, spread 8, 0.30 lot, '
           '2018.01.02-2026.10.30: v1.12W full EA +$94,121, PF 1.41, max DD $9,527, 1,811 trades, 54.45% closed in profit; v1.10 part unchanged '
           '1,491 trades +$80,891. y1 = 2018-21, y2 = 2022-26. W5 (v1.13W, BRENT_WED_HOL_v113W.mq4 md5 775dc705c5db4d1440cab29d19454155): his MT4 run 21 Nov 2026, '
           '106 trades +$4,322, positive in both 2018-21 and 2022-26, rest of the engine unchanged (the full-EA totals above are the v1.12W run - no v1.13W full total was given). '
           'W5 Python check on his broker M1 file (my replay, not MT4): 53% closed in profit.',
    note='DEMO / FORWARD TEST ONLY - no target, they close on time (21:30 broker); % = closed in profit, not hit target. Live v1.10 rules unchanged.')

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

# ---------------- W4: daily 21:29 broker closes (v1.12W) ----------------
def day_close(feed, d):
    """The 21:29 close of broker day d = close (bid) of the last minute bar that STARTS before 21:30 broker (the EA's 'last price
    before the line-20 close time'; on an early-close day it is simply the last bar). None = no bars that day (market holiday)."""
    d = pd.Timestamp(d).normalize()
    b = prices(feed, 'MINUTE', d + pd.Timedelta(hours=19), d + pd.Timedelta(hours=21, minutes=30), pd.Timedelta(minutes=900))
    b = b[(b.index >= d) & (b.index < d + pd.Timedelta(minutes=E.EXIT_MIN))]
    return None if not len(b) else round(float(b.c.iloc[-1]), 3)

def daily_closes(feed, day, budget_s=30):
    """Keeps docs/brent_close.json up to date (a few days per run, newest first, own time budget) and returns
    dict(ready, have, missing, none, series). ready = every weekday of the last CLOSE_BACK_DAYS calendar days is fetched AND no more than
    CLOSE_MAX_NONE of them came back empty (a few holidays are normal; many would mean the minute history is too short - W4 must
    then sit out rather than run on a wrong 150-day window)."""
    day = pd.Timestamp(day).normalize()
    S = loadj(CLOSEF, {}); days = S.get('days', {}) if isinstance(S.get('days'), dict) else {}
    want = [str(d.date()) for d in pd.bdate_range(day - pd.Timedelta(days=CLOSE_BACK_DAYS), day - pd.Timedelta(days=1))]
    miss = [d for d in want if d not in days][::-1]          # newest first
    t_end = time.time() + budget_s; got = 0
    for d in miss:
        if time.time() > min(t_end, DEADLINE - 5): break
        try: c = day_close(feed, d)
        except TimeoutError: break
        except Exception as e: print('Brent W4 close fetch failed for', d, type(e).__name__, str(e)[:80]); continue    # tried again next run
        days[d] = c; got += 1
    if got:
        S['days'] = {k: v for k, v in days.items() if k >= want[0]}; S['saved'] = str(day.date()); dumpj(S, CLOSEF)
    left = [d for d in want if d not in days]; none = sum(1 for d in want if d in days and days[d] is None)
    ser = pd.Series({pd.Timestamp(k): v for k, v in days.items() if v is not None and k >= want[0]}, dtype=float).sort_index()
    return dict(ready=(not left) and none <= CLOSE_MAX_NONE, have=len(ser), missing=len(left), none=none, series=ser)

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
    # v1.10: K2 trades carry a NUMERIC size (E.K2_LOT_X = 0.5, half a normal trade) instead of the string 'full' -
    # autotrade.py's weight() reads a numeric size literally as the risk multiplier, so this is what actually
    # halves K2's real lot size/risk on the demo account (the stop distance itself is unchanged, see k2_trade()).
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], rule=t['rule'], tag=t.get('tag'),
                price=round(t['entry'], 2), entry=round(t['entry'], 2), stop=round(t['stop'], 2), stop0=round(t.get('stop0', t['stop']), 2),
                stop_usd=round(abs(t['entry'] - t.get('stop0', t['stop'])), 2), status=t['status'],
                size=(E.K2_LOT_X if t.get('tag') == 'K2' else 'full'), part=1.0, half=False,
                exit=None if t['exit'] is None else round(t['exit'], 2), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=None if t.get('res') is None else round(t['res'], 3), res_sized=None if t.get('res') is None else round(t['res'], 3),
                **(dict(demo=True, nostop=bool(t.get('nostop'))) if t['rule'] in E.WATCH_RULES else {}))

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

def watch_summary(JW):
    """Forward-test totals per watch rule from docs/journal_brent_watch.json: trades, closed, % closed in profit (never 'hit target'), net $/bbl."""
    out = {}
    for rk in E.WATCH_RULES:
        ts = [t for d in JW.get('days', []) for t in d['trades'] if t.get('rule') == rk]; rr = [t['res'] for t in ts if t.get('res') is not None]
        out[rk] = dict(trades=len(ts), closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), net=round(sum(rr), 2) if rr else None)
    allr = [t['res'] for d in JW.get('days', []) for t in d['trades'] if t.get('res') is not None]
    out['all'] = dict(trades=sum(v['trades'] for k, v in out.items()), closed=len(allr), win=(round(100 * sum(p > 0 for p in allr) / len(allr), 1) if allr else None),
                      net=round(sum(allr), 2) if allr else None)
    return out

def watch_next(now):
    """Next scheduled W1/W2/W3/W5 dates (today still counts while its entry time is ahead), with side and Dubai entry time, from the EA's own day lists."""
    day = now.normalize(); out = []
    for code, lst, em, side in (('W1', E.WATCH_M4_DAYS, E.M4_ENTRY_MIN, 'BUY'), ('W2', E.WATCH_M1_DAYS, E.M1_ENTRY_MIN, 'SELL'), ('W3', E.WATCH_EU_DAYS, E.EU_ENTRY_MIN, 'SELL'), ('W5', E.WATCH_LTD4_DAYS, E.LTD4_ENTRY_MIN, 'BUY')):
        nxt = [d for d in sorted(lst) if d + pd.Timedelta(minutes=em) > now and not (code == 'W3' and any(E.rule_flags(d)))]   # EA skips W3 on live calendar days
        if nxt:
            d = nxt[0]; t = d + pd.Timedelta(minutes=em)
            out.append(dict(rule=code, side=side, date=str(d.date()), label=F.broker_to_dubai(t).strftime('%a %-d %b ') + dubai(t)))
    return out

def base_card():
    note = ('STOP 1.0 x 20-day average daily range, no target (rule C: 2.0x) · exit 21:30 broker (Dubai: see the trade times) if not stopped first · '
            'rules can fire together the same day (separate trades, same stop/exit) - an opposite signal closes an already-open trade and is itself skipped: '
            'A) Wednesday - 10:00→14:00 move > 0.5x its own 60-day spread, trade that direction at 14:00 · B) SELL 11:00 the first trading day after a '
            'US federal holiday · C) 20-day range break - price inside the range at 09:00, first 1-min close beyond it 09:00-19:00, follow (stop 2.0x) · '
            'D) BUY 11:00 on a UK bank holiday the market trades, SELL 11:00 the next trading day · E) SELL 10:00 the 2nd trading day after a UK bank '
            'holiday · F) BUY 19:00 the trading day before a US federal or UK bank holiday · '
            'K+) NEW 9 Nov 2026, thin before 2026 - overextension fade: price 0.8x the 20-day range away from its own 09:00 or 10:00 broker price (first '
            'touch, before 18:00) -> fade back, stop 2.0x the range, exit 19:00 broker. Independent of A-F - its own position, never conflict-closed, '
            'skipped on Wednesday/calendar days or if rule C already opened today · '
            'AW) NEW 9 Nov 2026, 2022-heavy - Wednesday re-entry: only on rule A\'s own signal days; if price closes back through the 14:00 price within '
            '30 min AGAINST rule A\'s direction -> a 2nd trade IN rule A\'s direction, stop 2.0x the range, exit 21:30 broker · '
            'K2) NEW 9 Nov 2026, 2022-heavy - K+ add-on at HALF size: only after a K+ trade; if price runs a further 0.5x the range beyond K+\'s own '
            'trigger price in the same direction as the original stretch -> a 2nd fade, same direction as K+, HALF the normal size, stop 2.0x the range, '
            'exit 21:30 broker (not K+\'s own 19:00). AW and K2 are each independent of A-F/K+/each other - own position, never conflict-closed, skipped '
            'on calendar days (K2 also skips on Wednesday or if rule C already traded today) · '
            'WATCH W1-W5) NEW 19 Nov 2026 (W5 added 21 Nov), DEMO / FORWARD TEST ONLY, own positions, never conflict-closed, no target (close 21:30 broker): '
            'W1 BUY 15:00 on the 4th-last trading day of the month (no stop in the test; the demo order carries a far 2.0x safety stop) · '
            'W2 SELL 15:00 on the first trading day of the month (stop 2.0x) · W3 SELL 11:00 on a Germany/France-only holiday (stop 1.0x) · '
            'W4 follow the first daily 21:29 close beyond the last 150 closes, entry 03:20 broker (stop 1.0x) · '
            'W5 BUY 10:00 the day before Brent options expiry (stop 1.0x)')
    return dict(code='BRENT', name='Brent Oil', symbol='BRENT · Capital.com Brent Oil Future', live=False, paper=True, status='Paper', version=VERSION_LABEL, live_rules=RULES,
                unit='usd', dp=2, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live Brent signals do as well as the v1.05 MT4 test (this build\'s own v1.06 B/D/C/conflict-close deltas were '
                          'only MT4-tested bundled with the dropped rule G, never alone - see the backtest note). v1.07a (9 Nov 2026) added rule K+ on '
                          'top, unchanged A-F; K+ has its own isolated MT4 proof - new and thin before 2026, see the K+ panel. v1.10 (9 Nov 2026) adds '
                          'rules AW + K2 on top of THAT, A-F and K+ themselves unchanged - their own isolated MT4 proof is new and 2022-heavy, see the '
                          'AW+K2 panel (v1.10 technically misses the strict $10,000 max-drawdown cap by $241 but wins on the equal-drawdown rule - his '
                          'go-ahead 9 Nov 2026). Copied to the Capital.com DEMO account by the auto-trader, same as Gold/USDJPY/Oil/Nasdaq/S&P500/GBPUSD '
                          '(his 6 Nov go-ahead, reversing his earlier same-day "signals only" instruction); up to 3 Brent positions can be open at once '
                          '(e.g. A-F + K+ + K2, or A + C + AW) - autotrade.py\'s own per-trade keying already supports it, no autotrade.py change needed. '
                          'v1.12W (19 Nov 2026) adds four WATCH rules W1-W4 on top, DEMO forward test only, live v1.10 rules unchanged - own journal, see the watch panel; '
                          'v1.13W (21 Nov 2026) adds a fifth watch rule W5 (day before Brent options expiry, BUY), same demo-only treatment. '
                          'Decision after about 3 months.',
                cost_note='Results are $ per barrel (0.30-lot backtest scale, K2 at half that - 0.15 lot), from the signal price after the live Capital.com spread (at least 2 cents).',
                net_label=f'Net $ per barrel ({RULES})',
                kfade=dict(KPLUS_BACKTEST), awk2=dict(AWK2_BACKTEST), watch_backtest=dict(WATCH_BACKTEST))

def watch_block(JW, now, cl):
    """The card's 'watch' panel: forward-test totals, next scheduled W1/W2/W3/W5 trades, and W4's close history state (cl = daily_closes() result or None)."""
    w4 = None if cl is None else dict(ready=bool(cl['ready']), have=int(cl['have']), need=E.N150_DAYS + 2, missing=int(cl['missing']), empty=int(cl['none']))
    return dict(version=WRULES, label='DEMO / FORWARD TEST', summary=watch_summary(JW), next=watch_next(now), w4=w4, close=dubai(now.normalize() + pd.Timedelta(minutes=E.EXIT_MIN)))

def main(feed=None, get=None, getd=None, getc=None, now=None):
    global DEADLINE; DEADLINE = time.time() + 75           # own 75s time budget per market
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[])); JW = loadj(JOURW, dict(start=None, days=[]))
    dt = E.day_type(day)
    if now.dayofweek >= 5:
        prev = mk.get('BRENT') or {}
        wb = watch_block(JW, now, None); wb['w4'] = (prev.get('watch') or {}).get('w4')
        mk['BRENT'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(), state='closed', message='Market closed for the weekend.',
                           entries=[], journal=summary(J), jdays=jdays(J), feed_error=False, watch=wb)
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
    cl = None                                              # v1.12W: W4's daily 21:29 closes (its own try: a problem here must never stop the live rules)
    try: cl = (getc or daily_closes)(feed, day)
    except Exception as e: print('Brent W4 closes unavailable:', type(e).__name__, str(e)[:100])
    dcl = cl['series'] if (cl and cl['ready']) else None
    trades_all = E.run_day(b, day, dt, A, hi, lo, sd, cost=cost, dcl=dcl) if (len(b) and np.isfinite(A)) else []
    trades = [t for t in trades_all if t['rule'] not in E.WATCH_RULES]; wtrades = [t for t in trades_all if t['rule'] in E.WATCH_RULES]
    rows = [row(t) for t in trades]; wrows = [row(t) for t in wtrades]
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows,
                             range_usd=(None if not np.isfinite(A) else round(A, 2)), ruleB=dt['ruleB'], ruleD_buy=dt['ruleD_buy'], ruleD_sell=dt['ruleD_sell'],
                             ruleE=dt['ruleE'], ruleF=dt['ruleF'], wed=dt['wed'])],
                       key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    if JW.get('start') is None: JW['start'] = str(day.date())
    if wrows:                                              # watch journal: only days that had a watch trade (never mixed into the live Brent journal)
        JW['days'] = sorted([d for d in JW['days'] if d['date'] != str(day.date())] +
                            [dict(date=str(day.date()), rules=WRULES, label=day.strftime('%a %d %b'), side=wrows[0]['side'], trades=wrows,
                                  range_usd=(None if not np.isfinite(A) else round(A, 2)))], key=lambda d: d['date'])
    JW['summary'] = watch_summary(JW); dumpj(JW, JOURW, indent=1)
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    rule_tags = [t['rule'] for t in trades]
    exit_lbl = dubai(day + pd.Timedelta(minutes=E.EXIT_MIN))
    if not np.isfinite(A): state, msg = 'none', 'No trade: fewer than 20 days of price history for the average range yet.'
    elif rows:
        sides = ', '.join(f"{r['side']} ({r['rule']})" for r in rows)
        state = 'mixed' if len(set(r['side'] for r in rows)) > 1 else rows[0]['side'].lower()
        msg = f"Today's signals: {sides}. Stop 1.0x the 20-day range (rule C: 2.0x), no target; closes {exit_lbl} Dubai if not stopped first."
    elif dt['wed']: state, msg = 'waiting', "Wednesday - checking the 10:00→14:00 broker move against its 60-day spread (enters 14:00 broker if big enough)."
    else: state, msg = 'none', 'No Brent signal today (not a Wednesday, US-holiday day-after, UK bank holiday, pre-holiday day, or 20-day range break).'
    if wrows: msg += ' Watch (DEMO forward test): ' + ', '.join(f"{r['side']} ({r['rule']})" for r in wrows) + f'; closes {exit_lbl} Dubai.'
    if dt.get('list_expiring'): msg += ' (A rule\'s holiday dates run out soon - the Brent chat needs to extend the EA\'s baked-in lists.)'
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 2), round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2)] for t, r in g5.iterrows()]
    mk['BRENT'] = dict(base_card(), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 2)),
                       entries=rows + wrows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC, watch=watch_block(JW, now, cl),
                       range_usd=(None if not np.isfinite(A) else round(A, 2)),
                       rule_today=dict(wed=dt['wed'], ruleB=dt['ruleB'], ruleD_buy=dt['ruleD_buy'], ruleD_sell=dt['ruleD_sell'], ruleE=dt['ruleE'], ruleF=dt['ruleF']))
    dumpj(old, PORTAL, indent=1)
    w4txt = None if cl is None else (cl['have'], 'ready' if cl['ready'] else 'warming, %s days to fetch' % cl['missing'])      # 21 Nov: plain string - the old nested f-string only compiles on Python 3.12+, the runner is 3.11
    wtags = [r['rule'] for r in wrows]
    print(f'Brent paper: {now} broker | bars {len(b)} | A {round(A,2) if np.isfinite(A) else None} | trades today {len(rows)} | rules {rule_tags} | watch trades {wtags} | W4 closes {w4txt}')

def fail(e):
    """Keep the last good Brent card and say what failed. NOTE: EPIC='OIL_BRENT' (env CAPITAL_EPIC_BRENT overrides it)
    is the WTI-style naming guess (matches OIL_CRUDE's convention) - not yet confirmed against the live Capital.com
    account (no API access from the build session); a wrong epic shows up here as a 400/404 feed error, not silently
    wrong prices - check this message once live and fix the epic (one line) if it names the wrong instrument."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('BRENT') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"Brent paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute. (If this persists, the Capital.com epic '{EPIC}' may be wrong - tell the Trading Dashboard chat.)"
    mk['BRENT'] = c; dumpj(old, PORTAL, indent=1)
