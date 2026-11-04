"""Keeps one GitHub job checking the signals EVERY MINUTE (GitHub only starts scheduled jobs every ~20 minutes, often later).
Each minute: run.safe_main() (gold v2.06 + USDJPY paper + WTI paper + Nasdaq paper + GBP/USD paper, unchanged rules; Silver removed 4 Nov). Telegram alerts go out the same minute; the page data
is pushed every 10 minutes, and at once after any alert. The job hands over to the next scheduled job as soon as that one is
waiting, stops after LOOP_MINUTES, and does one pass only when the market is closed for the weekend.
Prices: one Capital.com session is shared and re-made after any feed error; the 460-day hourly history is fetched in full every
30 minutes and topped up with the last 2 days in between (same bars, far fewer requests)."""
import os, sys, time, json, subprocess, requests, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); os.chdir(HERE)
import feeds as F

# ---- one shared Capital.com session (gold and USDJPY), re-made after an error
_Capital = F.Capital
_SHARED = [None]
def _shared_capital():
    if _SHARED[0] is None: _SHARED[0] = _Capital()
    return _SHARED[0]
F.Capital = _shared_capital

# ---- hourly history cache
_H1 = {}
class _CachedH1:
    def __init__(self, f): self.f = f
    def h1(self, days=200, epic=None):
        k = (days, epic); c = _H1.get(k); t = time.time()
        if c is None or t - c[0] > 1800:
            d = self.f.h1(days=days, epic=epic); _H1[k] = (t, d); return d
        new = self.f.h1(days=2, epic=epic)
        d = c[1] if not len(new) else pd.concat([c[1][c[1].index < new.index[0]], new])
        _H1[k] = (c[0], d); return d
    def __getattr__(self, n): return getattr(self.f, n)
_get_feed = F.get_feed
def _cached_feed():
    f, src = _get_feed(); return _CachedH1(f), src
F.get_feed = _cached_feed

import run as R

MAX_MIN = float(os.environ.get('LOOP_MINUTES', '330'))
PUSH_EVERY = float(os.environ.get('PUSH_EVERY_SEC', '600'))
REPO, RUN_ID, TOKEN = os.environ.get('GITHUB_REPOSITORY'), os.environ.get('GITHUB_RUN_ID'), os.environ.get('GITHUB_TOKEN')

def git(*a): return subprocess.run(['git', *a], capture_output=True, text=True)
def push():
    # one path per add: a path that matches nothing makes git add refuse the WHOLE list (22 Oct)
    for p in ('sent.json', 'docs/*.json', 'docs/nq_min', 'docs/sp_min',   # Nasdaq / S&P minute files
              'autotrade_state.json', 'autotrade_log.json',                              # demo auto-trader memory (which demo positions are ours)
              'data/sentiment'):                                                         # Capital.com client sentiment, 1 row/market/minute (23 Oct)
        git('add', p)
    staged = git('diff', '--cached', '--quiet').returncode != 0
    if staged: git('commit', '-m', 'alerts state')
    ahead = git('rev-list', '--count', '@{u}..HEAD').stdout.strip()    # 22 Oct: a commit left over from a failed push is pushed again too
    if not staged and ahead in ('', '0'): return 'nothing new'
    r = git('push')
    if r.returncode == 0: return 'pushed'
    print('PUSH FAILED - pulling and trying once more:', r.stderr.strip()[-200:], flush=True)
    p = git('pull', '--rebase', '-X', 'theirs')
    if p.returncode != 0:
        git('rebase', '--abort'); print('PULL FAILED:', p.stderr.strip()[-200:], flush=True)
        return 'PUSH FAILED (pull failed) - kept locally, retried at the next save'
    r = git('push')
    if r.returncode == 0: return 'pushed after pull'
    print('PUSH FAILED AGAIN after pull:', r.stderr.strip()[-200:], flush=True)
    return 'PUSH FAILED - kept locally, retried at the next save'

def next_job_waiting():
    """True when a newer run of this workflow is waiting to start (then this job hands over)."""
    if not (REPO and RUN_ID and TOKEN): return False
    try:
        r = requests.get(f'https://api.github.com/repos/{REPO}/actions/workflows/gold_alerts.yml/runs', timeout=15,
                         params={'per_page': 10}, headers={'Authorization': f'Bearer {TOKEN}', 'Accept': 'application/vnd.github+json'})
        return any(str(x['id']) != str(RUN_ID) and x.get('event') == 'schedule' and x['status'] in ('queued', 'pending', 'waiting', 'requested')
                   for x in r.json().get('workflow_runs', []))
    except Exception as e:
        print('run list not read:', type(e).__name__); return False

def feed_error():
    try:
        mk = json.load(open(R.PORTAL)).get('markets', {})
        return bool((mk.get('GOLD') or {}).get('feed_error'))              # gold's own feed error only
    except Exception: return True

def main():
    start = time.time(); last_push = time.time(); n = 0
    try: import yen_run                                                    # yen_run sets its 4-minute budget once, at import:
    except Exception: yen_run = None                                       # give it a fresh budget every minute
    try: import wti_run                                                    # same for the WTI paper page
    except Exception: wti_run = None
    try: import nq_run                                                     # same for the Nasdaq paper page
    except Exception: nq_run = None
    try: import sp_run                                                     # same for the S&P paper page (22 Oct)
    except Exception: sp_run = None
    try: import gbp_run                                                    # same for the GBP/USD paper page (24 Oct)
    except Exception: gbp_run = None
    try: import autotrade                                                  # demo auto-trader: copies the desk's trades to the Capital.com DEMO account
    except Exception as e: autotrade = None; print('autotrade not loaded:', type(e).__name__, e)
    try: import sentiment                                                  # read-only client-sentiment recorder (23 Oct)
    except Exception as e: sentiment = None; print('sentiment not loaded:', type(e).__name__, e)
    while True:
        before = open(R.STATE).read() if os.path.exists(R.STATE) else ''
        if yen_run is not None and hasattr(yen_run, 'DEADLINE'): yen_run.DEADLINE = time.time() + 90
        if wti_run is not None and hasattr(wti_run, 'DEADLINE'): wti_run.DEADLINE = time.time() + 90
        if nq_run is not None and hasattr(nq_run, 'DEADLINE'): nq_run.DEADLINE = time.time() + 90
        if sp_run is not None and hasattr(sp_run, 'DEADLINE'): sp_run.DEADLINE = time.time() + 90
        if gbp_run is not None and hasattr(gbp_run, 'DEADLINE'): gbp_run.DEADLINE = time.time() + 90
        R.safe_main(); n += 1
        at_before = open('autotrade_state.json').read() if os.path.exists('autotrade_state.json') else ''
        if autotrade is not None:
            try: autotrade.run_once()
            except Exception as e: print('autotrade error:', type(e).__name__, e)
        if sentiment is not None:
            try: sm = sentiment.record(); (n % 30 == 1) and print(sm)
            except Exception as e: print('sentiment error:', type(e).__name__, e)
        at_changed = (open('autotrade_state.json').read() if os.path.exists('autotrade_state.json') else '') != at_before
        if feed_error(): _SHARED[0] = None; _H1.clear()                   # fresh session + full history next minute
        alerted = (open(R.STATE).read() if os.path.exists(R.STATE) else '') != before
        if alerted or at_changed or time.time() - last_push >= PUSH_EVERY:
            print(time.strftime('%H:%M:%S'), 'check', n, '|', push()); last_push = time.time()
        if F.broker_now().dayofweek >= 5: print('weekend - one pass only'); break
        if (time.time() - start) / 60 >= MAX_MIN: print('time limit'); break
        if next_job_waiting(): print('next job is waiting - handing over'); break
        time.sleep(max(1.0, 65 - time.time() % 60))                       # 5 s after the next minute starts
    print('final save |', push(), '| checks', n)

if __name__ == '__main__':
    main()
