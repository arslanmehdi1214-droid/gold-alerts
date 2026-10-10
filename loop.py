"""Keeps one GitHub job checking the signals EVERY MINUTE (GitHub only starts scheduled jobs every ~20 minutes, often later).
Each minute: run.safe_main() (gold v2.06 + USDJPY paper, unchanged rules). Telegram alerts go out the same minute; the page data
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
    git('add', 'sent.json', 'docs/*.json')
    if git('diff', '--cached', '--quiet').returncode == 0: return 'nothing new'
    git('commit', '-m', 'alerts state')
    if git('push').returncode == 0: return 'pushed'
    r = git('pull', '--rebase', '-X', 'theirs')
    if r.returncode != 0: git('rebase', '--abort'); return 'pull failed: ' + r.stderr[-200:]
    return 'pushed after pull' if git('push').returncode == 0 else 'push failed'

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
    while True:
        before = open(R.STATE).read() if os.path.exists(R.STATE) else ''
        if yen_run is not None and hasattr(yen_run, 'DEADLINE'): yen_run.DEADLINE = time.time() + 90
        R.safe_main(); n += 1
        if feed_error(): _SHARED[0] = None; _H1.clear()                   # fresh session + full history next minute
        alerted = (open(R.STATE).read() if os.path.exists(R.STATE) else '') != before
        if alerted or time.time() - last_push >= PUSH_EVERY:
            print(time.strftime('%H:%M:%S'), 'check', n, '|', push()); last_push = time.time()
        if F.broker_now().dayofweek >= 5: print('weekend - one pass only'); break
        if (time.time() - start) / 60 >= MAX_MIN: print('time limit'); break
        if next_job_waiting(): print('next job is waiting - handing over'); break
        time.sleep(max(1.0, 65 - time.time() % 60))                       # 5 s after the next minute starts
    print('final save |', push(), '| checks', n)

if __name__ == '__main__':
    main()
