"""GBP/USD PAPER signals for the page - GBP_CROWD v1.04 rules (gbp_engine.py; MT4-proven 24 Oct 2026, his run 5: 3,810 trades
2011-01..2026-06, net $15,966.95 at 0.10 lot, max DD $1,636.34, net/DD 9.76, PF 1.21, profit days 54.3% of weekdays, losing years 3).
v1.04 adds the busy/calm regime rules (gbp_engine.mode): regime from docs/gbp_daily.json (daily highs/lows: HistData seed to 30 Sep 2026 +
Capital.com days on top, kept up to date here) and, on calm days, the 00:00 -> 10:00 GBP vs EUR gap (Capital.com minute opens). One trade a day at most,
copied onto the Capital.com DEMO by the auto-trader from 26 Oct (his choice A, 26 Oct; was manual - his choice B, 23 Oct). No phone alerts, no real money.
Called by run.py every minute. Each run: (1) the weekly CFTC British Pound report (publicreporting.cftc.gov, free, no key) is re-read
at most once an hour and cached in docs/cftc_gbp.json - the desk keeps working on the cached report if the CFTC site is down;
(1b) v1.03: the weekly CFTC EURO FX report the same way (docs/cftc_eur.json); (2) the 14-day average range and, for layer 4,
EUR/GBP at 10:00 broker of the last 20 trading days, from Capital.com hourly bars (GBPUSD + EURUSD, once a day); (3) today's Capital.com minute bars (bid + spread) -> gbp_engine.trade();
(4) docs/journal_gbp.json (every paper trade) and docs/data.json -> markets.GBPUSD (the page)."""
import os, json, time, requests, numpy as np, pandas as pd
import feeds as F, gbp_engine as E
DEADLINE = time.time() + 240          # loop.py resets this every minute; the GBP part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
JOUR = os.path.join(HERE, 'docs', 'journal_gbp.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
CFTC = os.path.join(HERE, 'docs', 'cftc_gbp.json'); CFTC_EUR = os.path.join(HERE, 'docs', 'cftc_eur.json'); HIST = os.path.join(HERE, 'docs', 'gbp_daily.json'); HIST_KEEP = 500          # days kept (regime needs 250 + 14)
CFTC_URL = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'
EPIC = os.environ.get('CAPITAL_EPIC_GBP', 'GBPUSD'); EPIC_EUR = os.environ.get('CAPITAL_EPIC_EUR', 'EURUSD')
RULES = 'v1.05'
PASS = dict(pf=1.10, months=3)
BACKTEST = dict(direction='—', days='93% of weekdays traded, 1 trade a day (2 on ~14 days a year: + holiday sell) · profit days 55%', perday='0.98', win='7.9% hit target · 57.3% closed in profit', pf='1.19',
                net='+$15,515.36 at 0.10 lot (net/DD 10.26)',
                source='MT4 test GBP_CROWD v1.05 (his run 7, 7 Nov 2026, spread 1.8 pips), 2010-08..2026-06-19, 4,048 trades (200 holiday sells +$1,371); max DD $1,512.42; v1.04 same data: $14,144 / DD $1,792')

class FeedError(RuntimeError):
    pass

_DAILY = {}                            # today's daily-range table (kept between minutes inside one desk job)

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

# ---------------- weekly CFTC report ----------------
def cftc_rows(get=None, mcode='096742', path=None, name='CFTC'):
    """Cached weekly rows; refreshed from the CFTC site at most once an hour. Returns (rows, note). mcode 096742 = British Pound,
    099741 = Euro FX (layer 5)."""
    path = path or CFTC
    c = loadj(path, {}); rows = c.get('rows') or []; note = None
    if time.time() - float(c.get('fetched', 0)) >= 3600 or not rows:
        try:
            if get is not None: new = get()
            else:
                r = requests.get(CFTC_URL, timeout=20, params={'$where': f"cftc_contract_market_code='{mcode}'", '$order': 'report_date_as_yyyy_mm_dd DESC', '$limit': 200,
                                 '$select': 'report_date_as_yyyy_mm_dd,open_interest_all,lev_money_positions_long,lev_money_positions_short,nonrept_positions_long_all,nonrept_positions_short_all'})
                r.raise_for_status()
                new = [dict(d=str(x['report_date_as_yyyy_mm_dd'])[:10], oi=float(x['open_interest_all']), lev_l=float(x['lev_money_positions_long']),
                            lev_s=float(x['lev_money_positions_short']), nr_l=float(x['nonrept_positions_long_all']), nr_s=float(x['nonrept_positions_short_all'])) for x in r.json()]
            if len(new) >= 60:
                rows = sorted({x['d']: x for x in rows + new}.values(), key=lambda x: x['d'])[-260:]
                dumpj(dict(fetched=time.time(), source=CFTC_URL, rows=rows), path, indent=0)
            else: note = f'{name} site returned only {len(new)} weeks - using the saved report'
        except Exception as e:
            note = f'{name} site not reachable ({type(e).__name__}) - using the saved report'
            if rows: dumpj(dict(c, fetched=time.time() - 3000), path, indent=0)      # retry in ~10 min, not every minute
    if not rows: raise FeedError(f'no {name} report saved yet and the CFTC site is not reachable')
    return rows, note

def weekly(rows):
    W = pd.DataFrame(rows); W.index = pd.to_datetime(W.pop('d')); return E.codes(W[['oi', 'lev_l', 'lev_s', 'nr_l', 'nr_s']].astype(float))
def weekly_eur(rows):
    W = pd.DataFrame(rows); W.index = pd.to_datetime(W.pop('d')); return E.eur_codes(W[['oi', 'lev_l', 'lev_s']].astype(float))

# ---------------- prices ----------------
def to_utc(b): return (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)

def prices(feed, res, start_b, end_b, step, epic=None):
    """Capital.com GBP/USD bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('GBP time budget used up - next run continues')
        t1 = min(end, t0 + step)
        r = requests.get(f'{feed.base}/api/v1/prices/{epic or EPIC}', headers=feed.h, timeout=20,
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
    """weekday high/low per broker day from hourly bars of the last 45 days (before today), plus g10 = GBP/USD 10:00 broker open
    (layer 4 needs 20 trading days)."""
    h = prices(feed, 'HOUR', day - pd.Timedelta(days=45), day, pd.Timedelta(hours=900))
    h = h[h.index < day]
    if not len(h): return pd.DataFrame(columns=['h', 'l', 'g10'])
    d = h.groupby(h.index.normalize()).agg(h=('h', 'max'), l=('l', 'min'))
    g10 = h[(h.index.hour == 10) & (h.index.minute == 0)].o; g10.index = g10.index.normalize()
    d['g10'] = g10.reindex(d.index); return d
def eur10(feed, day):
    """EUR/USD per broker day of the last 45 days (before today): e10 = 10:00 broker hourly open (layer 4), h / l = day high / low (v1.04 gap)."""
    h = prices(feed, 'HOUR', day - pd.Timedelta(days=45), day, pd.Timedelta(hours=900), epic=EPIC_EUR)
    h = h[h.index < day]
    if not len(h): return pd.DataFrame(columns=['e10', 'h', 'l'])
    d = h.groupby(h.index.normalize()).agg(h=('h', 'max'), l=('l', 'min'))
    s = h[(h.index.hour == 10) & (h.index.minute == 0)].o; s.index = s.index.normalize(); d['e10'] = s.reindex(d.index); return d
def eur_opens(feed, day):
    """today's EUR/USD minute opens at 00:00 and 10:00 broker (first bar within 5 minutes, as the research). Returns (e0, e10)."""
    out = []
    for mins in (0, E.ENTRY_MIN):
        t = day + pd.Timedelta(minutes=mins); b = prices(feed, 'MINUTE', t, t + pd.Timedelta(minutes=6), pd.Timedelta(minutes=900), epic=EPIC_EUR)
        b = b[b.index >= t]; out.append(float(b.o.iloc[0]) if len(b) and b.index[0] - t <= pd.Timedelta(minutes=5) else np.nan)
    return tuple(out)
def first_open(b, t):
    b = b[b.index >= t]; return float(b.o.iloc[0]) if len(b) and b.index[0] - t <= pd.Timedelta(minutes=5) else np.nan

# ---------------- v1.04 daily history (regime) ----------------
def hist_merge(key, fresh, day):
    """docs/gbp_daily.json rows for `key` ('gbp' / 'eur') + the freshly fetched days (fresh wins) -> DataFrame h, l (days before today).
    Saved back once a day so the file keeps growing with Capital.com days."""
    H = loadj(HIST, {}); rows = {r[0]: r for r in H.get(key, [])}
    if fresh is not None and len(fresh):
        for t, r in fresh[['h', 'l']].dropna().iterrows():
            if pd.Timestamp(t) < day: rows[str(pd.Timestamp(t).date())] = [str(pd.Timestamp(t).date()), round(float(r.h), 5), round(float(r.l), 5)]
    R = sorted(rows.values())[-HIST_KEEP:]
    if H.get(key + '_saved') != str(day.date()) and fresh is not None and len(fresh):
        H[key] = R; H[key + '_saved'] = str(day.date()); dumpj(H, HIST)
    d = pd.DataFrame([r[1:] for r in R], index=pd.to_datetime([r[0] for r in R]), columns=['h', 'l'], dtype=float)
    return d[d.index < day]
def eg_now(dd, e10):
    """layer 4 side for today from the trading days before today (days that have both 10:00 prices)."""
    if isinstance(e10, pd.DataFrame): e10 = e10['e10']
    v = (e10.reindex(dd.index) / dd['g10']).dropna() if 'g10' in dd else pd.Series(dtype=float)
    return E.eg_side(v.values)

def feed_check(b, now):
    """None if today's closed bars look fresh, else the reason (01:00-23:30 broker only)."""
    hm = now.hour * 60 + now.minute
    if hm < 60 or hm > 23 * 60 + 30: return None
    if not len(b): return 'no price bars received for today'
    age = now - (b.index[-1] + pd.Timedelta(minutes=1))
    if age > pd.Timedelta(minutes=5): return f'newest closed price bar ({dubai(b.index[-1])} Dubai) is {age.total_seconds() / 60:.0f} min old'
    return None

# ---------------- page rows / journal ----------------
def row(t, now_px, cost):
    s = t['dir']; st = t['status']; dp = 5
    hol = t['layer'] == 6; sz = E.HOL_SIZE if hol else 1.0
    live = None if st != 'open' or now_px is None else round((s * (now_px - t['entry']) - cost) * 1e4, 1)
    nxt = None
    if st == 'open':
        cl = f"closes at {dubai(t['t'].normalize() + pd.Timedelta(minutes=E.CLOSE_MIN))} Dubai"
        if hol:
            nxt = f"Hold · HALF-size holiday sell · stop {t['stop']:.5f} · no target · {cl}"
        elif t.get('lock') and t.get('locked'):
            nxt = f"Hold · stop MOVED to {t['stop']:.5f} (entry + 5 pips, locked) · target {t['target']:.5f} (close the WHOLE trade there) · {cl}"
        elif t.get('lock'):
            nxt = (f"Hold · stop {t['stop']:.5f} · target {t['target']:.5f} · when price reaches {t['lock_px']:.5f}, MOVE THE STOP to {t['lock_stop']:.5f} "
                   f"(entry + 5 pips) · no half-close · {cl}")
        else:
            nxt = f"Hold · stop {t['stop']:.5f} · target {t['target']:.5f} (close the WHOLE trade there) · no half-close, no stop move · {cl}"
    return dict(time=dubai(t['t']), side='BUY' if s == 1 else 'SELL', name=E.LAYER_NAME[t['layer']], layer=t['layer'],
                price=round(t['entry'], dp), entry=round(t['entry'], dp), stop=round(t['stop'], dp), stop0=round(t.get('stop0', t['stop']), dp), stop_pips=round(t['sd'] * 1e4, 1),
                mode=t.get('mode', 'normal'), lock_px=None if not t.get('lock') else round(t['lock_px'], dp), locked=bool(t.get('locked')),
                half_px=None if t['target'] is None else round(t['target'], dp), half=(st == 'target'), part=1.0, size=(round(E.HOL_SIZE * E.HOL_STOP, 4) if hol else 'full'), status=st,   # holiday: risk weight 0.75 = half the normal lots at a 1.5 x stop (as the MT4 EA)
               
                exit=None if t['exit'] is None else round(t['exit'], dp), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                pips=None if t['pips'] is None else round(t['pips'], 1), res=None if t['pips'] is None else round(t['pips'], 1),
                res_sized=None if t['pips'] is None else round(t['pips'] * sz, 1), r=None if t['pips'] is None else round(t['pips'] / (t['sd'] * 1e4), 3),
                live=live, spread=round(cost * 1e4, 2), next=nxt)

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t.get('res_sized', t['pips']) for t in allt if t.get('pips') is not None]
    start = D3[0]['date']; end = str((day or pd.Timestamp(D3[-1]['date'])).date())
    wd = max(1, len(pd.bdate_range(start, end))); tdays = sum(1 for d in D3 if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(start).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(t.get('status') == 'target' for t in allt) / len(rr), 1) if rr else None),
                inprofit=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES, direction=None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('res_sized', t.get('pips')) or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None, rep=None, code=0, md=None, pct=None, hol=False):
    rp = '—' if rep is None else pd.Timestamp(rep).strftime('%a %d %b')
    lay = {0: 'no layer on', 1: 'layer 1 (hedge funds crowded)', 2: 'layer 2 (small traders crowded)', 3: 'layer 3 (small traders jumped in)',
           4: 'layer 4 (pound stretched vs euro)', 5: 'layer 5 (euro hedge funds trend)'}[abs(code)]
    note = (f"Today: {'BUY' if code > 0 else 'SELL' if code < 0 else 'NO TRADE'} · {lay} · CFTC report of {rp} · 14-day range "
            + ('—' if A is None else f'{A * 1e4:.0f} pips') + ('' if pct is None else f" · market {'BUSY' if md == 'busy' else 'CALM' if md in ('calm', 'calm_gap') else 'normal'} (range at {100 * pct:.0f}% of its last 250 days)")
            + (' · BUSY rules: stop 1.25 x range, target 1.5 x stop · ' if md == 'busy' else
               ' · CALM rules: stop 1.0 x range, target 1.0 x stop, move the stop to entry + 5 pips once +0.35 x stop in profit; side set at 10:00 against any big overnight GBP-vs-EUR gap · ' if md in ('calm', 'calm_gap') else
               ' · stop 1.0 x range, target 1.0 x stop (close the whole trade there), no half-close · ')
            + ('DAY AFTER A UK/US HOLIDAY: extra HALF-size SELL at 10:00, stop 1.5 x range, no target · ' if hol else '')
            + 'one trade a day at 10:00 broker (11:00 am Dubai in summer, 12:00 pm in winter) · everything closes at 23:45 broker '
            + '(12:45 am Dubai in summer, 1:45 am in winter)')
    return dict(code='GBPUSD', name='GBP/USD', symbol='GBPUSD · Capital.com GBP/USD', live=False, paper=True, status='Paper', version=RULES,
                unit='pips', dp=5, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live GBP/USD signals do as well as the v1.05 MT4 test. The auto-trader places each trade on the Capital.com demo (from 27 Oct). Decision after about 3 months.',
                cost_note='Results are pips per trade after the spread (at least 1.5 pips). 0.01 lot = 1,000 units = $0.10 per pip.',
                net_label='Net pips (v1.05 rules, holiday sell at half size)')

def main(feed=None, get=None, getd=None, cget=None, now=None, eget=None, cget_eur=None, eoget=None):
    global DEADLINE; DEADLINE = time.time() + 75     # own 75 s time budget per market
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    rows_c, cnote = cftc_rows(cget); C = weekly(rows_c)
    gcode, rep = E.code_for(C, day)
    try:
        rows_e, enote = cftc_rows(cget_eur, '099741', CFTC_EUR, 'CFTC euro'); CE = weekly_eur(rows_e); ecode, erep = E.code_for(CE, day)
    except Exception as ex:                                               # layer 5 is optional - layers 1-4 still work
        CE, ecode, erep, enote = None, 0, None, f'euro report unavailable ({type(ex).__name__})'
    if enote: cnote = (cnote + '; ' if cnote else '') + enote
    code = gcode
    if now.dayofweek >= 5:
        prev = mk.get('GBPUSD') or {}
        nxt_code, nxt_rep = E.code_for(C, day + pd.Timedelta(days=7 - day.dayofweek))
        if nxt_code == 0 and CE is not None: nxt_e, _ = E.code_for(CE, day + pd.Timedelta(days=7 - day.dayofweek))
        else: nxt_e = 0
        nx = ('BUY' if nxt_code > 0 else 'SELL') + ' days (pound crowd layers)' if nxt_code else ('day by day: layer 4 (EUR/GBP) first, else ' + ('BUY' if nxt_e > 0 else 'SELL' if nxt_e < 0 else 'no') + ' (euro funds)')
        mk['GBPUSD'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(None, nxt_rep, nxt_code), state='closed',
                            message=f"Market closed for the weekend. Next week: {nx} (CFTC report of {'—' if nxt_rep is None else pd.Timestamp(nxt_rep).strftime('%d %b')}).",
                            entries=[], journal=summary(J), jdays=jdays(J), feed_error=False, cftc_note=cnote)
        dumpj(old, PORTAL, indent=1); print('GBP: weekend'); return
    get = get or minutes; getd = getd or daily
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('GBP paper needs the Capital.com prices')
        feed = F.Capital()
    if _DAILY.get('day') != str(day.date()) or len(_DAILY.get('d', [])) < E.RANGE_DAYS:   # daily ranges fetched once a day (hourly bars)
        _DAILY.update(day=str(day.date()), d=getd(feed, day))
    dd = _DAILY['d']; A = E.avg_range(dd, day)
    eg, egz = 0, np.nan
    if _DAILY.get('eday') != str(day.date()):                             # EUR/USD daily table (layer 4 + v1.04 gap), fetched once a day
        try: _DAILY.update(eday=str(day.date()), e10=(eget or eur10)(feed, day))
        except Exception as ex: _DAILY.update(eday=None, e10=None); cnote = (cnote + '; ' if cnote else '') + f'EUR/USD prices unavailable ({type(ex).__name__})'
    if gcode == 0 and _DAILY.get('e10') is not None: eg, egz = eg_now(dd, _DAILY['e10'])
    code = E.decide(gcode, eg, ecode)
    pct = np.nan                                                          # v1.04 regime: own 14-day range vs its last 250 days
    try:
        gh = hist_merge('gbp', dd, day); pct = E.regime_pct(E.range_hist(gh, day).values)
    except Exception as ex: cnote = (cnote + '; ' if cnote else '') + f'regime history unavailable ({type(ex).__name__}) - v1.03 shape today'
    if not np.isfinite(pct): cnote = (cnote + '; ' if cnote else '') + 'regime history too short - v1.03 trade shape today'
    ed = _DAILY.get('e10'); eA = np.nan
    try:
        eh = hist_merge('eur', ed if isinstance(ed, pd.DataFrame) else None, day); eA = E.avg_range(eh, day)
    except Exception: pass
    code0 = code
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]
    bad = feed_check(b, now)
    if bad: raise FeedError(bad)
    sp = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else 0.0
    cost = max(E.COST, sp)
    t_in = day + pd.Timedelta(minutes=E.ENTRY_MIN)
    dv = np.nan
    if abs(code) in (1, 2, 3) and np.isfinite(pct) and pct < E.CALM_Q and now >= t_in + pd.Timedelta(minutes=1):   # calm day: the gap needs 10:00 prices
        if _DAILY.get('eoday') != str(day.date()) or not np.isfinite(_DAILY.get('eo', (np.nan, np.nan))[1]):
            try: _DAILY.update(eoday=str(day.date()), eo=(eoget or eur_opens)(feed, day))
            except Exception as ex: _DAILY.update(eoday=None, eo=(np.nan, np.nan)); cnote = (cnote + '; ' if cnote else '') + f'EUR/USD minute prices unavailable ({type(ex).__name__})'
        e0, e10_ = _DAILY.get('eo', (np.nan, np.nan))
        dv = E.gap_div(first_open(b, day), first_open(b, t_in), e0, e10_, A, eA)
    code, kS, kT, lk, md = E.mode(code, pct, dv)
    A0 = A                                                                # v1.05 holiday sell uses today's own range
    jd = next((d for d in J['days'] if d['date'] == str(day.date())), None)
    if jd and jd.get('trades') and jd.get('frozen'):                       # a trade already shown keeps its entry, stop, target and rules
        fz = jd['frozen']; code = int(fz['code']); A = float(fz['A']); kS = float(fz.get('k', E.STOP_X)); kT = float(fz.get('t', E.TGT_X)); lk = bool(fz.get('lock', False)); md = fz.get('mode', 'normal')
    t = E.trade(b[['o', 'h', 'l', 'c']], day, code, A, now=now, cost=cost, k=kS, tx=kT, lock=lk)
    if t: t['mode'] = md
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    rows = [row(t, last, cost)] if t else []
    hol = E.is_post_holiday(day); ht = None
    if hol and np.isfinite(A0):                                           # v1.05: extra half-size SELL on the day after a UK/US holiday
        ht = E.trade(b[['o', 'h', 'l', 'c']], day, -6, A0, now=now, cost=cost, k=E.HOL_STOP, tx=0.0, lock=False)
        if ht: ht['mode'] = 'holiday'
    hrows = [row(ht, last, cost)] if ht else []
    t_out = day + pd.Timedelta(minutes=E.CLOSE_MIN)
    if J.get('start') is None: J['start'] = str(day.date())
    nd = dict(date=str(day.date()), rules=RULES, label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None), trades=rows + hrows,
              final=(bool(t is None and now >= t_in + pd.Timedelta(minutes=E.ENTRY_LATE + 1)) or bool(t and t['status'] != 'open')) and not (ht and ht['status'] == 'open'),
              code=int(code), report=None if rep is None else str(pd.Timestamp(rep).date()), mode=md,
              regime=None if not np.isfinite(pct) else round(pct, 3), gap=None if not np.isfinite(dv) else round(dv, 3), code_before_gap=int(code0))
    if t: nd['frozen'] = dict(code=int(code), A=float(A), k=float(kS), t=float(kT), lock=bool(lk), mode=md)
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] + [nd], key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(x).strftime('%-I:%M %p').lower(), round(float(r.c), 5), round(float(r.o), 5), round(float(r.h), 5), round(float(r.l), 5)] for x, r in g5.iterrows()]
    side = 'BUY' if code > 0 else 'SELL' if code < 0 else None
    if rows:
        r0 = rows[0]; state = r0['side'].lower()
        st0 = r0['status']
        if st0 == 'open':
            msg = (f"PAPER {r0['side']} at {r0['price']:.5f} ({r0['time']} Dubai). Stop {r0['stop']:.5f}, target {r0['half_px']:.5f} - "
                   f"close the WHOLE trade at the target; otherwise it closes at {dubai(t_out)} Dubai.")
            if t.get('lock') and not t.get('locked'): msg += f" CALM day: when price reaches {t['lock_px']:.5f}, move the stop to {t['lock_stop']:.5f} (entry + 5 pips)."
            elif t.get('locked'): msg += f" Stop now locked at {t['stop']:.5f} (entry + 5 pips) since {dubai(t['locked_t'])} Dubai."
            if md == 'calm_gap' and np.sign(code) != np.sign(code0): msg += ' (Side switched at 10:00: GBP ran away from EUR overnight - trading the snap-back.)'
            if md == 'busy': msg += ' BUSY day: wider stop (1.25 x range) and target 1.5 x stop.'
        elif st0 == 'stopped' and t.get('locked'): msg = f"Locked stop hit at {r0['exit_time']} Dubai: {r0['pips']:+.1f} pips. Done for today."
        elif st0 == 'target': msg = f"Target hit at {r0['exit_time']} Dubai: {r0['pips']:+.1f} pips. Done for today."
        elif st0 == 'stopped': msg = f"Stop hit at {r0['exit_time']} Dubai: {r0['pips']:+.1f} pips. Done for today."
        elif st0 == 'eod': msg = f"Closed at the day end ({r0['exit_time']} Dubai): {r0['pips']:+.1f} pips."
        else: msg = f"Day ended without a {dubai(t_out)} price - closed at the last price: {r0['pips']:+.1f} pips."
    elif side is None: state, msg = 'none', 'No GBP/USD trade today: no layer is on (pound crowds, EUR/GBP stretch and euro funds all neutral).'
    elif now < t_in:
        state, msg = 'waiting', f"Today is a {side} day ({E.LAYER_NAME[abs(code)].split(' · ')[1]}). The trade opens at {dubai(t_in)} Dubai (10:00 broker)."
        if md in ('calm', 'calm_gap'): msg += ' CALM market: at 10:00 the side can switch if GBP runs away from EUR overnight; stop moves to entry + 5 pips once +0.35 x stop in profit.'
        elif md == 'busy': msg += ' BUSY market: stop 1.25 x range, target 1.5 x stop.'

    elif not np.isfinite(A): state, msg = 'none', 'No trade: fewer than 14 days of price history for the average range.'
    else: state, msg = 'none', f'No trade today: no price bar between {dubai(t_in)} and {dubai(t_in + pd.Timedelta(minutes=E.ENTRY_LATE))} Dubai.'
    if hrows:
        h0 = hrows[0]
        msg += (f" + HOLIDAY SELL (half size, day after a UK/US holiday) at {h0['price']:.5f} ({h0['time']} Dubai), stop {h0['stop']:.5f}, no target, closes {dubai(t_out)} Dubai." if h0['status'] == 'open'
                else f" + Holiday sell closed ({h0['exit_time']} Dubai): {h0['pips']:+.1f} pips (half size).")
    elif hol and now < t_in: msg += f" Day after a UK/US holiday: an extra HALF-size SELL opens at {dubai(t_in)} Dubai."
    if cnote: msg += f' ({cnote}.)'
    if not rows and hrows: state = 'sell'
    mk['GBPUSD'] = dict(base_card(A if np.isfinite(A) else None, rep, code, md, pct if np.isfinite(pct) else None, hol), state=state, mode=md, regime=None if not np.isfinite(pct) else round(pct, 3), gap=None if not np.isfinite(dv) else round(dv, 3), message=msg, price=last,
                        change=(None if last is None or first is None else round(last - first, 5)), entries=rows + hrows, spark=spark, journal=J['summary'], jdays=jdays(J),
                        feed_error=False, epic=EPIC, close_at=dubai(t_out), open_at=dubai(t_in), signal=side, layer=abs(int(code)), cftc_note=cnote,
                        report=None if rep is None else str(pd.Timestamp(rep).date()), range_pips=None if not np.isfinite(A) else round(A * 1e4, 1),
                        cftc=dict(levp=None if rep is None else round(float(C.loc[rep, 'levp']), 3), nrp=None if rep is None else round(float(C.loc[rep, 'nrp']), 3),
                                  nrcp=None if rep is None else round(float(C.loc[rep, 'nrcp']), 3),
                                  eur_levp=None if (CE is None or erep is None) else round(float(CE.loc[erep, 'levp']), 3)),
                        eurgbp_z=None if not np.isfinite(egz) else round(egz, 2))
    dumpj(old, PORTAL, indent=1)
    print(f'GBP paper: {now} broker | bars {len(b)} | code {code} report {None if rep is None else pd.Timestamp(rep).date()} | A {A * 1e4 if np.isfinite(A) else None} pips | trade {None if not t else t["status"]}')

def fail(e):
    """Keep the last good GBP/USD card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('GBPUSD') or {}
    c.update({k: v for k, v in base_card().items() if k not in ('day_note',)}); c.setdefault('day_note', base_card()['day_note'])
    c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"GBP/USD paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['GBPUSD'] = c; dumpj(old, PORTAL, indent=1)
