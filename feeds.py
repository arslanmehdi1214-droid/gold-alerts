"""Price feeds. All bars returned with index = BROKER time (New York time + 7h), columns o,h,l,c."""
import os, time, datetime as dt, requests, numpy as np, pandas as pd

NY = 'America/New_York'
def utc_to_broker(ts_utc):
    return pd.DatetimeIndex(ts_utc).tz_localize('UTC').tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
def broker_now():
    return pd.Timestamp.now(tz='UTC').tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
def broker_to_dubai(t):
    return (pd.Timestamp(t) - pd.Timedelta(hours=7)).tz_localize(NY, ambiguous=False, nonexistent='shift_forward').tz_convert('Asia/Dubai').tz_localize(None)

# ---------------- Capital.com (your broker's own prices, real time) ----------------
class Capital:
    def __init__(self):
        self.base = 'https://demo-api-capital.backend-capital.com' if os.environ.get('CAPITAL_DEMO', '1') == '1' else 'https://api-capital.backend-capital.com'
        self.key = os.environ['CAPITAL_API_KEY']; self.ident = os.environ['CAPITAL_IDENTIFIER']; self.pw = os.environ['CAPITAL_API_PASSWORD']
        self.epic = os.environ.get('CAPITAL_EPIC', 'GOLD'); self.h = None
    def login(self):
        r = requests.post(self.base + '/api/v1/session', headers={'X-CAP-API-KEY': self.key, 'Content-Type': 'application/json'},
                          json={'identifier': self.ident, 'password': self.pw, 'encryptedPassword': False}, timeout=20)
        r.raise_for_status()
        self.h = {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}
    def bars(self, resolution, start_utc, end_utc, step, epic=None):
        if self.h is None: self.login()
        epic = epic or self.epic
        out = []; t0 = start_utc
        while t0 < end_utc:
            t1 = min(end_utc, t0 + step)
            r = requests.get(f'{self.base}/api/v1/prices/{epic}', headers=self.h, timeout=20,
                             params={'resolution': resolution, 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
            if r.status_code == 200:
                for p in r.json().get('prices', []):
                    out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid']))
            elif r.status_code not in (400, 404):   # 400/404 = no prices in that window (weekend)
                r.raise_for_status()
            t0 = t1; time.sleep(0.15)
        if not out: return pd.DataFrame(columns=list('ohlc'), index=pd.DatetimeIndex([]), dtype=float)
        d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c']).drop_duplicates('t')
        d.index = utc_to_broker(pd.to_datetime(d.t)); return d[['o', 'h', 'l', 'c']].astype(float).sort_index()
    def h1(self, days=200, epic=None):
        end = pd.Timestamp.utcnow().tz_localize(None); return self.bars('HOUR', end - pd.Timedelta(days=days), end, pd.Timedelta(hours=900), epic)
    def m1_today(self, day_broker):
        start = (day_broker - pd.Timedelta(hours=7)).tz_localize(NY).tz_convert('UTC').tz_localize(None)
        end = pd.Timestamp.utcnow().tz_localize(None)
        return self.bars('MINUTE', start, end, pd.Timedelta(minutes=900))

# ---------------- Yahoo Finance gold futures (no sign-up, ~10 min delayed, futures prices) ----------------
class Yahoo:
    def _get(self, sym, interval, period):
        import yfinance as yf
        d = yf.download(sym, period=period, interval=interval, progress=False, auto_adjust=False)
        if isinstance(d.columns, pd.MultiIndex): d.columns = [c[0] for c in d.columns]
        d = d.rename(columns=str.lower).rename(columns={'open': 'o', 'high': 'h', 'low': 'l', 'close': 'c'})
        d.index = pd.DatetimeIndex(d.index).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
        return d[['o', 'h', 'l', 'c']].dropna().astype(float)
    def h1(self, days=200): return self._get('GC=F', '1h', '730d')
    def m1_today(self, day_broker):
        d = self._get('GC=F', '1m', '2d'); return d[d.index >= day_broker]

def get_feed():
    if os.environ.get('CAPITAL_API_KEY'): return Capital(), 'Capital.com'
    return Yahoo(), 'Yahoo gold futures (10 min delay)'

# ---------------- US 10-year yield and S&P 500 (daily, Yahoo) ----------------
def macro_dir(sym, day):
    """Same rule as the EA's built-in lists: 5-session change, using daily closes labelled one calendar day later,
    taken strictly before the broker day. Falling yields / falling S&P = +1 (helps gold buys)."""
    import yfinance as yf
    d = yf.download(sym, period='3mo', interval='1d', progress=False, auto_adjust=False)
    s = d['Close'][sym] if isinstance(d.columns, pd.MultiIndex) else d['Close']
    s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize() + pd.Timedelta(days=1)
    prev = s.dropna()[s.dropna().index < day]
    if len(prev) < 6: return 9
    ch = prev.iloc[-1] - prev.iloc[-6]
    return 0 if ch == 0 else int(-np.sign(ch))
