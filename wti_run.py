"""WTI PAPER signals for the page (no phone alerts, no real money). Called by run.py after gold and USDJPY, every minute.
Replays today's Capital.com US Crude (OIL_CRUDE) minutes through the WTI_DAYTRADE v1.03 rules (wti_engine.py; checked against his MT4
run A of the v1.03 EA, 2020-01 to 2026-09: 3,355 of 3,355 trades same minute + direction, sizes 99.9%, half-close 99.4%, same day sign 98.7%)
and keeps a paper journal, judged after ~3 months (pass = green days >= 60% and profit factor >= 1.10 with v1.03 sizes after Capital.com's spread).
Files: docs/wti_hist.json (finished broker days: date, open, high, low, close, settle; seeded from HistData to 2026-10-02, then extended
with Capital.com minutes), docs/journal_wti.json (every paper trade), docs/data.json -> markets.OIL (the page)."""
import os, re, json, time, requests, numpy as np, pandas as pd
import feeds as F, wti_engine as W
DEADLINE = time.time() + 240          # loop.py resets this every minute; the WTI part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
HIST = os.path.join(HERE, 'docs', 'wti_hist.json'); JOUR = os.path.join(HERE, 'docs', 'journal_wti.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
CUSH = os.path.join(HERE, 'docs', 'cushing.json')     # v1.05: EIA weekly Cushing crude stocks (thousand barrels) by week end
PROD = os.path.join(HERE, 'docs', 'production.json')  # v1.06: EIA weekly US crude oil production (thousand barrels a day) by week end
EPIC = os.environ.get('CAPITAL_EPIC_WTI', 'OIL_CRUDE')
MIN_SPREAD = 0.02                     # the paper result never uses less than 2 cents a barrel
PASS = dict(green=60.0, pf=1.10, months=3)
RULES = 'v1.05'                       # journal days are tagged; the card's record counts only the current rules (set per day in main)
V106_FROM = pd.Timestamp('2026-10-26') # v1.06 from broker day Mon 26 Oct 2026 (days before keep v1.05 - no mid-day rule change)
V107_FROM = pd.Timestamp('2026-10-27') # v1.07 from broker day Tue 27 Oct 2026 (later buys off; his MT4 run 26 Oct)
V108_FROM = pd.Timestamp('2026-11-02') # v1.08 from broker day Mon 2 Nov 2026 (v1.07 + the weakest third of entries at half size; his MT4 run 1 Nov: profit +0.5%, drawdown -9.4%, same trades)
V110_FROM = pd.Timestamp('2026-11-03') # v1.10 from broker day Tue 3 Nov 2026 (v1.08 + a side sell after a weak close; his MT4 run 2 Nov: 4,727 trades, +$49,793, PF 1.49, drawdown 7.65%)
V111_FROM = pd.Timestamp('2026-11-06') # v1.11 from broker day Fri 6 Nov 2026 (v1.10 + time-decay first target; his MT4 run 5 Nov: 89.94% closed in profit vs 88.13%, +$44,948, PF 1.50, 4,812 deals)
V115_FROM = pd.Timestamp('2026-11-16') # v1.15 from broker day Mon 16 Nov 2026 (his yes 7 Nov): v1.14 + no new ladder sell after a sell closed at break-even (his MT4 nobe_only run 7 Nov: green days 84.05% vs 82.0%, drawdown $5,977 vs $6,207, net +$39,654 vs +$43,999, PF 1.66)
V114_FROM = pd.Timestamp('2026-11-09') # v1.14 from broker day Mon 9 Nov 2026 (his choice B, 7 Nov: skip the v1.12 and v1.13 steps) (v1.13 + two buy-only levels: the day open from 7:00 and the high of 0:00-10:00; his MT4 runs 7 Nov: 92.39% closed in profit vs 90.77%, 1,724 days vs 1,690, green days 82.0% vs 77.9%, net +$43,999 vs +$50,691, drawdown $6,207 vs $6,664, PF 1.59)
V113_FROM = pd.Timestamp('2026-11-16') # v1.13 from broker day Mon 16 Nov 2026 (v1.12 + closer levels count; his MT4 run 6 Nov: 90.81% closed in profit, +$51,045, PF 1.62, drawdown $6,664, 4,916 deals, 1,677 days)
V112_FROM = pd.Timestamp('2026-11-09') # v1.12 from broker day Mon 9 Nov 2026 (v1.11 + weak-flow sells bank sooner; his MT4 run 6 Nov: 90.42% closed in profit vs 89.94%, +$46,700, PF 1.55, drawdown $6,901, 4,834 deals)
BACKTEST_115 = dict(direction='—', days='1,724 trading days (same as v1.14)', perday='1.4', win='92.43% closed in profit (v1.14: 92.39%); green days 84.05% (82.0%)', pf='1.66', net='+$39,654 (v1.14 same window: +$43,999), max drawdown $5,977 (v1.14: $6,207)',
                source='MT4 v1.15 rule 64 only, his run 7 Nov 2026, window 2018-01-02 to 2026-10-30 (trades from 2020-01-01), 4,388 deals (v1.14: 4,901), spread 4, Lots 0.30; after a part-closed sell closes at break-even, no new ladder sell that day (the day is already a failed sell day)')
BACKTEST_114 = dict(direction='—', days='1,724 trading days (v1.13 rules, same window: 1,690)', perday='1.5', win='92.39% closed in profit (v1.13 rules: 90.77%); green days 82.0% (77.9%)', pf='1.59', net='+$43,999 (v1.13 rules same window: +$50,691), max drawdown $6,207 (v1.13: $6,664)',
                source='MT4 v1.14, his runs 7 Nov 2026, window 2018-01-02 to 2026-10-30 (trades from 2020-01-01), 4,901 deals (v1.13 rules: 4,942), spread 4, Lots 0.30; adds two buy-only levels: a break up through the day open (watched from 7:00 broker) or through the high of 0:00-10:00 (set at 10:00) when price is below it = a buy, once a day each. The lower profit comes mostly from one crash day, 5 Jul 2022 (+$11,051 in v1.13 rules, -$502 in v1.14)')
BACKTEST_113 = dict(direction='—', days='1,677 trading days (v1.12: 1,663)', perday='1.5', win='90.81% closed in profit (v1.12: 90.42%)', pf='1.62', net='+$51,045 (v1.12 same window: +$46,700), max drawdown $6,664 (v1.12: $6,901)',
                source='MT4 v1.13, his run 6 Nov 2026, 2019-10-12 to 2026-10-10, 4,916 deals (v1.12: 4,834); levels count from 0.0125 x range away (was 0.05); also v1.12 weak-flow rule, spread 4, Lots 0.30; a ladder SELL entered while the day is not falling (5-min down-vs-up move flow <= 0.212) gets its part-close level at 0.10 of risk from the start')
BACKTEST_112 = dict(direction='—', days='same days and entries as v1.11 (1,663 trading days; green days 77.15% vs 76.01%)', perday='1.5', win='90.42% closed in profit (v1.11: 89.94%)', pf='1.55', net='+$46,700 (v1.11 same window: +$44,948), max drawdown $6,901 (v1.11: $8,480)',
                source='MT4 v1.12, his run 6 Nov 2026, 2019-10-12 to 2026-10-10, 4,834 deals (v1.11: 4,812), spread 4, Lots 0.30; a ladder SELL entered while the day is not falling (5-min down-vs-up move flow <= 0.212) gets its part-close level at 0.10 of risk from the start')
BACKTEST_111 = dict(direction='—', days='same days and entries as v1.10', perday='1.5', win='89.94% closed in profit (v1.10: 88.13%)', pf='1.50', net='+$44,948 (v1.10 same window: +$49,793), max drawdown $8,480 (v1.10: $9,511)',
                source='MT4 v1.11, his run 5 Nov 2026, 2019-10-12 to 2026-10-10, 4,812 deals (v1.10: 4,727), spread 4, Lots 0.30; a ladder trade with no part-close 90 min after entry gets a lower part-close level (sells 0.05, buys 0.02 of its risk)')
BACKTEST_110 = dict(direction='—', days='same days as v1.08 + ~0.15 trades/day', perday='1.5', win='—', pf='1.49', net='+$49,793 (v1.08 same run: +$49,559), max drawdown 7.65% (v1.08: 7.27%)',
                source='MT4 v1.10, his run 2 Nov 2026, 2019-10-12 to 2026-10-10, 4,727 trades (v1.08: 4,239), spread 4; side sell: 266 trades, 83.5% closed in profit, net +$766')
BACKTEST_108 = dict(direction='—', days='same days as v1.07', perday='1.40', win='—', pf='1.51', net='+$49,559 (v1.07 same run: +$49,300), max drawdown 7.27% (v1.07: 8.01%)',
                source='MT4 v1.08, his run 1 Nov 2026, 2019-10-12 to 2026-10-10, 4,239 trades (same as v1.07), spread 4, Half_Close_Part 0.2; weakest third of entries at half size')
BACKTEST = dict(direction='—', days='69.3% green / 93.7% traded', perday='1.40', win='79.1%', pf='1.44', net='+$48,688 at 0.30 + 0.10 lots (v1.06: +$46,306)',
                source='MT4 v1.07, his run 26 Oct 2026, 2020-01 to 2026-10-09, 2,480 trades, spread 4 (worst day -$1,724); $34.7/day 2020-22, $21.9/day 2023-26')
BACKTEST_106 = dict(direction='—', days='65.2% green / 93.7% traded', perday='1.86', win='81.5%', pf='1.38', net='+$46,306 at 0.30 + 0.10 lots (v1.05: +$35,670)',
                source='MT4 v1.06, his run 23 Oct 2026, 2020-01 to 2026-10-09, 3,297 trades, spread 4 (worst day -$1,724); $33.6/day 2020-22, $20.3/day 2023-26')
BACKTEST_105 = dict(direction='—', days='65.7% green / 93.9% traded', perday='1.91', win='83.6%', pf='1.33', net='+$37,406 at 0.30 + 0.10 lots (v1.04: +$32,010)',
                source='MT4 v1.05, his run 20 Oct 2026, 2020-01 to 2026-09, 3,355 trades, spread 4 (worst day -$1,724); $26.7/day 2020-22, $17.0/day 2023-26')
def rules_for(day):
    d = pd.Timestamp(day).normalize()
    return 'v1.15' if d >= V115_FROM else 'v1.14' if d >= V114_FROM else 'v1.13' if d >= V113_FROM else 'v1.12' if d >= V112_FROM else 'v1.11' if d >= V111_FROM else 'v1.10' if d >= V110_FROM else 'v1.08' if d >= V108_FROM else 'v1.07' if d >= V107_FROM else 'v1.06' if d >= V106_FROM else 'v1.05'

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

def minutes(feed, start_b, end_b):
    """Capital.com OIL_CRUDE minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    global SKIPPED
    t0, end = to_utc(start_b), to_utc(end_b); out = []; SKIPPED = 0
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
        else: SKIPPED += 1                    # 400/404 = no prices in that chunk (weekend - or a Capital.com hiccup): counted for the log
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); return d[['o', 'h', 'l', 'c', 'sp']].astype(float).sort_index()

def day_bars(b, day):
    b = b[(b.index >= day) & (b.index < day + pd.Timedelta(days=1))]
    return b.index, b.o.values, b.h.values, b.l.values, b.c.values

SKIPPED = 0                           # chunks the last minutes() call got no prices for (400/404)
# 23 Oct fix: a finished day is saved only when it is reasonably complete; otherwise the history does not advance and the next run retries
EXP_MIN = 1365                        # minutes in a full broker day (his WTI M1 data 2025-26: median 1,362-1,370 by weekday)
COMPLETE = 0.85                       # complete = >= 85% of that weekday's usual minute count AND the 21:30-21:35 settlement bar
TRIES, TRY_SECS = 3, 1800             # an empty / short download is accepted (holiday / short day) only after 3 tries spread over >= 30 min
STALE_SECS, GAP_MIN, LOOK_MIN = 180, 3, 60   # today: newest closed minute older than 3 min, or > 3 missing minutes in the last 60 = feed error
CHECK_FROM, CHECK_TO = 1 * 60 + 10, 20 * 60 + 5   # broker minutes the today-check runs (market reopens 1:00; the desk's day ends with the 20:00 bar)

def usual_minutes(H, wd):
    """Usual minute count for weekday `wd` (0 = Monday): median of the last 10 complete days stored, else EXP_MIN."""
    v = [n for d, n in sorted((H.get('nmin') or {}).items()) if pd.Timestamp(d).dayofweek == wd][-10:]
    return float(np.median(v)) if len(v) >= 3 else float(EXP_MIN)

def tried_enough(H, key):
    """Counts one more try for day `key`; True once there were >= TRIES tries spread over >= TRY_SECS."""
    t = H.setdefault('tries', {}).setdefault(key, [0, time.time()]); t[0] += 1
    return t[0] >= TRIES and time.time() - t[1] >= TRY_SECS

def catch_up(feed, H, day, get=None):
    """Add every finished weekday after H['through'] and before `day` (Capital.com minutes) - only when the day has >= 85% of its usual
    minutes and the settlement bar. A short / empty download does NOT advance the history: the next run retries. After 3 tries over
    >= 30 min the day is taken as it is (>= 60 bars: short day; fewer: holiday, as before). Saves after each day.
    Returns (added, waiting) - waiting = why the history is not up to date yet."""
    get = get or minutes; last = pd.Timestamp(H['through']); added = []; H.setdefault('nmin', {})
    def save(): json.dump(H, open(HIST, 'w'), separators=(',', ':'))
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1); key = str(nxt.date())
        if nxt.dayofweek < 5:
            t, o, h, l, c = day_bars(get(feed, nxt, nxt + pd.Timedelta(days=1)), nxt)
            row_ = W.daily_from_minutes(t, o, h, l, c) if len(t) else None
            usual = usual_minutes(H, nxt.dayofweek)
            full = len(t) >= COMPLETE * usual and row_[4] is not None
            if full: H['nmin'][key] = int(len(t))
            elif not tried_enough(H, key):
                save()
                return added, (f"{key}: {len(t)} of ~{usual:.0f} minutes" + ('' if (row_ and row_[4] is not None) else ', no settlement bar')
                               + f" so far - retrying (try {H['tries'][key][0]} of {TRIES})")
            if len(t) >= 60:
                H['days'].append([key, *row_]); added.append(key + ('' if full else f' (short day, {len(t)} minutes' + ('' if row_[4] is not None else ', no settlement') + ')'))
            else: added.append(key + f' (no prices after {TRIES} tries over {TRY_SECS // 60} min - holiday)')
            H.get('tries', {}).pop(key, None)
        last = nxt; H['through'] = key; H['days'] = H['days'][-W.KEEP_DAYS:]; H['nmin'] = dict(sorted(H['nmin'].items())[-40:])
        save()
    return added, None

def feed_health(b, now, day):
    """Today's minutes good enough to trade on? (ok, why). Checked Mon-Fri 1:10-20:05 broker: newest closed minute older than 3 min,
    > 3 missing minutes in the last 60, or < 85% of the minutes since 1:00 = not ok."""
    hm_now = now.hour * 60 + now.minute
    if now.dayofweek >= 5 or not (CHECK_FROM <= hm_now <= CHECK_TO): return True, ''
    tw = b.index[b.index >= day + pd.Timedelta(hours=1)]
    if not len(tw): return False, 'no oil prices yet today (market closed?)'
    age = (now - (tw[-1] + pd.Timedelta(minutes=1))).total_seconds()
    if age > STALE_SECS: return False, f'newest closed minute is {int(age // 60)} min old'
    x = tw[tw >= now - pd.Timedelta(minutes=LOOK_MIN + 1)].values.astype('datetime64[s]').astype(np.int64)
    if len(x) > 1 and np.diff(x).max() > (GAP_MIN + 1) * 60:
        return False, f'{int(np.diff(x).max()) // 60 - 1} minutes missing in the last {LOOK_MIN} min'
    want = int((tw[-1] - (day + pd.Timedelta(hours=1))).total_seconds() // 60) + 1
    if want >= 60 and len(tw) < COMPLETE * want: return False, f'only {len(tw)} of {want} minutes today'
    return True, ''

EIA_URL = 'https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=W_EPC0_SAX_YCUOK_MBBL&f=W'
def eia_parse(s):
    """EIA weekly table (one row per month: 'YYYY-Mon', then MM/DD + value pairs) -> [[week_end 'YYYY-MM-DD', stocks], ...]."""
    out = []
    for row in re.findall(r"<tr>\s*<td class='B6'>(.*?)</tr>", s, re.S):
        y = re.search(r'(\d{4})-', row)
        if not y: continue
        cells = re.findall(r"<td class='B5'>([^<]*)</td>\s*<td class='B3'>([^<]*)</td>", row)
        for dd, v in cells:
            dd = dd.replace('&nbsp;', '').strip(); v = v.replace('&nbsp;', '').replace(',', '').strip()
            if not dd or not v: continue
            m_, d_ = dd.split('/'); out.append([f"{y.group(1)}-{int(m_):02d}-{int(d_):02d}", float(v)])
    return out
STALE_DAYS = 8                        # newest released report older than this = stale -> rule off (first sell 1/3)
_HOL = []
def eia_release(week_end):
    """Broker time the EIA Weekly Petroleum Status Report for the week ending `week_end` (Friday) comes out: normally Wednesday 10:30 am
    New York; a US federal holiday on the Monday-Wednesday before moves it to Thursday (11:00 am New York). Broker = New York + 7 h."""
    if not _HOL:
        from pandas.tseries.holiday import USFederalHolidayCalendar
        _HOL.append(set(USFederalHolidayCalendar().holidays('2010-01-01', '2040-12-31')))
    we = pd.Timestamp(week_end).normalize()
    late = any(we + pd.Timedelta(days=k) in _HOL[0] for k in (3, 4, 5))
    return we + pd.Timedelta(days=6, hours=11 + 7) if late else we + pd.Timedelta(days=5, hours=10.5 + 7)

def cushing(day):
    """v1.05: latest Cushing stock change RELEASED (real EIA release time, see eia_release) before broker day `day` starts. Refreshes the
    stored series from eia.gov at most once an hour while a newer report is due. The answer is worked out once per broker day and then
    frozen (docs/cushing.json 'frozen'), so a report fetched later in the day can never change a first sell already shown.
    Returns (build True/False/None, week end, change, stale) - stale (newest released report > 8 days old, or none): build = None."""
    C = loadj(CUSH, dict(weeks=[], last_try=0))
    last = pd.Timestamp(C['weeks'][-1][0]) if C['weeks'] else pd.Timestamp('2000-01-01')
    if day >= last + pd.Timedelta(days=12) and time.time() - C.get('last_try', 0) > 3600:
        C['last_try'] = time.time()
        try:
            r = requests.get(EIA_URL, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            w = eia_parse(r.text) if r.status_code == 200 else []
            if len(w) > 100: C['weeks'] = w[-600:]
        except Exception as e: print('cushing fetch failed', type(e).__name__)
        json.dump(C, open(CUSH, 'w'), separators=(',', ':'))
    key = str(pd.Timestamp(day).date()); fz = C.get('frozen') or {}
    if fz.get('day') == key: return tuple(fz['res'])
    prev = [(eia_release(a), a, v) for a, v in C['weeks']]; prev = [x for x in prev if x[0] < day]
    if len(prev) < 2: res = (None, None, None, True)
    else:
        ch = float(prev[-1][2] - prev[-2][2]); stale = (day - prev[-1][0]) > pd.Timedelta(days=STALE_DAYS)
        res = (None if stale else bool(ch > 0), prev[-1][1], ch, bool(stale))
    C['frozen'] = dict(day=key, res=list(res)); json.dump(C, open(CUSH, 'w'), separators=(',', ':'))
    return res
def first_sell_full(H, day):
    """v1.05 rule for `day`: last Cushing report = build AND yesterday's close < close 5 trading days earlier (off when Cushing is stale)."""
    cl = [r[4] for r in H['days'] if pd.Timestamp(r[0]) < day]
    down = len(cl) > 5 and cl[-1] < cl[-6]
    b, wk, ch, stale = cushing(day)
    return bool(b and down), dict(cushing_build=b, cushing_week=wk, cushing_change=ch, down5=bool(down), cushing_stale=bool(stale))

PROD_URL = 'https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=PET&s=WCRFPUS2&f=W'
def production(day):
    """v1.06: latest US crude production change RELEASED (same EIA weekly report and release time as Cushing) before broker day `day`.
    Same fetch / freeze logic as cushing(). Returns (up True/False/None, week end, change kb/d, stale)."""
    C = loadj(PROD, dict(weeks=[], last_try=0))
    last = pd.Timestamp(C['weeks'][-1][0]) if C['weeks'] else pd.Timestamp('2000-01-01')
    if day >= last + pd.Timedelta(days=12) and time.time() - C.get('last_try', 0) > 3600:
        C['last_try'] = time.time()
        try:
            r = requests.get(PROD_URL, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            w = eia_parse(r.text) if r.status_code == 200 else []
            if len(w) > 100: C['weeks'] = w[-600:]
        except Exception as e: print('production fetch failed', type(e).__name__)
        json.dump(C, open(PROD, 'w'), separators=(',', ':'))
    key = str(pd.Timestamp(day).date()); fz = C.get('frozen') or {}
    if fz.get('day') == key: return tuple(fz['res'])
    prev = [(eia_release(a), a, v) for a, v in C['weeks']]; prev = [x for x in prev if x[0] < day]
    if len(prev) < 2: res = (None, None, None, True)
    else:
        ch = float(prev[-1][2] - prev[-2][2]); stale = (day - prev[-1][0]) > pd.Timedelta(days=STALE_DAYS)
        res = (None if stale else bool(ch > 0), prev[-1][1], ch, bool(stale))
    C['frozen'] = dict(day=key, res=list(res)); json.dump(C, open(PROD, 'w'), separators=(',', ':'))
    return res
SUPPLY_AVG = 50
def hold_sells(H, day):
    """v1.06 rule for `day`: production rose in the last released EIA report AND yesterday's close < average of the last 50 closes
    (yesterday included) - same as the EA (inputs 10-11). Off when production data is stale / missing or < 50 days of history."""
    cl = [r[4] for r in H['days'] if pd.Timestamp(r[0]) < day][-SUPPLY_AVG:]
    below = len(cl) >= SUPPLY_AVG and cl[-1] < sum(cl) / SUPPLY_AVG
    up, wk, ch, stale = production(day)
    return bool(up and below), dict(prod_up=up, prod_week=wk, prod_change=ch, below50=bool(below), prod_stale=bool(stale))
_EXP = []
def expiry_day(day):
    """v1.06: WTI (LO) option-expiry day = 7 US business days before the 26th of the month (US federal holidays + Good Friday) - same
    dates as the EA's built-in list (rule checked: Dec 2024 = 16 Dec)."""
    if not _EXP:
        from pandas.tseries.holiday import USFederalHolidayCalendar, GoodFriday
        hol = list(USFederalHolidayCalendar().holidays('2018-01-01', '2041-01-01')) + list(GoodFriday.dates('2018-01-01', '2041-01-01'))
        bd = pd.offsets.CustomBusinessDay(holidays=hol)
        _EXP.append({pd.Timestamp(y, m, 26) - 7 * bd for y in range(2018, 2041) for m in range(1, 13)})
    return pd.Timestamp(day).normalize() in _EXP[0]

def hold(why):
    """Keep the last good WTI card, with feed_error=True so the auto-trader leaves oil alone this minute; journal untouched."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('OIL') or {}
    c = {k: v for k, v in c.items() if k not in ('status', 'note')} if c.get('paper') is None else c
    c.update({k: v for k, v in base_card(day=F.broker_now().normalize()).items() if k != 'day_note'}); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = (f"Oil prices not complete at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({why}) "
                    "— shows the last good update; checks again next minute.")
    mk['OIL'] = c; json.dump(old, open(PORTAL, 'w'), indent=1); print('WTI held:', why)

def row(t, now, day_over):
    st = t['status']
    if st == 'open' and day_over: st = 'close_now'
    sp = max(MIN_SPREAD, t['spread'] or 0.0)
    res = None if t['exit'] is None else round(t['res'], 3) if t.get('res') is not None else round((t['exit'] - t['px']) * t['dir'] - sp, 3)
    w = float(t['size']) if isinstance(t['size'], (int, float)) else (1.0 if t['size'] == 'full' else 1 / 3)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], price=round(t['px'], 2), stop=round(t['stop'], 2), stop0=round(t.get('stop0', t['stop']), 2),
                half_px=(None if t.get('half_px') is None else round(t['half_px'], 2)), half=bool(t.get('half')), part=t.get('part', 0.5), late=bool(t.get('late')),
                stop_usd=round(abs(t['px'] - t.get('stop0', t['stop'])), 2), size=t['size'], first=t['first'], status=st,
                exit=None if t['exit'] is None else round(t['exit'], 2), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=None if res is None else round(res * w, 3), rwf=t['rwf'], spread=round(sp, 3))

def summary(J, day=None):
    """Paper record of the CURRENT rules only (v1.07 days from 27 Oct 2026; v1.06 26 Oct; v1.05 20-23 Oct); older days stay in the journal but are not mixed in."""
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    J = dict(start=D3[0]['date'], days=D3)
    allt = [t for d in J.get('days', []) for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]; rr = [t['res_sized'] for t in allt if t.get('res_sized') is not None]
    end = str((day or pd.Timestamp(J['days'][-1]['date'])).date()) if J.get('days') else J['start']
    wd = max(1, len(pd.bdate_range(J['start'], end))); tdays = sum(1 for d in J['days'] if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), decided=len(dec),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 2) if rr else None, rules=RULES,
                green=round(100 * sum(1 for d in J['days'] if sum(t.get('res_sized') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None, day=None):
    v = rules_for(day if day is not None else F.broker_now().normalize())
    note = ('14-day range ' + ('—' if A is None else f'${A:.2f}') + ' · stop: buys 1 range, sells ¾ range · close 25% at +0.05 (buys) / +0.15 (sells) '
            'x risk, then stop to entry' + (' (sells on supply days: no part-close, hold to stop / day end)' if v in ('v1.06', 'v1.07', 'v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else '') +
            ' · day lock +2R/+1R · no new trades after 4:30 pm broker (one late first trade to 7:00 pm)' + (' · option-expiry day: first trade only' if v in ('v1.06', 'v1.07', 'v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else '') + (' · a buy only as the first trade (later buy signals skipped)' if v in ('v1.07', 'v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else '') + (' · v1.08: the weakest third of entries (by a fixed score) trade at half size' if v in ('v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else '') + (' · v1.10: SIDE SELL at 7:00 am broker time if yesterday closed in the bottom 20% of its range and nothing has traded yet, ¼ size, own stop' if v in ('v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else '') + (' · v1.11: a ladder trade with no part-close 90 min after entry gets a lower part-close level (sells 0.05, buys 0.02 of its risk)' if v in ('v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else '') + (' · v1.14: two extra BUY levels - the day open (from 7:00 am broker) and the high of 0:00-10:00 broker (from 10:00): price below the level then breaks up through it = a buy, once a day each' if v == 'v1.14' else '') + (' · v1.12: a ladder SELL entered while the day is not falling (5-minute down-vs-up move flow at or below 0.212) gets its part-close level at 0.10 of its risk from the start' if v in ('v1.12', 'v1.13', 'v1.14', 'v1.15') else '') +
            ' · close 8:00 pm broker = 9:00 pm Dubai, 10:00 pm in winter · size: first trade and buys ⅓, later sells full while the day is in profit' + (' · v1.08: weakest-third entries at half of that' if v in ('v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15') else ''))
    return dict(code='OIL', name='Oil (WTI)', symbol='WTI · Capital.com US Crude', live=False, paper=True, status='Paper', version=v,
                unit='usd', dp=2, stats=(BACKTEST_115 if v == 'v1.15' else BACKTEST_114 if v == 'v1.14' else BACKTEST_113 if v == 'v1.13' else BACKTEST_112 if v == 'v1.12' else BACKTEST_111 if v == 'v1.11' else BACKTEST_110 if v == 'v1.10' else BACKTEST_108 if v == 'v1.08' else BACKTEST if v == 'v1.07' else BACKTEST_106 if v == 'v1.06' else BACKTEST_105), pass_bar=PASS, day_note=note,
                what_note='This page tracks whether live WTI signals do as well as the backtest. Decision after about 3 months.',
                cost_note="Results are $ per barrel (sizes: full or ⅓), from the signal price with the backtest's slip, after a fixed 4-cent spread (the MT4 test's spread and Capital.com's usual; fixed so shown levels never change).",
                net_label=f'Net $ per barrel ({v})')

def main(feed=None, get=None, now=None):
    global DEADLINE, RULES; DEADLINE = time.time() + 75                # 22 Oct: own time budget per market
    now = now or F.broker_now(); day = now.normalize(); RULES = rules_for(day); v6 = RULES in ('v1.06', 'v1.07', 'v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15'); v7 = RULES in ('v1.07', 'v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15'); v8 = RULES in ('v1.08', 'v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15'); v10 = RULES in ('v1.10', 'v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15'); v11 = RULES in ('v1.11', 'v1.12', 'v1.13', 'v1.14', 'v1.15'); v12 = RULES in ('v1.12', 'v1.13', 'v1.14', 'v1.15'); v13 = RULES in ('v1.13', 'v1.14', 'v1.15'); v14 = RULES in ('v1.14', 'v1.15'); v15 = RULES == 'v1.15'
    H = loadj(HIST, None)
    if H is None: raise RuntimeError('docs/wti_hist.json missing')
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    if now.dayofweek >= 5:
        prev = mk.get('OIL') or {}
        mk['OIL'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(day=day), state='closed', message='Market closed for the weekend.',
                         entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        json.dump(old, open(PORTAL, 'w'), indent=1); print('WTI: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('WTI paper needs the Capital.com prices')
        feed = F.Capital()
    added, wait = catch_up(feed, H, day, get)
    if wait: return hold('history not complete: ' + wait)
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]       # today's closed minute bars only
    ok, why = feed_health(b, now, day)
    if not ok: return hold(why)
    P = W.prep(H['days'], day)
    try: fsf, finfo = first_sell_full(H, day)
    except Exception as e: fsf, finfo = False, dict(cushing_build=None, cushing_week=None, cushing_change=None, down5=False, cushing_stale=False); print('v1.05 rule failed', e)
    if P is not None: P['first_sell_full'] = fsf
    exp, hs, hinfo = False, False, dict(prod_up=None, prod_week=None, prod_change=None, below50=False, prod_stale=True)
    if v6:
        try: exp = expiry_day(day)
        except Exception as e: print('v1.06 expiry rule failed', e)
        try: hs, hinfo = hold_sells(H, day)
        except Exception as e: print('v1.06 supply rule failed', e)
        if P is not None: P['expiry_first_only'] = exp; P['hold_sells'] = hs; P['later_buys_off'] = v7; P['weak_down'] = v8
        if P is not None and v15: P['nobe'] = True                                                      # v1.15: no new ladder sell after a sell closed at break-even
        if P is not None and v14: P['buyl'] = True                                                      # v1.14: two buy-only level families (day open, morning high)
        if P is not None and v13: P['mind'] = 0.0125                                                   # v1.13: a level counts if the price is at least 0.0125 x range away (was 0.05)
        if P is not None and v12: P['skew'] = (0.212, 0.10)                                           # v1.12: weak-flow ladder sells get part-close level 0.10 from the start (threshold, level)
        if P is not None and v11: P['decay'] = (90, 0.05, 0.02)                                       # v1.11: time-decay first target (minutes, sell level, buy level)
    hm = W.close_hm(day); eod = day + pd.Timedelta(minutes=hm); day_over = now >= eod
    trades = W.run_day(P, b.index, b.o.values, b.h.values, b.l.values, b.c.values) if (P and len(b)) else []     # 23 Oct: fixed 4-cent spread inside the engine
    rows = [row(t, now, day_over) for t in trades]
    if v10 and P and len(b):                                                                  # v1.10: side sell (own trade, never sets the day's direction)
        try: rows = rows + [row(t, now, day_over) for t in W.side_sell(P, b.index, b.o.values, b.h.values, b.l.values, b.c.values, trades)]
        except Exception as e: print('v1.10 side sell failed', e)
    nside = sum(1 for r in rows if r['name'].startswith('Side sell'))
    lrows = rows[:len(rows) - nside] if nside else rows                                          # ladder rows only (for the day's direction)
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(lrows[0]['side'] if lrows else None), trades=rows,
                             range_usd=(None if P is None else round(P['A'], 2)), traded=bool(P), final=bool(day_over))], key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    json.dump(J, open(JOUR, 'w'), indent=1)
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    last_sig = now >= eod
    if P is None: state, msg = 'none', 'No trading today (not enough history or the day after a long break - same rule as the EA).'
    elif lrows:
        side = lrows[0]['side']; state = side.lower()
        msg = (f"PAPER {side} day — " + ("option-expiry day: no more trades today. " if exp else "v1.07: no more trades today (a buy only as the day's first trade). " if (v7 and side == 'BUY') else f"later signals today are {side} only. ") +
               ("Supply day: hold the whole sell (no part-close), the stop stays where it is; " if (hs and side == 'SELL') else "Close 25% at the part level, then move the stop to entry; ") +
               f"everything closes at {dubai(eod)} Dubai. No new trades after {dubai(day + pd.Timedelta(minutes=W.LAST_ENTRY))} (one late first trade allowed).")
    elif last_sig: state, msg = 'none', 'No paper trade today.'
    else: state, msg = 'waiting', 'Waiting for the first signal.'
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()   # 5-min candles for the page: [time, close, open, high, low]
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 2), round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2)] for t, r in g5.iterrows()]
    mk['OIL'] = dict(base_card(None if P is None else P['A'], day), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 2)),
                     entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, epic=EPIC,
                     live_spread=(round(float(np.nanmedian(b.sp.values[-30:])), 3) if len(b) and np.isfinite(b.sp.values[-30:]).any() else None),
                     history_note=f"history to {H['through']} ({len(H['days'])} days)" + (f" · added {', '.join(added)}" if added else ''),
                     day_note=base_card(None if P is None else P['A'], day)['day_note'] + ' · v1.05: ' + ('First sell today: FULL size (Cushing stocks rose in the last EIA report and oil is down over 5 days)' if fsf else
                                   'First sell today: 1/3 size (' + ('Cushing data stale - newest EIA report over 8 days old' if finfo.get('cushing_stale') else 'Cushing build' if finfo['cushing_build'] else 'Cushing draw' if finfo['cushing_build'] is False else 'Cushing data missing')
                                   + ', 5-day move ' + ('down' if finfo['down5'] else 'up') + ')') + (f" · EIA week {finfo['cushing_week']}: {finfo['cushing_change']:+,.0f}k bbl" if finfo['cushing_week'] else '')
                              + ('' if not v7 else ' · v1.07: later buys off') + ('' if not v6 else ' · v1.06: ' + ('OPTION-EXPIRY DAY: first trade only' if exp else 'not an option-expiry day') + ' · sells today: '
                                 + ('HOLD whole trade (US production rose in the last EIA report and oil is below its 50-day average)' if hs else
                                    'normal part-close (' + ('production data stale/missing' if hinfo.get('prod_stale') or hinfo.get('prod_up') is None else 'production ' + ('up' if hinfo['prod_up'] else 'down/flat'))
                                    + ', oil ' + ('below' if hinfo['below50'] else 'above') + ' 50-day avg)')
                                 + (f" · EIA production week {hinfo['prod_week']}: {hinfo['prod_change']:+,.0f}k b/d" if hinfo.get('prod_week') else '')))
    json.dump(old, open(PORTAL, 'w'), indent=1)
    print(f'WTI paper: {now} broker | trades today {len(rows)} | bars {len(b)} (empty chunks {SKIPPED}) | history to {H["through"]} | added {added}')

def fail(e):
    """Keep the last good WTI card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('OIL') or {}
    c = {k: v for k, v in c.items() if k not in ('status', 'note')} if c.get('paper') is None else c
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"WTI paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['OIL'] = c; json.dump(old, open(PORTAL, 'w'), indent=1)
