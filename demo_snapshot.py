"""Saved copy of the Capital.com DEMO account for the dashboard (19 Nov).
Why: some internet providers (e.g. in Pakistan) block or break *.workers.dev, so the dashboard cannot reach the Cloudflare price
Worker's /demo route and the demo box / trade sizes go blank. This module writes docs/demo.json (GitHub Pages is reachable
everywhere) with the SAME shape the Worker's /demo returns; the dashboard reads it only when the live Worker does not answer.
Read-only: it only GETs the account, positions and today's closed trades on the DEMO server (autotrade.Demo is hard-wired to
the demo server) - it never places, changes or closes anything. Called from loop.py just before each page save, inside try/except,
so a failure here can never touch trading."""
import os, json, datetime as dt
from zoneinfo import ZoneInfo
import autotrade as A

OUT = os.path.join(A.HERE, 'docs', 'demo.json')

def broker_day_start_utc(now=None):
    """Broker day = New York time + 7 h -> it starts at 17:00 New York the evening before (same rule as the Worker)."""
    now = now or dt.datetime.now(dt.timezone.utc)
    ny = now.astimezone(ZoneInfo('America/New_York'))
    start = ny.replace(hour=17, minute=0, second=0, microsecond=0)
    if start > ny: start -= dt.timedelta(days=1)
    return start.astimezone(dt.timezone.utc)

def _get(api, path):
    r = api.req('GET', path); r.raise_for_status(); return r.json()

def _f(x):
    try: return float(x)
    except Exception: return None

def build(api, now=None):
    now = now or dt.datetime.now(dt.timezone.utc)
    a = _get(api, '/api/v1/accounts').get('accounts') or []
    acc = next((x for x in a if x.get('preferred')), a[0] if a else {})
    positions = []
    for x in _get(api, '/api/v1/positions').get('positions', []):
        q = x.get('position') or {}; m = x.get('market') or {}
        positions.append(dict(dealId=q.get('dealId'), epic=m.get('epic'), name=m.get('instrumentName'), direction=q.get('direction'),
                              size=q.get('size'), level=q.get('level'), stop=q.get('stopLevel'), profit=q.get('profitLevel'),
                              upl=q.get('upl'), currency=q.get('currency'), opened=q.get('createdDateUTC'),
                              bid=m.get('bid'), offer=m.get('offer')))
    start = broker_day_start_utc(now); iso = lambda d: d.strftime('%Y-%m-%dT%H:%M:%S')
    closed, realized, errors = [], 0.0, []
    try:
        secs = max(60, int((now - start).total_seconds()))
        try: t = _get(api, '/api/v1/history/transactions?type=TRADE&lastPeriod=%d' % secs)
        except Exception: t = _get(api, '/api/v1/history/transactions?type=TRADE&from=%s&to=%s' % (iso(start), iso(now - dt.timedelta(seconds=1))))
        for x in t.get('transactions', []):
            amt = _f(x.get('size'))
            closed.append(dict(t=x.get('dateUtc'), name=x.get('instrumentName'), amount=amt, currency=x.get('currency'), note=x.get('note'), ref=x.get('reference')))
            if amt is not None: realized += amt
    except Exception as e:
        errors.append(str(e)[:120])
    b = acc.get('balance') or {}
    return dict(at=now.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                account=dict(id=acc.get('accountId'), name=acc.get('accountName'), type=acc.get('accountType'), currency=acc.get('currency'),
                             balance=b.get('balance'), deposit=b.get('deposit'), upl=b.get('profitLoss'), available=b.get('available')),
                positions=positions, closed_today=closed, realized_today=realized, day_start_utc=start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                errors=errors, snapshot=True)

def write(api=None):
    if os.environ.get('CAPITAL_DEMO', '1') != '1': return 'off'              # never anything but the demo
    api = api or A.Demo()
    body = build(api)
    if not body['account'].get('id'): return 'no account read - file left as it was'   # never overwrite a good copy with an empty one
    tmp = OUT + '.tmp'
    with open(tmp, 'w') as f: json.dump(body, f, separators=(',', ':'))
    os.replace(tmp, OUT)
    return 'saved %d open, %d closed today' % (len(body['positions']), len(body['closed_today']))

if __name__ == '__main__':
    print(write())
