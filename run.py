"""Runs every minute (GitHub Actions, via loop.py). GOLD v2.15 from 22 Oct 2026 (= v2.11 + day lock 2R/0.5R + real-yield size 1.5 + strong-family size 1.5 + add a 3rd trade when every open trade is up 1.25x its stop; desk209.V215_FROM; MT4 his run passed 21 Oct). Before: GOLD v2.11 (20 Oct 2026; = v2.10 with NO half-close / no stop to entry, desk209.SPLIT=False). Was v2.10 (18 Oct 2026; = v2.09 + no 2nd trade in the same minute): today's gold minute bars -> the EA's signals
(engine206.py, v2.06 signal set) -> the v2.10 trade rules (desk209.py: one direction, max 2 trades, half close at 0.20 x stop,
stop to entry, rest to the day-end close, range-fade fill). Writes the page + the live journal, including the ACTIONS list
(OPEN / ADD / HOLD / CLOSE HALF / STOP / REVERSE / CLOSE ALL). Desk only - no Telegram (his rule, 18 Oct).
It never trades. You place the trades yourself."""
import os, sys, json, requests, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine206 as E, inputs206 as I, feeds as F, desk209 as DK

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = float(os.environ.get('ALERT_SIZE_OZ', '0.1'))
STATE = os.path.join(HERE, 'sent.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
JOURNAL = os.path.join(HERE, 'docs', 'journal.json'); INPUTS = os.path.join(HERE, 'docs', 'inputs.json')
BACKTEST_V210 = dict(direction='—', days='72–73% green', perday='1.7', win='79–81%', pnl='—', source='MT4 backtest v2.10, his run 2020–2026 (worst day −2.1R)')
BACKTEST = dict(direction='—', days='49% green (53% of trade days)', perday='1.5', win='0% hit target · 51% closed in profit', pnl='—', source='MT4 backtest v2.15, his run 21 Oct 2020–2026 ($247/day 2020–22, $263/day 2023–26 at $1,000 risk; worst day −$4,681)')
BACKTEST_V211 = dict(direction='—', days='45–46% green', perday='1.5', win='47–50%', pnl='—', source='MT4 backtest v2.11, his runs 20 Oct 2020–2026 ($162/day 2020–22, $189/day 2023–26 at $1,000 risk; worst day −3.6R)')

def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()
def eod_of(day):
    """Broker day -> its day-end close (broker time). Falls back to the old rule if engine206.py is an older copy."""
    d = pd.Timestamp(day); f = getattr(E, 'close_minutes', None)
    return d + pd.Timedelta(minutes=f(d) if f else (22 * 60 + 50 if d.dayofweek == 4 else 23 * 60))
def send(text):
    """DESK ONLY (his rule, 18 Oct 2026): nothing goes to Telegram any more; the message is shown on the page instead."""
    print('[desk only] ' + text.replace('\n', ' | ')); return True
    tok, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not tok or not chat: print('[no Telegram keys] ' + text.replace('\n', ' | ')); return True
    try:
        r = requests.post(f'https://api.telegram.org/bot{tok}/sendMessage', data={'chat_id': chat, 'text': text}, timeout=20)
    except Exception as e:
        print('telegram not sent:', type(e).__name__); return False        # retried next run (not marked as sent)
    print('telegram', r.status_code, text.splitlines()[0]); return r.status_code == 200
def dumpj(obj, p, **kw):
    """Write JSON atomically (temp file + rename), so a cancelled job never leaves a half-written file."""
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(obj, f, **kw)
    os.replace(tmp, p)
def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d

def daily_bars(h1, day):
    """Broker-day bars from hourly bars (index = broker time), days before `day` only."""
    d = h1[h1.index < day]
    g = d.groupby(d.index.normalize())
    return pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})

def regime_today(feed, h1, day, now, with_err=False):
    """1 / 0 / None and the correlation; needs the broker's 00:00 hourly FX bars (closed at 1:00 broker).
    with_err=True adds a third value: True = the fetch FAILED (value not known yet), False = known (None = too little data -> 0)."""
    if now < day + pd.Timedelta(hours=1): return (None, None, False) if with_err else (None, None)
    try:
        fx = {}
        for p in I.W:
            b = feed.h1(days=45, epic=p); b = b[b.index.hour == 0]
            fx[p] = {t.date(): float(c) for t, c in zip(b.index.normalize(), b.c)}
        g = h1[h1.index <= now]; opens = g.groupby(g.index.normalize()).o.first()
        r = I.dollar_regime([(t.date(), float(o)) for t, o in opens.items()], fx)
        return (r[0], r[1], False) if with_err else r
    except Exception as e:
        print('regime not computed:', type(e).__name__, e); return (None, None, True) if with_err else (None, None)

RY_FILE = os.path.join(HERE, 'docs', 'realyield.json')   # v2.15: US 10-yr real yield (Treasury daily real yield curve = FRED DFII10)
RY_URL = 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all?type=daily_treasury_real_yield_curve&field_tdr_date_value={y}&page&_format=csv'
def realyield(day):
    """v2.13 sizing input for broker day `day`: change of the 10-yr real yield on its latest date <= day - 2 calendar days (vs the previous
    date). Refreshes docs/realyield.json from treasury.gov at most once an hour while that date is missing. None = unknown (no yield size)."""
    import time
    R = loadj(RY_FILE, dict(rows=[], last_try=0)); need = (day - pd.Timedelta(days=2)).normalize()
    have = pd.Timestamp(R['rows'][-1][0]) if R['rows'] else pd.Timestamp('2000-01-01')
    stale = have < need - pd.Timedelta(days=4)          # fixpack 22 Oct: was re-fetched EVERY minute while > 4 days old (2 calls, 15 s
    if have < need and time.time() - R.get('last_try', 0) > (1800 if stale else 3600):   # timeouts); now at most every 30 min
        R['last_try'] = time.time(); rows = {r[0]: r[1] for r in R['rows']}
        for y in sorted({need.year - 1, need.year}):
            try:
                r = requests.get(RY_URL.format(y=y), timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
                if r.status_code != 200: continue
                lines = r.text.strip().splitlines(); hd = [h.strip('"') for h in lines[0].split(',')]; c = hd.index('10 YR')
                for ln in lines[1:]:
                    v = ln.split(',')
                    if len(v) > c and v[c].strip():
                        m_, d_, y_ = v[0].split('/'); rows[f'{y_}-{int(m_):02d}-{int(d_):02d}'] = float(v[c])
            except Exception as e: print('real yield fetch failed', y, type(e).__name__)
        R['rows'] = sorted(rows.items())[-400:]; dumpj(R, RY_FILE)
    prev = [r for r in R['rows'] if pd.Timestamp(r[0]) <= need]
    if len(prev) < 2 or pd.Timestamp(prev[-1][0]) < need - pd.Timedelta(days=6): return None
    return round(prev[-1][1] - prev[-2][1], 4)

VOL_HIST_FILE = os.path.join(HERE, 'volmult_hist.csv')   # v2.21 DT225 sizing input (Vol_High_Size): EXACT port of the EA's own
# hardcoded volD[]/volV[] array (GOLD_DAYTRADE.mq4, "combined GLD+GC-futures+SLV volume z-score x1000, by day 2008-2026") -
# same real-backtestable-no-live-feed pattern the EA used for RYMult, which run.py mirrors LIVE instead via realyield() above.
# This one is NOT live-extended: 7 Nov tried reverse-engineering a live equivalent from free GLD/SLV/GC=F volume data (6
# formula variants - raw/log, rolling/expanding windows), best correlation only ~0.32 - not trustworthy enough to ship as a
# live signal. His call 7 Nov: port the array as-is. The array's last date is 2026-09-21; any broker day after that (no
# array coverage) sizes 1.0x (no boost) until a verified live source is found. See day-trading-gold-v3 memory for detail.
VOL_HIGH_CUT = 0.14   # v2.21 Vol_High_Cut: combined-volume z-score cutoff for a "high volume day" (top third of real days)
V225_FROM = np.datetime64('2026-11-07')   # v2.21 DT225 sizing goes live dashboard-side from push day - same precedent as
# v2.20/v2.22/v2.24 above (no MT4-confirmed go-live date for the Python mirror). Gated by date so past journal/Analytics
# days are never recomputed differently.
_VOL_HIST = None
def _vol_hist():
    """Lazy-load + cache VOL_HIST_FILE as (sorted date list, matching z-score list)."""
    global _VOL_HIST
    if _VOL_HIST is None:
        import csv, bisect as _b
        dates, zs = [], []
        with open(VOL_HIST_FILE) as f:
            for row in csv.DictReader(f):
                dates.append(np.datetime64(row['date'], 'D')); zs.append(int(row['z1000']) / 1000.0)
        _VOL_HIST = (dates, zs)
    return _VOL_HIST
def volume_high(day):
    """v2.21 DT225 sizing input for broker day `day`: True when the array's most recent date strictly before `day`
    has a combined-volume z-score >= VOL_HIGH_CUT (same most-recent-prior-day lookup as the EA's VolMult()). False
    before V225_FROM, and False for any day the array doesn't cover (see VOL_HIST_FILE comment above)."""
    import bisect
    d = np.datetime64(day, 'D')
    if d < V225_FROM: return False
    dates, zs = _vol_hist()
    idx = bisect.bisect_left(dates, d) - 1
    if idx < 0: return False
    return zs[idx] >= VOL_HIGH_CUT

def fmt(e):
    side = 'BUY' if e['dir'] == 1 else 'SELL'
    if e['kind'] == 'ENTRY':
        return (f"GOLD {side} now  ({'first trade' if e['first'] else 'add, same direction'} · {e['tag']})\n"
                f"Signal price {e['px']:.2f} | stop {e['stop']:.2f} ({abs(e['px'] - e['stop']):.1f} away) | no target\n"
                f"Size {SIZE:.2f} oz | hold until the stop or the day-end close at {dubai(eod_of(pd.Timestamp(e['t']).normalize()))} Dubai | {dubai(e['t'])} Dubai")
    if e['kind'] == 'STOP':
        return f"GOLD {side} ({e['tag']}, entered {dubai(e['t0'])}): stop hit at {e['px']:.2f} | {dubai(e['t'])} Dubai"
    if e['kind'] == 'EOD':
        return f"GOLD END OF DAY: close ALL open gold trades now ({e.get('n', '')} from today's signals) | {dubai(e['t'])} Dubai"
    if e['kind'] == 'SKIP':
        return f"GOLD: first {side} signal skipped by the dollar filter ({e['tag']}) - waiting for the next one | {dubai(e['t'])} Dubai"
    return str(e)

STATUS = {'open': 'open', 'half': 'open', 'stop hit': 'stopped', 'stop at entry': 'be', 'day end': 'eod', 'reversed': 'reversed', 'day lock': 'lock'}
def row(g, k=0, late=False):
    """One v2.10 trade (desk209 leg) -> page/journal row. price = his fill (Ask for buys, Bid for sells).
    late=True (fixpack 22 Oct): the desk could not show this trade in time (inputs or data arrived after its entry minute) -
    while it runs its status is 'late', never 'open', so the demo auto-trader never enters it; it is kept on paper only."""
    st = STATUS.get(g['status'], g['status']); half = g.get('half_t') is not None
    nxt = None
    if st == 'open' and late:
        st = 'late'; nxt = (f"LATE - do not enter: the desk could only show this signal after its time (inputs / prices arrived late). "
                            f"Paper only · stop {g['stop']:.2f} or the day-end close")
    elif st == 'open':
        nxt = (f"Half banked at {g['half_px']:.2f} · stop is at entry {g['entry']:.2f} · hold the rest to the stop or the day-end close"
               if half else (f"Close HALF at {g['half_px']:.2f}, then move the stop to entry {g['entry']:.2f} · stop now {g['stop']:.2f}" if g.get('half_px') is not None
               else f"Hold to the stop {g['stop']:.2f} or the day-end close · no half-close" + (f" · size x{g.get('size_x', 1):g}" if g.get('size_x', 1) != 1 else "")))
    return dict(time=dubai(g['t']), side='BUY' if g['dir'] == 1 else 'SELL', tag=g['tag'], price=g['entry'], stop=g['stop'],
                stop0=g['stop0'], half_px=g['half_px'], half=half, half_time=(dubai(g['half_t']) if half else None), size=SIZE,
                status=st, first=(k == 0), exit=g['exit'], exit_time=(dubai(g['exit_t']) if g['exit_t'] is not None else None),
                pnl=(None if g['pnl_oz'] is None else round(g['pnl_oz'] * g.get('size_x', 1.0), 2)), pnl_oz=g['pnl_oz'], size_x=g.get('size_x', 1.0), rwf=None, next=nxt, late=bool(late))
def act_rows(acts):
    return [dict(time=dubai(a['t']), kind=a['kind'], side=a['side'], text=a['text']) for a in acts]

# ---------------- fixpack 22 Oct: inputs gate, shown-row freeze, late rows, data checks ----------------
REQ = ('d1', 'd5', 'vix', 'tnx')                    # required daily inputs: no new gold row while one of these is unknown (9)
NAMES = dict(d1='dollar 1-day', d5='dollar 5-day', vix='VIX 5-day', tnx='US 10y 5-day', attn='low attention (Wikipedia)', regime='dollar-driven')
WORDS = dict(d1='dollar_1d', d5='dollar_5d', vix='vix_5d', tnx='tnx_5d', attn='attn_z')
LATE_MIN = 5                                        # a row first shown more than 5 min after its entry minute = LATE (= autotrade MAX_AGE_MIN)
SHOWN = os.path.join(HERE, 'docs', 'gold_shown.json')   # rows the desk has shown today: {day: {time|side|tag: frozen row}}

def mm_of(m1): return dict(t=m1.index.values.astype('datetime64[m]'), o=m1.o.values, h=m1.h.values, l=m1.l.values, c=m1.c.values)
def rkey(t, d, tag): return f"{dubai(t)}|{'BUY' if d > 0 else 'SELL'}|{tag}"     # same parts as autotrade.key_of (time, side, tag)

def load_inputs(day, now, old):
    """Today's daily inputs. Fetched once; while one is unknown (9: dollar / VIX / US10y / attention) it is re-tried every 30 min,
    and a value already known is NEVER replaced by a re-try (no flip-flop of known inputs during the day)."""
    unknown = lambda x: [k for k in REQ + ('attn',) if x.get(k, 9) == 9]
    if old is not None and not (unknown(old) and now - pd.Timestamp(old.get('fetched', '2000-01-01')) > pd.Timedelta(minutes=30)):
        return old
    new = I.daily_inputs(day.date()); new['fetched'] = str(now)
    if old is not None:
        for k in REQ + ('attn',):
            if old.get(k, 9) != 9: new[k] = old[k]; new[WORDS[k]] = old.get(WORDS[k])
        for k in ('regime', 'corr', 'ready_at', 'waiting_since', 'missing'):
            if k in old: new[k] = old[k]
    return new

def fingerprint(res):
    legs, acts, skipped, _ = res
    return ([(str(g['t']), g['dir'], g['tag'], g['status'], g['exit']) for g in legs], [(str(x['t']), x['dir']) for x in skipped])

def frozen_leg(s, mm, eod, now, acts):
    """A row the desk already showed but today's re-run no longer gives (or gives with another entry / stop): kept with its SHOWN
    entry and stop, closed by its own stop (entry minute after the fill, like desk209), a day lock / reversal in today's actions,
    or the day-end close."""
    T = mm['t']; O, H, L, C = (np.asarray(mm[k], float) for k in ('o', 'h', 'l', 'c')); SP = DK.SP
    d = s['dir']; t0 = np.datetime64(pd.Timestamp(s['t']), 'm'); stop = s['stop']; e64 = np.datetime64(eod, 'm')
    g = dict(t=t0, dir=d, tag=s['tag'], entry=s['entry'], stop=stop, stop0=s['stop0'], half_px=None, half_t=None, status='open',
             exit=None, exit_t=None, pnl_oz=None, size_x=s['size_x'], frozen=True)
    def close(px, t, why): g.update(exit=round(px, 2), exit_t=t, status=why, pnl_oz=round(d * (px - s['entry']), 2))
    ends = {}
    for a in acts:
        if a['kind'] == 'LOCK' or (a['kind'] == 'REVERSE' and (1 if a['side'] == 'BUY' else -1) != d):
            ends.setdefault(np.datetime64(pd.Timestamp(a['t']), 'm'), (a['price'], 'day lock' if a['kind'] == 'LOCK' else 'reversed'))
    for j in range(int(np.searchsorted(T, t0, side='left')), len(T)):
        if T[j] >= e64: break
        if T[j] == t0:
            at_open = abs(s.get('p0', np.nan) - O[j]) < 1e-9; up = C[j] >= O[j]
            hit = ((L[j] if (at_open or not up) else C[j]) <= stop) if d > 0 else ((H[j] if (at_open or up) else C[j]) + SP >= stop)
            px = stop
        else:
            hit = (L[j] <= stop) if d > 0 else (H[j] + SP >= stop); px = min(stop, O[j]) if d > 0 else max(stop, O[j] + SP)
        if hit: close(px, T[j], 'stop hit'); break
        if T[j] in ends and ends[T[j]][0] is not None: close(ends[T[j]][0], T[j], ends[T[j]][1]); break
    if g['exit'] is None and np.datetime64(now, 'm') >= e64 and len(T):
        k = min(max(int(np.searchsorted(T, e64, side='left')) - 1, 0), len(T) - 1); close(C[k] if d > 0 else C[k] + SP, e64, 'day end')
    return g

def publish(legs, acts, S, mm, now, eod, open_ok, ready):
    """desk209 legs -> page/journal rows, so that a row the desk has SHOWN never vanishes and never changes entry / stop / size later
    in the day (S = today's shown rows, updated here), no NEW row appears while a required input is missing (open_ok False), and a
    new row is LATE (status 'late', not 'open') when its entry minute is before the inputs became complete (ready) or more than
    LATE_MIN minutes before now. Also returns the actions that belong to published rows (late OPEN / ADD marked)."""
    out, used, pub, late_li = [], set(), set(), set()
    for g in legs:
        k = rkey(g['t'], g['dir'], g['tag']); s = S.get(k)
        if s is not None:
            if abs(s['entry'] - g['entry']) < 0.011 and abs(s['stop0'] - g['stop0']) < 0.011:
                g['size_x'] = s['size_x']; used.add(k); pub.add(g['li']); out.append((g, s['late']))
                if s['late']: late_li.add(g['li'])
            continue                                   # re-run changed a shown row: the shown one is kept (frozen) below
        if not open_ok: continue                       # inputs missing: no new rows
        tb = pd.Timestamp(g['t'])
        late = bool((ready is not None and tb < ready) or now - tb > pd.Timedelta(minutes=LATE_MIN))
        S[k] = dict(t=str(tb), dir=int(g['dir']), tag=g['tag'], p0=float(g.get('p0', g['entry'])), entry=g['entry'], stop0=g['stop0'],
                    stop=g['stop'], size_x=g.get('size_x', 1.0), shown_at=str(now), late=late)
        used.add(k); pub.add(g['li']); out.append((g, late))
        if late: late_li.add(g['li'])
    for k, s in S.items():
        if k not in used: out.append((frozen_leg(s, mm, eod, now, acts), s['late']))
    out.sort(key=lambda x: pd.Timestamp(x[0]['t']))
    rows = [row(g, i, late) for i, (g, late) in enumerate(out)]
    keep = []
    for a in acts:
        li = a.get('li')
        if li is None:
            if open_ok or (pub and a['kind'] in ('LOCK', 'CLOSE_ALL', 'REVERSE')): keep.append(a)
        elif li in pub:
            keep.append(dict(a, text='LATE - do not enter (paper only): ' + a['text']) if (li in late_li and a['kind'] in ('OPEN', 'ADD')) else a)
    return rows, keep

def feed_problems(feed, m1, h1, day, now):
    """Partial or stale minute data (weekdays, 1:30-23:58 broker). [] = fine. Flags: first bar late while the hourly feed has
    earlier bars today / a gap over 3 min in today's bars that is recent (ended < 15 min ago) or comes with a price window the
    feed refused (400/404 = the old silent drop) / newest closed bar over 2 min old. An older hole with no refused window survived
    15 re-fetches: that is the broker's own history (gold M1 2025-26: holes > 3 min on 26 of 429 days, mostly ~2 am) - not flagged,
    else one such hole would block the desk for the whole day."""
    if now.dayofweek >= 5 or now < day + pd.Timedelta(minutes=90) or now >= day + pd.Timedelta(hours=23, minutes=58): return []
    hb = h1[(h1.index >= day) & (h1.index <= now)]
    if not len(m1): return ['no minute bars yet today'] if len(hb) else []        # no hourly bars either: market shut (holiday)
    p = []; first = m1.index[0]; dropped = list(getattr(feed, 'dropped', None) or [])
    if first > day + pd.Timedelta(minutes=90) and len(hb) and hb.index[0] < first.floor('h'):
        p.append(f"first minute bar only at {first:%H:%M} broker")
    ix = m1.index.to_series(); dif = ix.diff()
    for t, gp in dif[dif > pd.Timedelta(minutes=3)].items():
        if dropped or now - t < pd.Timedelta(minutes=15):
            p.append(f"{int(gp.total_seconds() // 60)} min gap in minute bars before {t:%H:%M} broker")
    age = now - (m1.index[-1] + pd.Timedelta(minutes=1))
    if age > pd.Timedelta(minutes=2): p.append(f"newest closed minute bar is {age.total_seconds() / 60:.0f} min old")
    if p and dropped: p.append(f"{len(dropped)} price window(s) refused by the feed")
    return p

def data_problem(now, probs):
    """Keep the last good gold card, flag feed_error (the auto-trader then changes nothing) and say why. No re-run, no journal write."""
    old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
    print('GOLD data problem:', probs)
    if g is not None:
        g['message'] = (f"Price data incomplete at {dubai(now)} Dubai ({'; '.join(probs)}) - the page shows the last good update; "
                        f"it retries every minute."); g['feed_error'] = True
        dumpj(old, PORTAL, indent=1)

def compute(h1, m1, day, now, inp):
    """The EA's trades for broker day `day` as of `now` (same steps for today and for a missed day)."""
    D1 = daily_bars(h1, day)
    D = E.Daily(D1.index.values.astype('datetime64[D]'), D1.o.values, D1.h.values, D1.l.values, D1.c.values)
    hh = h1[h1.index <= now]
    Hh = E.Hourly(hh.index.values.astype('datetime64[m]'), hh.h.values, hh.l.values, hh.c.values)
    dayst = np.datetime64(day.date(), 'D')
    one_am = dayst.astype('datetime64[m]') + np.timedelta64(60, 'm')
    reg = inp.get('regime')
    einp = dict(d5=inp['d5'], d1=inp['d1'], vix=inp['vix'], tnx=inp['tnx'], attn=inp.get('attn', 0),
                regime=lambda t: (reg if (reg is not None and t >= one_am) else 0))
    mm = dict(t=m1.index.values.astype('datetime64[m]'), o=m1.o.values, h=m1.h.values, l=m1.l.values, c=m1.c.values)
    sig = E.run_day(dayst, D, Hh, mm, einp) if len(m1) else []
    taken = [t for t in sig if not t.get('skipped')]; skipped = [t for t in sig if t.get('skipped')]
    ry = None
    if dayst >= DK.V215_FROM:
        try: ry = realyield(day)
        except Exception as e: print('real yield failed', type(e).__name__, e)
    vol = False
    try: vol = volume_high(day)
    except Exception as e: print('volume sizing failed', type(e).__name__, e)
    legs, acts = DK.run(taken, dayst, mm, np.datetime64(now, 'm'), D.atr(0), np.datetime64(eod_of(day), 'm'), label=dubai, ry=ry, vol=vol) if len(m1) else ([], [])
    return legs, acts, skipped, D

def missed_days(J, now, cache):
    """Past broker days (last 9 days, inputs still cached) that never got their day-end run."""
    today = str(now.normalize().date())
    return [d for d in J.get('days', []) if not d.get('final') and d['date'] < today and d['date'] in cache
            and (now.normalize() - pd.Timestamp(d['date'])).days <= 9]

def finish_missed_days(feed, h1, now):
    """CATCH-UP: a past broker day whose day-end run never happened (e.g. GitHub down at midnight) is replayed to its end and
    written to the journal as final; if trades were still open at the day-end close, one Telegram tells him to close them."""
    J = loadj(JOURNAL, None)
    if not J: return
    today = str(now.normalize().date()); cache = loadj(INPUTS, {}); state = loadj(STATE, {}); changed = False
    for d in missed_days(J, now, cache):
        try:
            day = pd.Timestamp(d['date']); inp = dict(cache[d['date']])
            m1 = feed.m1_today(day); m1 = m1[m1.index < day + pd.Timedelta(days=1)]
            if not len(m1) or m1.index.max() < day + pd.Timedelta(hours=22):          # minutes do not reach the day end: try later
                print('missed day', d['date'], 'not caught up: minute bars end', (m1.index.max() if len(m1) else None)); continue
            probs = feed_problems(feed, m1, h1, day, min(m1.index.max() + pd.Timedelta(minutes=1), day + pd.Timedelta(hours=23, minutes=57)))
            if probs: print('missed day', d['date'], 'not caught up: minute data incomplete', probs); continue   # final = never rewritten
            if inp.get('regime') is None:
                reg, corr = regime_today(feed, h1, day, day + pd.Timedelta(hours=23))
                if reg is not None: inp.update(regime=reg, corr=corr)
            was_open = any(t.get('status') in ('open', 'close_now') for t in d.get('trades', []))
            end = day + pd.Timedelta(hours=23, minutes=59)
            legs, acts, skipped, _ = compute(h1, m1, day, end, inp)
            SH = loadj(SHOWN, {})
            if d['date'] in SH:                          # rows the desk showed live stay as shown; rows it never showed are LATE
                rows, _ = publish(legs, acts, dict(SH[d['date']]), mm_of(m1), end, eod_of(day), True,
                                  pd.Timestamp(inp['ready_at']) if inp.get('ready_at') else None)
            else: rows = [row(g, k) for k, g in enumerate(legs)]
        except Exception as e:
            print('missed day', d['date'], 'not caught up:', type(e).__name__, e); continue
        d.update(side=(rows[0]['side'] if rows else None), trades=rows, skipped=len(skipped), final=True, caught_up=str(now))
        changed = True
        if was_open or any(r['status'] == 'eod' for r in rows):
            k = f"MISSED_EOD|{d['date']}"; sent = set(state.get(today, []))
            if k not in sent and send(f"GOLD: the day-end close for {day.strftime('%a %d %b')} was missed (the signal server was down). "
                                      f"If any gold trade from that day is still open, close it now. | {dubai(now)} Dubai"):
                sent.add(k); state[today] = sorted(sent)
        print('caught up missed day', d['date'], len(rows), 'trades')
    if changed:
        dumpj(J, JOURNAL, indent=1); dumpj(state, STATE, indent=0)

def summary(J, day):
    allt = [t for d in J['days'] for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]
    pnl = [t['pnl'] for t in allt if t.get('pnl') is not None]
    wd = max(1, len(pd.bdate_range(J['start'], str(day.date()))))
    tdays = sum(1 for d in J['days'] if d['trades'])
    return dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), trades=len(allt),
                direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), decided=len(dec),
                days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                avg_pnl=(round(sum(pnl) / len(pnl), 2) if pnl else None), closed=len(pnl),
                total_pnl_01=(round(sum(p * 0.1 for p in pnl), 2) if pnl else None))

def write_summary():
    J = loadj(JOURNAL, None)
    if J and J.get('days'):
        J['summary'] = summary(J, pd.Timestamp(J['days'][-1]['date'])); dumpj(J, JOURNAL, indent=1)
        old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
        if g is not None: g['journal'] = J['summary']; dumpj(old, PORTAL, indent=1)

def main():
    now = F.broker_now(); day = now.normalize(); test = '--test' in sys.argv
    if now.dayofweek >= 5 and not test:
        if missed_days(loadj(JOURNAL, {}), now, loadj(INPUTS, {})):
            try: feed, src = F.get_feed(); finish_missed_days(feed, feed.h1(days=460), now); write_summary()
            except Exception as e: print('weekend catch-up skipped:', type(e).__name__, e)
        old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
        if g: g.update(state='closed', message='Market closed for the weekend'); dumpj(old, PORTAL, indent=1)
        print('weekend'); return
    feed, src = F.get_feed()
    h1 = feed.h1(days=460)
    try: finish_missed_days(feed, h1, now)
    except Exception as e: print('catch-up skipped:', type(e).__name__, e)
    closed = lambda d: d[d.index + pd.Timedelta(minutes=1) <= now]                      # closed minute bars only
    m1 = closed(feed.m1_today(day))
    probs = feed_problems(feed, m1, h1, day, now)
    if probs:                                            # fixpack 22 Oct: one immediate re-fetch, then flag feed_error (no silent re-run)
        m1 = closed(feed.m1_today(day)); probs = feed_problems(feed, m1, h1, day, now)
    if probs and not test: data_problem(now, probs); return
    # daily outside values (cached per broker day; a missing one re-tried every 30 minutes; known values never replaced)
    cache = loadj(INPUTS, {}); key = str(day.date()); inp = load_inputs(day, now, cache.get(key))
    reg_err = False
    if inp.get('regime') is None:
        reg, corr, reg_err = regime_today(feed, h1, day, now, with_err=True)
        if reg is not None: inp.update(regime=reg, corr=corr)
    reg = inp.get('regime')
    res = compute(h1, m1, day, now, inp); taken, acts, skipped, D = res          # taken = desk209 legs
    # fixpack 22 Oct INPUTS GATE: no new gold row while a required input is unknown. Attention / dollar-driven (when their fetch
    # failed) only hold the desk when the other value would change today's trades so far.
    missing = [NAMES[k] for k in REQ if inp.get(k, 9) == 9]
    for k, unknown in (('attn', inp.get('attn') == 9), ('regime', reg_err)):
        if unknown and fingerprint(compute(h1, m1, day, now, dict(inp, **{k: 1}))) != fingerprint(res): missing.append(NAMES[k])
    if missing: inp.setdefault('waiting_since', str(now)); inp['missing'] = missing
    elif inp.get('waiting_since'):                       # inputs complete again: rows before this moment can only be LATE
        inp['ready_at'] = str(now); inp.pop('waiting_since'); inp.pop('missing', None)
    cache = {k: v for k, v in cache.items() if k >= str((day - pd.Timedelta(days=10)).date())}; cache[key] = inp
    dumpj(cache, INPUTS, indent=1)
    eod = eod_of(day)                                   # day-end close (22:50 broker on Fridays and in US winter time)
    SH = loadj(SHOWN, {}); S = SH.get(key, {})
    rows, acts = publish(taken, acts, S, mm_of(m1), now, eod, not missing, pd.Timestamp(inp['ready_at']) if inp.get('ready_at') else None)
    SH = {k: v for k, v in SH.items() if k >= str((day - pd.Timedelta(days=5)).date())}; SH[key] = S; dumpj(SH, SHOWN, indent=0)
    # ---- actions: shown on the page only; a NEW action is recorded in sent.json so loop.py pushes the page at once
    state = loadj(STATE, {}); sent = set(state.get(key, []))
    for a in acts:
        k = f"A|{a['kind']}|{pd.Timestamp(a['t']).isoformat()}|{a['text'][:48]}"
        if k not in sent: print('ACTION', dubai(a['t']), a['text']); sent.add(k)
    if test:
        last = float(m1.c.iloc[-1]) if len(m1) else float('nan')
        send(f"GOLD v2.06 signal system TEST OK [{src}]\nLast price {last:.2f} | broker day {day.date()} | daily range {D.atr(0):.1f}\n"
             f"Dollar 1d/5d {inp.get('dollar_1d')}/{inp.get('dollar_5d')} · VIX {inp.get('vix_5d')} · US10y {inp.get('tnx_5d')} · dollar-driven {reg} · low attention {inp.get('attn')}\n"
             f"Trades today so far: {len(taken)} | {dubai(now)} Dubai\n"
             f"CHECK: daily bars {D.n} ({str(D.t[0]) if D.n else '-'} .. {str(D.t[-1]) if D.n else '-'}) | hourly bars {len(h1)} | ADX {D.adx():.1f} | "
             f"dollar-driven corr {inp.get('corr')} | input notes {inp.get('notes')}")
    state = {k2: v for k2, v in state.items() if k2 >= str((day - pd.Timedelta(days=5)).date())}; state[key] = sorted(sent)
    dumpj(state, STATE, indent=0)
    write_pages(now, day, m1, rows, skipped, inp, reg, src, eod, D.atr(0), acts, missing)
    print(f'{now} broker | {src} | trades today {len(rows)} | skipped {len(skipped)} | missing {missing} | inputs {inp}')

def write_pages(now, day, m1, rows, skipped, inp, reg, src, eod, datr, acts=(), missing=()):
    """rows = published rows (run.publish: frozen once shown, LATE when shown too late, none while inputs are missing)."""
    if now >= eod: rows = [dict(r, status='close_now') if r['status'] == 'open' else r for r in rows]
    # page only: after the close, trades the desk booked at the day-end price are still open in his account until he closes them
    page_rows = [dict(r, status='close_now') if (now >= eod and r['status'] == 'eod') else r for r in rows]
    # ---- journal (one record per broker day, replaced on every run of that day UNTIL it is final - fixpack 22 Oct: a final day is never overwritten)
    J = loadj(JOURNAL, dict(start=str(day.date()), days=[]))
    was_final = any(d['date'] == str(day.date()) and d.get('final') for d in J['days'])
    days = J['days'] if was_final else [d for d in J['days'] if d['date'] != str(day.date())]
    if now.dayofweek < 5 and not was_final:
        days.append(dict(date=str(day.date()), label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None),
                         trades=rows, skipped=len(skipped), final=bool(now >= eod)))
    J['days'] = sorted(days, key=lambda d: d['date'])
    J['summary'] = summary(J, day)
    dumpj(J, JOURNAL, indent=1)
    # ---- page data
    old = loadj(PORTAL, {}); others = {k: v for k, v in (old.get('markets') or {}).items() if k != 'GOLD'}
    V211 = np.datetime64(day.date(), 'D') >= DK.V211_FROM               # v2.11 rules (no half-close) from the switch day
    V215 = np.datetime64(day.date(), 'D') >= DK.V215_FROM               # v2.15 rules from their switch day
    last_sig = now >= day + pd.Timedelta(hours=E.S['Signal_Last_Hour'])
    sig_end = dubai(day + pd.Timedelta(hours=E.S['Signal_Last_Hour']))          # 8:00 pm Dubai in US summer time, 9:00 pm in US winter
    wait = (f" Inputs missing - waiting ({', '.join(missing)} not loaded yet, re-tried every 30 min): no NEW gold trade until they "
            f"load; signals before then will show as LATE (do not enter).") if missing else ''
    if now.dayofweek >= 5: state, msg = 'closed', 'Market closed for the weekend'
    elif missing and not rows and not last_sig: state, msg = 'waiting', wait.strip()
    elif rows:
        side = rows[0]['side']; state = side.lower()
        msg = (f"{side} day — up to 2 {side} trades (a 3rd only when every open trade is up 1.25x its stop). Each runs to its stop or the day-end close at {dubai(eod)} Dubai. Day lock: once today reaches +2R, close all if it falls back to +0.5R." if V215 else
               f"{side} day — up to 2 {side} trades. Each runs to its stop or the day-end close at {dubai(eod)} Dubai (no half-close)." if V211 else
               f"{side} day — up to 2 {side} trades. Close HALF at the ½ level, then move the stop to entry; the rest runs to its stop or the day-end close at {dubai(eod)} Dubai.") + wait
    elif skipped and not last_sig: state, msg = 'blocked', 'The first signal was skipped by the dollar filter — watching for the next one.'
    elif last_sig: state, msg = 'none', f'No trade today — no signal (new signals stop at {sig_end} Dubai).' + wait
    else: state, msg = 'waiting', f'Waiting for the first signal (signals can come until {sig_end} Dubai).'
    spark = []
    if len(m1):
        g5 = m1[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()   # 5-min candles for the page: [time, close, open, high, low]
        spark = [[dubai(t), round(float(r.c), 2), round(float(r.o), 2), round(float(r.h), 2), round(float(r.l), 2)] for t, r in g5.iterrows()]
    last = float(m1.c.iloc[-1]) if len(m1) else None; first = float(m1.o.iloc[0]) if len(m1) else None
    hist = []
    for d in J['days'][-15:][::-1]:
        tr = d['trades']
        hist.append(dict(date=d['date'], label=d['label'], state=(d['side'] or 'none').lower() if tr else 'none', entries=len(tr),
                         stopped=sum(t['status'] == 'stopped' for t in tr), eod=sum(t['status'] in ('eod', 'close_now') for t in tr),
                         running=sum(t['status'] == 'open' for t in tr), rw=sum(1 for t in tr if t.get('rwf') == 1),
                         rd=sum(1 for t in tr if t.get('rwf') is not None),
                         pnl=(round(sum(t['pnl'] for t in tr if t.get('pnl') is not None), 2) if any(t.get('pnl') is not None for t in tr) else None)))
    gold = dict(code='GOLD', name='Gold', symbol='XAU/USD', live=True, version=('v2.15' if V215 else 'v2.11' if V211 else 'v2.10'), actions=act_rows(acts), actions_day=str(day.date()), feed_error=False, state=state, message=msg, price=last, close_at=dubai(eod),
                change=(None if last is None or first is None else round(last - first, 2)), size=SIZE, datr=round(datr, 2),
                open_now=sum(r['status'] in ('open', 'close_now') for r in page_rows), entries=page_rows, spark=spark, history=hist,
                inputs=dict(dollar_1d=inp.get('dollar_1d'), dollar_5d=inp.get('dollar_5d'), vix_5d=inp.get('vix_5d'), tnx_5d=inp.get('tnx_5d'),
                            dollar_driven=(None if reg is None else bool(reg)), corr=inp.get('corr'), low_attention=(None if inp.get('attn') == 9 else bool(inp.get('attn', 0))), missing=list(missing),
                            notes=inp.get('notes', [])),
                stats=(BACKTEST if V215 else BACKTEST_V211 if V211 else BACKTEST_V210), journal=J['summary'])
    data = dict(updated=F.broker_to_dubai(now).strftime('%a %d %b · %-I:%M %p').replace('AM', 'am').replace('PM', 'pm'),
                source=src, markets=dict(GOLD=gold, **others))
    dumpj(data, PORTAL, indent=1)

def safe_main():
    """Never crash the page: if a price source fails, say so on the page and keep the last good data."""
    import traceback
    try:
        main()
    except Exception as e:
        traceback.print_exc()
        try:
            old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
            if g is not None:
                now = F.broker_now()
                g['message'] = (f"Price feed problem at {F.broker_to_dubai(now).strftime('%-I:%M %p').lower()} Dubai "
                                f"({type(e).__name__}) - the page shows the last good update; it retries every minute.")
                g['feed_error'] = True
                dumpj(old, PORTAL, indent=1)
        except Exception:
            traceback.print_exc()
    try:                                    # USDJPY paper page (separate from gold; a yen failure never touches the gold card)
        import yen_run
        yen_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import yen_run; yen_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # WTI paper page (separate; a WTI failure never touches the gold or USDJPY cards)
        import wti_run
        wti_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import wti_run; wti_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # Nasdaq paper page (separate; a Nasdaq failure never touches the other cards)
        import nq_run
        nq_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import nq_run; nq_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # S&P 500 paper page (22 Oct, version A; copies the Nasdaq picks written just above)
        import sp_run
        sp_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import sp_run; sp_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # GBP/USD paper page (GBP_CROWD v1.02, 24 Oct; manual - the auto-trader does not copy it)
        import gbp_run
        gbp_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import gbp_run; gbp_run.fail(e)
        except Exception:
            traceback.print_exc()
    try:                                    # Brent paper page (v1.04, 6 Nov; copied to the demo auto-trader - his 6 Nov go-ahead)
        import brent_run
        brent_run.main()
    except Exception as e:
        traceback.print_exc()
        try:
            import brent_run; brent_run.fail(e)
        except Exception:
            traceback.print_exc()

if __name__ == '__main__':
    safe_main()
