"""Daily outside values for GOLD_DAYTRADE v2.06 - same rules as the EA's built-in lists (checked: 0 mismatches on 66 days).
dollar 1d / 5d : Yahoo DX-Y.NYB close of the last US date before the broker day vs 1 / 5 rows earlier
VIX 5d         : Yahoo ^VIX, 5 rows        US 10y 5d : Yahoo ^TNX (yield level), 5 rows
low attention  : Wikipedia "Gold" daily views, z = (log v - 28-day median) / 28-day stdev, last date <= day - 2, yes if z < -0.973
dollar-driven  : 20-day correlation of gold open-to-open changes vs a synthetic dollar (EURUSD -0.576, USDJPY 0.136, GBPUSD -0.119)
                 taken from the broker's 00:00 hourly bar close, below -0.6 = yes (known from 1:00 broker)
List values used by the engine: +1 = 'B', -1 = 'S', 0 = flat, 9 = not known.
"""
import math, statistics, datetime as dt, requests

UA = {'User-Agent': 'GoldSignalDesk/2.06 (personal trading notes)'}
ATTN_CUT = -0.9731857921142405
W = {'EURUSD': -0.576, 'USDJPY': 0.136, 'GBPUSD': -0.119}


def yahoo_closes(sym, rng='6mo'):
    r = requests.get(f'https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(sym)}',
                     params={'range': rng, 'interval': '1d'}, headers={'User-Agent': 'Mozilla/5.0'}, timeout=25)
    r.raise_for_status(); res = r.json()['chart']['result'][0]; off = res['meta'].get('gmtoffset', 0); out = {}
    for t, c in zip(res['timestamp'], res['indicators']['quote'][0]['close']):
        if c is not None and c > 0: out[dt.datetime.utcfromtimestamp(t + off).date()] = c
    return sorted(out.items())


def move(series, G, n, levels=False):
    idx = [i for i, (d, _) in enumerate(series) if d < G]
    if not idx or idx[-1] - n < 0: return None
    a, b = series[idx[-1]][1], series[idx[-1] - n][1]
    x = (a - b) if levels else (a / b - 1.0)
    return 'rose' if x > 0 else ('fell' if x < 0 else 'flat')


def word_to_list(w, rose_is_B):
    if w is None: return 9
    if w == 'flat': return 0
    if w == 'rose': return 1 if rose_is_B else -1
    return -1 if rose_is_B else 1


def attention(G):
    end = dt.datetime.utcnow().date(); start = end - dt.timedelta(days=70)
    r = requests.get('https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/Gold/daily/'
                     f'{start:%Y%m%d}00/{end:%Y%m%d}00', headers=UA, timeout=25)
    r.raise_for_status()
    v = [(dt.datetime.strptime(i['timestamp'][:8], '%Y%m%d').date(), float(i['views'])) for i in r.json()['items']]
    q = G - dt.timedelta(days=2); idx = [i for i, (d, _) in enumerate(v) if d <= q]
    if not idx or idx[-1] < 27: return None, None
    w = [math.log(x) for _, x in v[idx[-1] - 27: idx[-1] + 1]]; sd = statistics.stdev(w)
    if sd <= 0: return None, None
    z = (w[-1] - statistics.median(w)) / sd
    return (1 if z < ATTN_CUT else 0), round(z, 3)


def daily_inputs(G):
    """G = broker date (datetime.date). Returns dict of list values + words + notes. Never raises."""
    out = dict(date=str(G), notes=[])
    try:
        dxy = yahoo_closes('DX-Y.NYB'); w1, w5 = move(dxy, G, 1), move(dxy, G, 5)
        out.update(dollar_1d=w1, dollar_5d=w5, d1=word_to_list(w1, False), d5=word_to_list(w5, False))
    except Exception as e:
        out.update(d1=9, d5=9); out['notes'].append(f'dollar not loaded ({type(e).__name__})')
    try:
        w = move(yahoo_closes('^VIX'), G, 5); out.update(vix_5d=w, vix=word_to_list(w, True))
    except Exception as e:
        out.update(vix=9); out['notes'].append(f'VIX not loaded ({type(e).__name__})')
    try:
        w = move(yahoo_closes('^TNX'), G, 5, levels=True); out.update(tnx_5d=w, tnx=word_to_list(w, False))
    except Exception as e:
        out.update(tnx=9); out['notes'].append(f'US 10y not loaded ({type(e).__name__})')
    try:
        a, z = attention(G); out.update(attn=0 if a is None else a, attn_z=z)
        if a is None: out['notes'].append('attention data too short')
    except Exception as e:
        out.update(attn=0); out['notes'].append(f'attention not loaded ({type(e).__name__})')
    return out


def dollar_regime(gold_opens, fx_at_0059):
    """gold_opens: list of (broker_date, open) oldest..today; fx_at_0059: {pair: {broker_date: close of the 00:00 hourly bar}}.
    Returns (1/0 or None, correlation)."""
    if len(gold_opens) < 21: return None, None
    days = [d for d, _ in gold_opens[-21:]]; u = []
    for d in days:
        s = 0.0
        for p, w in W.items():
            c = fx_at_0059.get(p, {}).get(d)
            if c is None or c <= 0: return None, None
            s += w * math.log(c)
        u.append(s)
    g = [math.log(o) for _, o in gold_opens[-21:]]
    a = [g[i] - g[i - 1] for i in range(1, 21)]; b = [u[i] - u[i - 1] for i in range(1, 21)]
    ma, mb = sum(a) / 20, sum(b) / 20
    va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0: return None, None
    c = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(va * vb)
    return (1 if c < -0.6 else 0), round(c, 3)
