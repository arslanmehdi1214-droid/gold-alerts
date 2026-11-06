"""DEMO AUTO-TRADER (20 Oct 2026; 22 Oct: part = 1.0 -> one position with the take-profit; stop-to-entry uses each position's real fill; US500 added; 26 Oct: GBPUSD added; 6 Nov: BRENT added - reverses his earlier 6 Nov "signals only, EA is backtest only" instruction, per his explicit go-ahead later the same day). Copies the Signal Desk's trades onto the Capital.com DEMO account, every minute, inside loop.py.

How it works (one pass per minute, right after the desk engines ran):
  * reads docs/data.json (the desk's own trades for today, all markets)
  * NEW desk trade (status open, at most MAX_AGE_MIN old)  -> opens it on demo at market with the desk's stop.
      If the desk trade has a part-close level, it is opened as TWO positions: the "part" (desk part %) with a take-profit at the
      part-close level, and the "rest" with the same stop.
  * desk part done (half = true)                           -> part position closed (if the take-profit has not already done it)
  * desk stop changed (stop to entry, Nasdaq trail)        -> stop moved on every position of that trade
  * desk trade closed (stop / day end / day lock / reverse) -> every position of that trade closed
  * positions gone on Capital.com (their own stop/target)   -> marked closed here
  Desk trades older than MAX_AGE_MIN when first seen are NOT entered (no late entries at a worse price).

Safety: works ONLY on the demo server (CAPITAL_DEMO=1) and only when AUTOTRADE=1; touches ONLY positions it opened itself
(their deal ids are kept in autotrade_state.json); caps new positions per minute and open positions in total; any error is
logged and the desk carries on. 22 Oct fixes: risk limits from autotrade_config.json (open risk <= max_open_risk_pct of the
balance, daily_loss_pct stop, group_risk_aed for US100+US500, skip if lot rounding makes the risk > max_real_risk_x); (Silver removed
4 Nov - was grouped with GOLD)
an order is never sent twice (lost answer -> the position is found and adopted); lost state -> positions matching a desk row are
adopted; a watchdog closes everything past each market's day-end even with a feed error or when switched off. Sizes: AUTOTRADE_RISK_USD dollars lost if a FULL-size trade hits its first stop (1/3-size
trades risk one third)."""
import os, json, time, datetime as dt, requests

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, 'autotrade_state.json')
LOG_FILE = os.path.join(HERE, 'autotrade_log.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json')
DEMO_BASE = 'https://demo-api-capital.backend-capital.com'
CONFIG_FILE = os.path.join(HERE, 'autotrade_config.json')   # {"on": true, "risk_aed": 20, "max_age_min": 5, "split": true} - edit this file to switch off / resize
def _cfg():
    try:
        with open(CONFIG_FILE) as f: return json.load(f)
    except Exception: return {}
CFG = _cfg()
AED_PER_USD = 3.6725
RISK_USD = float(os.environ['AUTOTRADE_RISK_USD']) if os.environ.get('AUTOTRADE_RISK_USD') else (
    float(CFG['risk_aed']) / AED_PER_USD if 'risk_aed' in CFG else float(CFG.get('risk_usd', 100)))   # config "risk_aed" wins (AED account)
MAX_AGE_MIN = float(os.environ.get('AUTOTRADE_MAX_AGE_MIN', CFG.get('max_age_min', 5)))
SPLIT = bool(CFG.get('split', True))
MAX_NEW_PER_PASS = 8          # new positions per minute, all markets
MAX_OPEN_TOTAL = 24           # positions open at once, all markets
MARKETS = {                   # desk code -> Capital.com epic, quote currency
    'GOLD': dict(epic='GOLD', quote='USD'),
    'USDJPY': dict(epic='USDJPY', quote='JPY'),
    'OIL': dict(epic='OIL_CRUDE', quote='USD'),
    'US100': dict(epic='US100', quote='USD'),
    'US500': dict(epic='US500', quote='USD'),        # 22 Oct: S&P 500 paper (version A, no part close -> one position per leg)
    'GBPUSD': dict(epic='GBPUSD', quote='USD'),      # 26 Oct (his A): GBP/USD v1.04 - one trade a day, part 1.0 -> one position with the take-profit
    'BRENT': dict(epic='OIL_BRENT', quote='USD'),    # 6 Nov (his go-ahead): Brent v1.04 - part 1.0, no target, stop only (1.0x 20-day ADR); epic unverified, watch for feed_error
}
DUBAI = dt.timezone(dt.timedelta(hours=4))

def enabled():
    on = os.environ.get('AUTOTRADE', '1' if _cfg().get('on') else '0') == '1'      # re-read every minute: switching off works at once
    return on and os.environ.get('CAPITAL_DEMO', '1') == '1'

# ---------------------------------------------------------------- Capital.com demo client
class Demo:
    def __init__(self, session_maker=None):
        self.base = DEMO_BASE                                       # hard-wired: never the live server
        self.key = os.environ['CAPITAL_API_KEY']; self.ident = os.environ['CAPITAL_IDENTIFIER']; self.pw = os.environ['CAPITAL_API_PASSWORD']
        self.h = None; self.rules = {}; self.http = requests.Session(); self.last_order = 0.0; self.last_ref = None
    def login(self):
        try: return self._login()
        except requests.exceptions.ConnectionError:                  # dropped connection: one fresh try
            self.http.close(); self.http = requests.Session(); time.sleep(1); return self._login()
    def _login(self):
        r = self.http.post(self.base + '/api/v1/session', headers={'X-CAP-API-KEY': self.key, 'Content-Type': 'application/json'},
                           json={'identifier': self.ident, 'password': self.pw, 'encryptedPassword': False}, timeout=20)
        r.raise_for_status(); self.h = {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}
    def req(self, method, path, retry=True, **kw):
        if self.h is None: self.login()
        for attempt in (0, 1, 2):
            try: r = self.http.request(method, self.base + path, headers=self.h, timeout=20, **kw)
            except requests.exceptions.ConnectionError:              # Capital.com drops idle kept-alive connections: fresh connection, try again
                if attempt == 2 or not retry: raise                  # 22 Oct: an ORDER is never re-sent (it may have gone through)
                self.http.close(); self.http = requests.Session(); time.sleep(1); continue
            if r.status_code == 401 and attempt < 2: self.login(); continue   # 401 = not processed: safe to send again
            return r
    def positions(self):
        r = self.req('GET', '/api/v1/positions'); r.raise_for_status()
        out = {}
        for p in r.json().get('positions', []):
            q = p.get('position', {}); m = p.get('market', {})
            out[q.get('dealId')] = dict(epic=m.get('epic'), size=q.get('size'), level=q.get('level'), direction=q.get('direction'),
                                        stop=q.get('stopLevel'), profit=q.get('profitLevel'), bid=m.get('bid'), offer=m.get('offer'),
                                        created=q.get('createdDateUTC'), ref=q.get('dealReference'))
        return out
    def account(self):
        """(balance, open P/L, currency) of the preferred demo account."""
        r = self.req('GET', '/api/v1/accounts'); r.raise_for_status(); A = r.json().get('accounts') or []
        a = next((x for x in A if x.get('preferred')), A[0] if A else None)
        if not a: raise ValueError('no account')
        b = a.get('balance') or {}
        return float(b.get('balance')), float(b.get('profitLoss') or 0), a.get('currency')
    def market_rules(self, epic):
        if epic not in self.rules:
            r = self.req('GET', '/api/v1/markets/' + epic); r.raise_for_status(); j = r.json()
            dr = j.get('dealingRules', {}) or {}; ins = j.get('instrument', {}) or {}; sn = j.get('snapshot', {}) or {}
            mn = float((dr.get('minDealSize') or {}).get('value') or 0.01)
            inc = float((dr.get('minSizeIncrement') or {}).get('value') or mn)
            dp = sn.get('decimalPlacesFactor')
            self.rules[epic] = dict(min=mn, inc=inc, dp=int(dp) if dp is not None else 5, bid=sn.get('bid'), offer=sn.get('offer'),
                                    status=sn.get('marketStatus'), contract=max(1.0, _num(ins.get('contractSize'), 1.0)))
        return self.rules[epic]
    def _pace(self):                                               # opening orders: max one per 0.1 s (Capital.com limit) -> keep 0.25 s
        w = 0.25 - (time.time() - self.last_order)
        if w > 0: time.sleep(w)
        self.last_order = time.time()
    def confirm(self, ref):
        for _ in range(6):
            r = self.req('GET', '/api/v1/confirms/' + ref)
            if r.status_code == 200:
                j = r.json(); deals = j.get('affectedDeals') or []
                did = (deals[0].get('dealId') if deals else None) or j.get('dealId')
                return j.get('dealStatus'), did, j.get('level'), j.get('reason')
            time.sleep(0.4)
        return 'UNKNOWN', None, None, 'no confirm'
    def open(self, epic, direction, size, stop, profit=None):
        """Sends the order ONCE. 'UNKNOWN' = it may or may not be open (connection lost / timeout / 5xx / no confirm):
        the caller then reads the positions and adopts it - never sends it again."""
        self._pace(); body = dict(epic=epic, direction=direction, size=size, guaranteedStop=False, stopLevel=stop)
        if profit is not None: body['profitLevel'] = profit
        self.last_ref = None
        try: r = self.req('POST', '/api/v1/positions', retry=False, json=body)
        except requests.exceptions.RequestException as ex: return 'UNKNOWN', None, None, f'{type(ex).__name__} while sending'
        if r.status_code >= 500: return 'UNKNOWN', None, None, f'http {r.status_code} {r.text[:120]}'
        if r.status_code != 200: return 'REJECTED', None, None, f'http {r.status_code} {r.text[:160]}'
        self.last_ref = r.json().get('dealReference')
        try: return self.confirm(self.last_ref)
        except requests.exceptions.RequestException as ex: return 'UNKNOWN', None, None, f'{type(ex).__name__} on confirm'
    def set_stop(self, deal, stop, profit=None):
        body = dict(stopLevel=stop) if profit is None else dict(stopLevel=stop, profitLevel=profit)
        r = self.req('PUT', '/api/v1/positions/' + deal, json=body)
        return r.status_code == 200, r.text[:160]
    def close(self, deal):
        self._pace(); r = self.req('DELETE', '/api/v1/positions/' + deal)
        return r.status_code == 200, r.text[:160]

# ---------------------------------------------------------------- helpers
def _num(x, d):
    try: return float(x)
    except Exception: return d
def broker_now(now):
    """Broker clock = New York time + 7 h (naive datetime) and whether New York is on winter time."""
    from zoneinfo import ZoneInfo
    ny = now.astimezone(ZoneInfo('America/New_York'))
    return ny.replace(tzinfo=None) + dt.timedelta(hours=7), not ny.dst()
def broker_day(now):
    """Broker day = New York time + 7 h (the desk's day)."""
    return broker_now(now)[0].strftime('%Y-%m-%d')
def day_end(code, bnow, winter):
    """Day-end close of each market on the broker clock (same as the desk)."""
    fri = bnow.weekday() == 4
    hm = {'GOLD': (22, 50) if (fri or winter) else (23, 0),             # Mon-Thu 22:50 in US winter (from 2 Nov), Fri 22:50
          'USDJPY': (14, 0) if fri else (18, 0),
          'OIL': (20, 0),
          'US100': (22, 50) if fri else (23, 0),
          'US500': (22, 30),
          'GBPUSD': (23, 45),                                            # 26 Oct: GBP/USD v1.04 closes everything at 23:45 broker
          'BRENT': (21, 30)}.get(code, (23, 0))                          # 6 Nov: Brent v1.04 closes everything at 21:30 broker (his spec's own fixed exit time, no fri/winter variation)
    return bnow.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
GROUPS = ({'US100', 'US500'},)                                           # moves together: one risk cap per group (Silver dropped 4 Nov)
def group_of(code): return next((g for g in GROUPS if code in g), {code})
def utc_of(txt):
    """Capital.com 'createdDateUTC' ('2026-10-22T08:05:12.345') -> aware UTC datetime (None if missing)."""
    if not txt: return None
    try: return dt.datetime.fromisoformat(str(txt).replace('Z', '')[:26]).replace(tzinfo=dt.timezone.utc)
    except Exception: return None
SLEEP = time.sleep                                                     # tests replace it
def load(path, default):
    try:
        with open(path) as f: return json.load(f)
    except Exception: return default
def save(path, obj):
    tmp = path + '.tmp'
    with open(tmp, 'w') as f: json.dump(obj, f, indent=1, sort_keys=True)
    os.replace(tmp, path)
def now_dubai(): return dt.datetime.now(DUBAI)
def entry_time(txt, now):
    """Desk time '1:06 pm' (Dubai) -> the latest Dubai datetime at that clock time that is not in the future."""
    t = dt.datetime.strptime(txt.strip().upper(), '%I:%M %p').time()
    c = dt.datetime.combine(now.date(), t, tzinfo=DUBAI)
    return c if c <= now + dt.timedelta(minutes=1) else c - dt.timedelta(days=1)
def weight(code, e):
    s = e.get('size')
    if code == 'GOLD': return float(e.get('size_x') or 1.0)         # gold v2.15: leg size 1 / 1.5 / 2.25 (real-yield x strong-family); older rows 1
    if isinstance(s, (int, float)): return float(s)
    s = str(s).lower()
    return 1.0 if s in ('full', '1', '1.0') else (1 / 3 if s in ('third', '1/3', '⅓') else 1.0)
def key_of(code, e, day):
    return '|'.join(str(x) for x in (code, day, e.get('time'), e.get('side'), e.get('tag') or e.get('name') or e.get('sig') or ''))
def rnd_size(x, rules):
    inc = rules['inc'] or 0.01; n = int(x / inc + 1e-9) * inc
    return round(n, 6)
def rnd_px(x, rules): return None if x is None else round(float(x), max(0, min(8, rules['dp'])))

# ---------------------------------------------------------------- sizing (shared by opening and adopting)
def plan(code, cfg, e, rules):
    """What we would send for this desk row: sizes, stop, target, target risk and the REAL risk after lot rounding (AED)."""
    px = float(e['price']); stop0 = float(e.get('stop0') or e['stop']); dist = abs(px - stop0)
    if dist <= 0: return None
    usd_per_unit = (dist / px if cfg['quote'] == 'JPY' else dist) * rules['contract']
    size = RISK_USD * weight(code, e) / usd_per_unit
    part = float(e.get('part', 0.5)) if (SPLIT and e.get('half_px') is not None and not e.get('half')) else 0.0
    if part >= 0.999:                                            # 22 Oct (yen v1.04 HA 7am): whole trade closes at the target -> ONE position with the take-profit
        p_size = max(rnd_size(size, rules), rules['min']); r_size = 0.0
    else:
        p_size = rnd_size(size * part, rules) if part > 0 else 0.0
        r_size = rnd_size(size - p_size, rules)
        if p_size < rules['min'] or r_size < rules['min']:      # too small to split: one position, part handled by the stop move
            p_size = 0.0; r_size = max(rnd_size(size, rules), rules['min'])
    side = 'BUY' if e['side'] == 'BUY' else 'SELL'
    # 22 Oct: OIL sells - desk stop/target are bid prices, Capital.com triggers a sell's stop/target on the ask -> add the spread
    # 6 Nov: same fix applied to BRENT sells (same bid/ask issue, same instrument family) - own config key, same 0.04 default as OIL unless set
    sell_spread_key = {'OIL': 'oil_sell_spread', 'BRENT': 'brent_sell_spread'}.get(code)
    adj = float(e.get('spread') or CFG_NOW().get(sell_spread_key, 0.04)) if (sell_spread_key and side == 'SELL') else 0.0
    stop = rnd_px(float(e['stop']) + adj, rules)
    tp = None if e.get('half_px') is None else rnd_px(float(e['half_px']) + adj, rules)
    target_aed = RISK_USD * weight(code, e) * AED_PER_USD
    real_aed = round((p_size + r_size) * usd_per_unit * AED_PER_USD, 2)      # what the first stop really costs after lot rounding / minimum size
    return dict(px=px, part=part, p_size=p_size, r_size=r_size, side=side, stop=stop, tp=tp if p_size > 0 else None, adj=adj,
                usd_per_unit=usd_per_unit, target_aed=round(target_aed, 2), real_aed=real_aed)
def CFG_NOW(): return _cfg() or CFG

# ---------------------------------------------------------------- one pass
_API = [None]
def run_once(api=None, portal=PORTAL, now=None):
    if os.environ.get('CAPITAL_DEMO', '1') != '1': return 'off'          # never anything but the demo
    on = enabled()
    st = load(STATE_FILE, {'trades': {}}); st.setdefault('trades', {}); log = load(LOG_FILE, [])
    T = st['trades']
    has_open = any(tr.get('state') == 'open' for tr in T.values())
    if not on and not has_open: return 'off'                           # 22 Oct: switched off = no NEW trades; open ones are still managed / closed
    C = CFG_NOW()
    MAX_RISK_PCT = float(C.get('max_open_risk_pct', 15)); DAY_LOSS_PCT = float(C.get('daily_loss_pct', 5))
    GROUP_AED = float(C.get('group_risk_aed', 150)); REAL_X = float(C.get('max_real_risk_x', 1.3)); GONE_MIN = int(C.get('gone_minutes', 10))
    now = now or now_dubai(); stamp = now.strftime('%a %d %b %I:%M %p').replace(' 0', ' ')
    def note(market, what, detail, ok=True):
        log.append(dict(t=stamp, market=market, action=what, detail=detail, ok=ok)); print('AUTOTRADE', market, what, detail, 'ok' if ok else 'FAILED')
    def skip(code, k, why):
        T[k] = dict(market=code, state='not entered', why=why, at=stamp); note(code, 'skip', f'{k}: {why}', False)
    def open_ids(): return {d['id'] for tr in T.values() for r in ('part', 'rest') for d in [tr.get(r)] if d and d.get('open')}
    def all_ids(): return {d['id'] for tr in T.values() for r in ('part', 'rest') for d in [tr.get(r)] if d and d.get('id')}
    try:
        D = load(portal, {}); mk = D.get('markets', {})
        if api is None:
            if _API[0] is None: _API[0] = Demo()
            api = _API[0]
        live = api.positions()                                     # what is really open on the demo account
        today = broker_day(now); bnow, winter = broker_now(now)
        epics = {c['epic']: code for code, c in MARKETS.items()}
        # 0) account balance (risk caps) and the day's start (daily loss stop)
        try:
            bal, upl, cur = api.account(); st['balance'] = bal; st['balance_ccy'] = cur; equity = bal + upl
        except Exception as ex:
            bal = float(st.get('balance') or C.get('balance_fallback_aed', 1100)); equity = bal
            note('ALL', 'account not read - using last known balance', f'{bal} ({type(ex).__name__})', False)
        if (st.get('day') or {}).get('date') != today:
            st['day'] = dict(date=today, start_balance=bal, start_equity=equity, stopped=False)
        day = st['day']; day_pl = round(equity - float(day['start_equity']), 2); day['pl'] = day_pl
        if not day.get('stopped') and day_pl <= -DAY_LOSS_PCT / 100 * float(day['start_balance']):
            day['stopped'] = True; note('ALL', 'DAILY LOSS STOP', f'day P/L {day_pl} AED <= -{DAY_LOSS_PCT}% of {day["start_balance"]} - no new trades until the next broker day', False)
        # 1) positions that disappeared (their own stop / take-profit on Capital.com)
        for k, tr in T.items():
            for role in ('part', 'rest'):
                d = tr.get(role)
                if d and d.get('open') and d['id'] not in live:
                    d['open'] = False; d['closed_by'] = 'Capital.com stop/target'; note(tr['market'], f'{role} closed on demo', k)
            if tr.get('state') == 'open' and not any((tr.get(r) or {}).get('open') for r in ('part', 'rest')) and any(tr.get(r) for r in ('part', 'rest')):
                tr['state'] = 'closed'
        # 1b) ADOPT: an untracked demo position that matches an open desk row (state lost / order answer lost) becomes ours again
        if on:
            mine = all_ids()
            for did, p in live.items():
                code = epics.get(p.get('epic'))
                if code is None or did in mine: continue
                cr = utc_of(p.get('created')); m = mk.get(code) or {}
                if cr is None or not isinstance(m.get('entries'), list): continue
                rules = None
                for e in m['entries']:
                    if e.get('status') != 'open' or ('BUY' if e.get('side') == 'BUY' else 'SELL') != p.get('direction'): continue
                    k = key_of(code, e, today); tr = T.get(k)
                    slot_free = tr is not None and tr.get('state') == 'open' and not all(tr.get(r) for r in ('part', 'rest'))
                    if not (tr is None or tr.get('adoptable') or slot_free): continue
                    try: et = entry_time(e['time'], now)
                    except Exception: continue
                    if abs((cr - et).total_seconds()) > 600: continue
                    rules = rules or api.market_rules(MARKETS[code]['epic']); pl = plan(code, MARKETS[code], e, rules)
                    if pl is None: continue
                    sz = float(p.get('size') or 0)
                    if not any(c > 0 and abs(sz - c) <= 0.2 * c for c in (pl['p_size'], pl['r_size'], pl['p_size'] + pl['r_size'])): continue
                    if tr is None or tr.get('state') != 'open':
                        tr = T[k] = dict(market=code, state='open', side=pl['side'], stop=float(e['stop']), desk_price=pl['px'], opened_at=stamp,
                                         risk_usd=round(RISK_USD * weight(code, e), 2), risk_aed=pl['real_aed'], px_adj=pl['adj'], part_x=pl['part'], adopted=True)
                    role = 'part' if (p.get('profit') is not None and pl['p_size'] > 0) else 'rest'
                    if tr.get(role): role = 'rest' if role == 'part' else 'part'
                    if tr.get(role): continue
                    tr[role] = dict(id=did, size=sz, level=p.get('level'), tp=p.get('profit'), open=True, adopted=True); mine.add(did)
                    note(code, f'ADOPTED {role}', f'{k}: untracked {p.get("direction")} {sz} at {p.get("level")} matches the desk row')
                    break
        # 1c) untracked positions that match nothing: left alone, logged once an hour
        seen_u = st.setdefault('untracked_seen', {}); mine = open_ids()
        for did in list(seen_u):
            if did not in live: seen_u.pop(did)
        for did, p in live.items():
            if p.get('epic') in epics and did not in mine:
                last = seen_u.get(did)
                if last is None or (now - dt.datetime.fromisoformat(last)).total_seconds() >= 3600:
                    seen_u[did] = now.isoformat(); note('ALL', 'untracked position on demo (not ours / merged?) - left alone', f"{did} {p.get('epic')} {p.get('direction')} {p.get('size')}", False)
        closes, opens, moves = [], [], []
        seen = set(); counted = set(); open_keys = set()
        for code, cfg in MARKETS.items():
            m = mk.get(code) or {}
            if m.get('feed_error') in (False, 'False') and isinstance(m.get('entries'), list): counted.add(code)   # minutes that count for "desk row gone"
            if m.get('feed_error') in (True, 'True'): continue        # desk not sure of its prices: change nothing this minute
            for e in m.get('entries') or []:
                k = key_of(code, e, today); seen.add(k); tr = T.get(k); status = e.get('status')
                if tr is None:
                    if k in open_keys: continue                        # 22 Oct: same key twice in one pass -> open once
                    age = (now - entry_time(e['time'], now)).total_seconds() / 60
                    if status == 'open' and age <= MAX_AGE_MIN:
                        if on: opens.append((code, cfg, e, k)); open_keys.add(k)
                    else: T[k] = dict(market=code, state='not entered', why=f'desk trade seen {age:.0f} min after entry, status {status}', at=stamp)
                    continue
                if tr.get('state') != 'open': continue
                if status != 'open':                                   # desk closed it (stop, day end, day lock, reverse, close_now)
                    closes.append((k, tr, f'desk: {status}'))
                    continue
                if e.get('half') and tr.get('part') and tr['part'].get('open'):
                    closes.append((k, dict(tr, rest=None), 'desk: part close'))
                want = e.get('stop')
                if want is not None:   # 21 Oct: ignore tiny desk stop wobbles (yen stop flipped 0.6 pip every minute as the entry-bar spread was re-read)
                    cur = float(tr.get('stop', want)); rd = abs(float(e.get('price') or want) - float(e.get('stop0') or want))
                    be = abs(float(want) - float(e.get('entry') if e.get('entry') is not None else (e.get('price') or want))) <= 0.02 * max(rd, 1e-9)
                    if abs(float(want) - cur) > max(1e-9, 0.05 * rd): moves.append((k, tr, float(want), be))
        # WATCHDOG (runs even with a feed error or when switched off): past the market's day-end (+2 min) or from an earlier broker day -> close
        # ... and desk row vanished for GONE_MIN counted minutes in a row (the desk re-drew its day) -> close
        for k, tr in T.items():
            if tr.get('state') != 'open': continue
            if k.split('|')[1] < today: closes.append((k, tr, 'left over from an earlier day')); continue
            end = day_end(tr['market'], bnow, winter)
            if bnow >= end + dt.timedelta(minutes=2): closes.append((k, tr, f'watchdog: past day-end {end:%I:%M %p} broker')); continue
            if k in seen:
                if tr.get('missing'): tr['missing'] = 0
                continue
            if tr['market'] in counted:
                tr['missing'] = tr.get('missing', 0) + 1
                if tr['missing'] >= GONE_MIN: closes.append((k, tr, f'desk row gone {GONE_MIN} minutes'))
        # 2) closes first (so a reverse never meets the old position)
        done_c = set()
        for k, tr, why in closes:
            for role in ('part', 'rest'):
                d = tr.get(role)
                if d and d.get('open') and (k, role) not in done_c:
                    ok, msg = api.close(d['id']) if d['id'] in live else (True, 'already gone')
                    if ok: T[k][role]['open'] = False; T[k][role]['closed_by'] = why; done_c.add((k, role))
                    note(tr['market'], f'close {role}', f'{k} ({why}) {"" if ok else msg}', ok)
            if not any((T[k].get(r) or {}).get('open') for r in ('part', 'rest')): T[k]['state'] = 'closed'
        # 3) stop moves
        for k, tr, want, be in moves:
            if T[k].get('state') != 'open': continue
            rules = api.market_rules(MARKETS[tr['market']]['epic']); s = rnd_px(want + float(T[k].get('px_adj') or 0), rules); ok_all = True
            for role in ('part', 'rest'):
                d = T[k].get(role)
                if d and d.get('open'):
                    s_d = rnd_px(d['level'], rules) if (be and d.get('level') is not None) else s   # 22 Oct: stop to entry = this position's REAL fill, not the desk price
                    ok, msg = api.set_stop(d['id'], s_d, d.get('tp'))
                    if not ok and s_d != s: ok, msg = api.set_stop(d['id'], s, d.get('tp')); s_d = s     # real-fill level refused: use the desk level
                    ok_all &= ok
                    if not ok: note(tr['market'], f'move stop {role} FAILED', f'{k} to {s_d}: {msg}', False)
            if ok_all: T[k]['stop'] = want; note(tr['market'], 'stop moved', f'{k} to {s}' + (' (stop to entry: each position at its own fill price)' if be else ''))
        # 4) opens (risk limits first)
        def at_risk(tr):                                       # a trade whose stop is at/beyond its entry risks nothing more
            try:
                s, p = float(tr.get('stop')), float(tr.get('desk_price'))
                if (tr.get('side') == 'BUY' and s >= p) or (tr.get('side') == 'SELL' and s <= p): return 0.0
            except Exception: pass
            return float(tr.get('risk_aed') or 0)
        def open_risk(codes=None):
            return sum(at_risk(tr) for tr in T.values() if tr.get('state') == 'open' and (codes is None or tr.get('market') in codes))
        n_open = len(open_ids())
        for code, cfg, e, k in opens[:MAX_NEW_PER_PASS]:
            if n_open >= MAX_OPEN_TOTAL: skip(code, k, 'too many open positions'); continue
            if bnow >= day_end(code, bnow, winter): skip(code, k, 'after the day-end close'); continue
            if st['day'].get('stopped'): skip(code, k, f'daily loss stop (day P/L {st["day"].get("pl")} AED)'); continue
            rules = api.market_rules(cfg['epic']); pl = plan(code, cfg, e, rules)
            if pl is None: skip(code, k, 'zero stop distance'); continue
            if pl['real_aed'] > REAL_X * pl['target_aed']:
                skip(code, k, f'real risk {pl["real_aed"]} AED after lot rounding > {REAL_X}x target {pl["target_aed"]} AED'); continue
            cap = MAX_RISK_PCT / 100 * bal; tot = open_risk() + pl['real_aed']
            if tot > cap: skip(code, k, f'open risk would be {tot:.2f} AED > {MAX_RISK_PCT}% of balance {bal:.2f} ({cap:.2f})'); continue
            g = group_of(code); gt = open_risk(g) + pl['real_aed']
            if len(g) > 1 and gt > GROUP_AED: skip(code, k, f'{"+".join(sorted(g))} open risk would be {gt:.2f} AED > {GROUP_AED:.0f}'); continue
            side, stop, tp, real_aed = pl['side'], pl['stop'], pl['tp'], pl['real_aed']
            T[k] = dict(market=code, state='open', side=side, stop=float(e['stop']), desk_price=pl['px'], opened_at=stamp,
                        risk_usd=round(RISK_USD * weight(code, e), 2), risk_aed=real_aed, px_adj=pl['adj'], part_x=pl['part'])
            unknown = False
            for role, sz, prof in (('part', pl['p_size'], tp), ('rest', pl['r_size'], None)):
                if sz <= 0: continue
                stt, did, lvl, why = api.open(cfg['epic'], side, sz, stop, prof)
                if stt != 'ACCEPTED' and stt != 'REJECTED':           # 22 Oct: answer lost -> look for it on the account, NEVER send it again
                    SLEEP(2)
                    try: after = api.positions()
                    except Exception: after = {}
                    taken = all_ids(); ref = getattr(api, 'last_ref', None)
                    def fits(p):
                        cr = utc_of(p.get('created'))
                        return (p.get('epic') == cfg['epic'] and p.get('direction') == side and abs(float(p.get('size') or 0) - sz) <= max(1e-9, rules['inc'] / 2)
                                and cr is not None and (now - cr).total_seconds() <= 180)
                    cands = [(i, p) for i, p in after.items() if i not in taken and fits(p)]
                    cands.sort(key=lambda ip: (ref is None or ip[1].get('ref') != ref, -utc_of(ip[1]['created']).timestamp()))
                    if cands:
                        did, p = cands[0]; stt = 'ACCEPTED'; lvl = p.get('level'); live[did] = p
                        note(code, f'order answer lost ({why}) - position found and ADOPTED', f'{k} {role} {did}')
                    else: unknown = True
                if stt == 'ACCEPTED' and did:
                    T[k][role] = dict(id=did, size=sz, level=lvl, tp=prof, open=True); n_open += 1
                    note(code, f'OPEN {side} {role}', f'{k} size {sz} at {lvl} stop {stop}' + (f' target {prof}' if prof else '') + f' | trade risk {real_aed} AED')
                    if role == 'part' and pl['part'] >= 0.999 and prof is not None and lvl is not None:   # 22 Oct: yen tiny target -> same distance from the REAL fill
                        new_tp = rnd_px(float(lvl) + (float(e['half_px']) - pl['px']) + pl['adj'], rules)
                        if new_tp != prof:
                            ok, msg = api.set_stop(did, stop, new_tp)
                            if ok: T[k][role]['tp'] = new_tp
                            note(code, 'target moved to fill + desk distance' if ok else 'target move FAILED', f'{k} {prof} -> {new_tp} {"" if ok else msg}', ok)
                else:
                    note(code, f'open {role} REJECTED', f'{k} size {sz} stop {stop}: {stt} {why}', False)
            if not any((T[k].get(r) or {}).get('open') for r in ('part', 'rest')):
                T[k]['state'] = 'not entered'; T[k]['why'] = 'order answer lost and no position found (adopted later if it appears)' if unknown else 'rejected by Capital.com'
                if unknown: T[k]['adoptable'] = True
        if opens:                                                   # same-direction positions must stay separate (else switch "split" off)
            after = api.positions()
            for k2, tr in T.items():
                for r in ('part', 'rest'):
                    d = tr.get(r)
                    if d and d.get('open') and d['id'] not in after: note(tr['market'], f'CHECK {r} not on account right after opening', k2, False)
        for code, cfg, e, k in opens[MAX_NEW_PER_PASS:]:
            T[k] = dict(market=code, state='not entered', why='too many new trades in one minute', at=stamp)
        # keep 4 days of state, 400 log lines
        cut = (now - dt.timedelta(days=4)).strftime('%Y-%m-%d')
        st['trades'] = {k: v for k, v in T.items() if v.get('state') == 'open' or k.split('|')[1] >= cut}
        st['risk_usd'] = RISK_USD; st['open_positions'] = len(open_ids()); st['open_risk_aed'] = round(open_risk(), 2)
        save(STATE_FILE, st); save(LOG_FILE, log[-400:])
        return 'ok' if on else 'off (managing open trades)'
    except Exception as ex:
        note('ALL', 'error', f'{type(ex).__name__}: {str(ex)[:200]}', False); _API[0] = None
        try: save(STATE_FILE, st); save(LOG_FILE, log[-400:])
        except Exception: pass
        return 'error'
