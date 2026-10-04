"""Runs every 5 minutes (GitHub Actions). GOLD_DAYTRADE v2.06 signals: replays today's gold minute bars through the
EA's rules (engine206.py), sends NEW events (entry / stop hit / close at day end) and updates the page + the live journal.
It never trades. You place the trades yourself."""
import os, sys, json, requests, numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine206 as E, inputs206 as I, feeds as F

HERE = os.path.dirname(os.path.abspath(__file__))
SIZE = float(os.environ.get('ALERT_SIZE_OZ', '0.1'))
STATE = os.path.join(HERE, 'sent.json'); PORTAL = os.path.join(HERE, 'docs', 'data.json')
JOURNAL = os.path.join(HERE, 'docs', 'journal.json'); INPUTS = os.path.join(HERE, 'docs', 'inputs.json')
BACKTEST = dict(direction='60.3%', days='71.6%', perday='2.22', win='55.0%', pnl='$7.47', source='MT4 backtest 2020–2026 (v2.05 signals = v2.06)')

def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()
def send(text):
    tok, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not tok or not chat: print('[no Telegram keys] ' + text.replace('\n', ' | ')); return True
    r = requests.post(f'https://api.telegram.org/bot{tok}/sendMessage', data={'chat_id': chat, 'text': text}, timeout=20)
    print('telegram', r.status_code, text.splitlines()[0]); return r.status_code == 200
def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d

def daily_bars(h1, day):
    """Broker-day bars from hourly bars (index = broker time), days before `day` only."""
    d = h1[h1.index < day]
    g = d.groupby(d.index.normalize())
    return pd.DataFrame({'o': g.o.first(), 'h': g.h.max(), 'l': g.l.min(), 'c': g.c.last()})

def regime_today(feed, h1, day, now):
    """1 / 0 / None and the correlation; needs the broker's 00:00 hourly FX bars (closed at 1:00 broker)."""
    if now < day + pd.Timedelta(hours=1): return None, None
    try:
        fx = {}
        for p in I.W:
            b = feed.h1(days=45, epic=p); b = b[b.index.hour == 0]
            fx[p] = {t.date(): float(c) for t, c in zip(b.index.normalize(), b.c)}
        g = h1[h1.index <= now]; opens = g.groupby(g.index.normalize()).o.first()
        return I.dollar_regime([(t.date(), float(o)) for t, o in opens.items()], fx)
    except Exception as e:
        print('regime not computed:', type(e).__name__, e); return None, None

def fmt(e):
    side = 'BUY' if e['dir'] == 1 else 'SELL'
    if e['kind'] == 'ENTRY':
        return (f"GOLD {side} now  ({'first trade' if e['first'] else 'add, same direction'} · {e['tag']})\n"
                f"Signal price {e['px']:.2f} | stop {e['stop']:.2f} ({abs(e['px'] - e['stop']):.1f} away) | no target\n"
                f"Size {SIZE:.2f} oz | hold until the stop or the midnight close | {dubai(e['t'])} Dubai")
    if e['kind'] == 'STOP':
        return f"GOLD {side} ({e['tag']}, entered {dubai(e['t0'])}): stop hit at {e['px']:.2f} | {dubai(e['t'])} Dubai"
    if e['kind'] == 'EOD':
        return f"GOLD END OF DAY: close ALL open gold trades now | {dubai(e['t'])} Dubai"
    if e['kind'] == 'SKIP':
        return f"GOLD: first {side} signal skipped by the dollar filter ({e['tag']}) - waiting for the next one | {dubai(e['t'])} Dubai"
    return str(e)

def row(tr):
    st = tr.get('status') or 'open'
    st = {'stop hit': 'stopped', 'closed at day end': 'eod'}.get(st, st)
    return dict(time=dubai(tr['t']), side='BUY' if tr['dir'] == 1 else 'SELL', tag=tr['tag'], price=round(float(tr['px']), 2),
                stop=round(float(tr['stop']), 2), w=tr['w'], size=SIZE, status=st, first=bool(tr['first']),
                exit=None if tr.get('exit') is None else round(float(tr['exit']), 2), pnl=tr.get('pnl_oz'), rwf=tr.get('rwf'))

def main():
    now = F.broker_now(); day = now.normalize(); test = '--test' in sys.argv
    if now.dayofweek >= 5 and not test:
        old = loadj(PORTAL, {}); g = (old.get('markets') or {}).get('GOLD')
        if g: g.update(state='closed', message='Market closed for the weekend'); json.dump(old, open(PORTAL, 'w'), indent=1)
        print('weekend'); return
    feed, src = F.get_feed()
    h1 = feed.h1(days=460)
    m1 = feed.m1_today(day); m1 = m1[m1.index + pd.Timedelta(minutes=1) <= now]          # closed minute bars only
    D1 = daily_bars(h1, day)
    D = E.Daily(D1.index.values.astype('datetime64[D]'), D1.o.values, D1.h.values, D1.l.values, D1.c.values)
    hh = h1[h1.index <= now]
    Hh = E.Hourly(hh.index.values.astype('datetime64[m]'), hh.h.values, hh.l.values, hh.c.values)
    # daily outside values (cached per broker day; retried every 30 minutes if something was missing)
    cache = loadj(INPUTS, {}); key = str(day.date()); inp = cache.get(key)
    retry = inp is not None and any(inp.get(k) == 9 for k in ('d1', 'd5', 'vix', 'tnx')) and \
        (now - pd.Timestamp(inp.get('fetched', '2000-01-01'))) > pd.Timedelta(minutes=30)
    if inp is None or retry:
        inp = I.daily_inputs(day.date()); inp['fetched'] = str(now)
    if inp.get('regime') is None:
        reg, corr = regime_today(feed, h1, day, now)
        if reg is not None: inp.update(regime=reg, corr=corr)
    cache = {k: v for k, v in cache.items() if k >= str((day - pd.Timedelta(days=10)).date())}; cache[key] = inp
    json.dump(cache, open(INPUTS, 'w'), indent=1)
    dayst = np.datetime64(day.date(), 'D')
    one_am = dayst.astype('datetime64[m]') + np.timedelta64(60, 'm')
    reg = inp.get('regime')
    einp = dict(d5=inp['d5'], d1=inp['d1'], vix=inp['vix'], tnx=inp['tnx'], attn=inp.get('attn', 0),
                regime=lambda t: (reg if (reg is not None and t >= one_am) else 0))
    mm = dict(t=m1.index.values.astype('datetime64[m]'), o=m1.o.values, h=m1.h.values, l=m1.l.values, c=m1.c.values)
    trades = E.manage(E.run_day(dayst, D, Hh, mm, einp), dayst, mm, now=np.datetime64(now, 'm')) if len(m1) else []
    taken = [t for t in trades if not t.get('skipped')]; skipped = [t for t in trades if t.get('skipped')]
    friday = now.dayofweek == 4
    eod = day + (pd.Timedelta(hours=22, minutes=50) if friday else pd.Timedelta(hours=23))
    # ---- events -> Telegram (each sent once)
    ev = [dict(kind='ENTRY', t=pd.Timestamp(t['t']), **{k: t[k] for k in ('dir', 'tag', 'px', 'stop', 'w', 'first')}) for t in taken]
    ev += [dict(kind='SKIP', t=pd.Timestamp(t['t']), dir=t['dir'], tag=t['tag']) for t in skipped[:1] if not taken or pd.Timestamp(t['t']) < pd.Timestamp(taken[0]['t'])]
    ev += [dict(kind='STOP', t=pd.Timestamp(t['exit_t']), t0=pd.Timestamp(t['t']), dir=t['dir'], tag=t['tag'], px=t['exit']) for t in taken if t.get('status') == 'stop hit']
    open_n = [t for t in taken if t.get('status') == 'open']
    if now >= eod and open_n: ev.append(dict(kind='EOD', t=eod, dir=0))
    state = loadj(STATE, {}); sent = set(state.get(key, []))
    if test:
        last = float(m1.c.iloc[-1]) if len(m1) else float('nan')
        send(f"GOLD v2.06 signal system TEST OK [{src}]\nLast price {last:.2f} | broker day {day.date()} | daily range {D.atr(0):.1f}\n"
             f"Dollar 1d/5d {inp.get('dollar_1d')}/{inp.get('dollar_5d')} · VIX {inp.get('vix_5d')} · US10y {inp.get('tnx_5d')} · dollar-driven {reg} · low attention {inp.get('attn')}\n"
             f"Trades today so far: {len(taken)} | {dubai(now)} Dubai\n"
             f"CHECK: daily bars {D.n} ({str(D.t[0]) if D.n else '-'} .. {str(D.t[-1]) if D.n else '-'}) | hourly bars {len(h1)} | ADX {D.adx():.1f} | "
             f"dollar-driven corr {inp.get('corr')} | input notes {inp.get('notes')}")
    for e in sorted(ev, key=lambda z: z['t']):
        k = f"{e['kind']}|{e.get('tag', '')}|{e['t'].isoformat()}"
        if k in sent: continue
        if (now - e['t']) > pd.Timedelta(minutes=45) and e['kind'] != 'EOD': sent.add(k); continue   # too old to act on
        if send(fmt(e)): sent.add(k)
    state = {k2: v for k2, v in state.items() if k2 >= str((day - pd.Timedelta(days=5)).date())}; state[key] = sorted(sent)
    json.dump(state, open(STATE, 'w'), indent=0)
    write_pages(now, day, m1, taken, skipped, inp, reg, src, eod, D.atr(0))
    print(f'{now} broker | {src} | trades today {len(taken)} | skipped {len(skipped)} | inputs {inp}')

def write_pages(now, day, m1, taken, skipped, inp, reg, src, eod, datr):
    rows = [row(t) for t in taken]
    if now >= eod: rows = [dict(r, status='close_now') if r['status'] == 'open' else r for r in rows]
    # ---- journal (one record per broker day, replaced on every run of that day)
    J = loadj(JOURNAL, dict(start=str(day.date()), days=[]))
    days = [d for d in J['days'] if d['date'] != str(day.date())]
    if now.dayofweek < 5:
        days.append(dict(date=str(day.date()), label=day.strftime('%a %d %b'), side=(rows[0]['side'] if rows else None),
                         trades=rows, skipped=len(skipped), final=bool(now >= eod)))
    J['days'] = sorted(days, key=lambda d: d['date'])
    allt = [t for d in J['days'] for t in d['trades']]
    dec = [t['rwf'] for t in allt if t.get('rwf') is not None]
    pnl = [t['pnl'] for t in allt if t.get('pnl') is not None]
    wd = max(1, len(pd.bdate_range(J['start'], str(day.date()))))
    tdays = sum(1 for d in J['days'] if d['trades'])
    J['summary'] = dict(since=pd.Timestamp(J['start']).strftime('%d %b %Y'), trades=len(allt),
                        direction=(round(100 * sum(dec) / len(dec), 1) if dec else None), decided=len(dec),
                        days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                        avg_pnl=(round(sum(pnl) / len(pnl), 2) if pnl else None), closed=len(pnl),
                        total_pnl_01=(round(sum(p * 0.1 for p in pnl), 2) if pnl else None))
    json.dump(J, open(JOURNAL, 'w'), indent=1)
    # ---- page data
    old = loadj(PORTAL, {}); others = {k: v for k, v in (old.get('markets') or {}).items() if k != 'GOLD'}
    last_sig = now >= day + pd.Timedelta(hours=19)
    if now.dayofweek >= 5: state, msg = 'closed', 'Market closed for the weekend'
    elif rows:
        side = rows[0]['side']; state = side.lower()
        msg = (f"{side} day — any later signals today are {side} only. Hold every trade until its stop or the midnight close. No target.")
    elif skipped and not last_sig: state, msg = 'blocked', 'The first signal was skipped by the dollar filter — watching for the next one.'
    elif last_sig: state, msg = 'none', 'No trade today — no signal (new signals stop at 8 pm Dubai).'
    else: state, msg = 'waiting', 'Waiting for the first signal (signals can come until 8 pm Dubai).'
    spark = []
    if len(m1):
        c5 = m1.c.resample('5min').last().dropna(); spark = [[dubai(t), round(float(v), 2)] for t, v in c5.items()]
    last = float(m1.c.iloc[-1]) if len(m1) else None; first = float(m1.o.iloc[0]) if len(m1) else None
    hist = []
    for d in J['days'][-15:][::-1]:
        tr = d['trades']
        hist.append(dict(date=d['date'], label=d['label'], state=(d['side'] or 'none').lower() if tr else 'none', entries=len(tr),
                         stopped=sum(t['status'] == 'stopped' for t in tr), eod=sum(t['status'] in ('eod', 'close_now') for t in tr),
                         running=sum(t['status'] == 'open' for t in tr), rw=sum(1 for t in tr if t.get('rwf') == 1),
                         rd=sum(1 for t in tr if t.get('rwf') is not None),
                         pnl=(round(sum(t['pnl'] for t in tr if t.get('pnl') is not None), 2) if any(t.get('pnl') is not None for t in tr) else None)))
    gold = dict(code='GOLD', name='Gold', symbol='XAU/USD', live=True, version='v2.06', feed_error=False, state=state, message=msg, price=last,
                change=(None if last is None or first is None else round(last - first, 2)), size=SIZE, datr=round(datr, 2),
                open_now=sum(r['status'] in ('open', 'close_now') for r in rows), entries=rows, spark=spark, history=hist,
                inputs=dict(dollar_1d=inp.get('dollar_1d'), dollar_5d=inp.get('dollar_5d'), vix_5d=inp.get('vix_5d'), tnx_5d=inp.get('tnx_5d'),
                            dollar_driven=(None if reg is None else bool(reg)), corr=inp.get('corr'), low_attention=bool(inp.get('attn', 0)),
                            notes=inp.get('notes', [])),
                stats=BACKTEST, journal=J['summary'])
    data = dict(updated=F.broker_to_dubai(now).strftime('%a %d %b · %-I:%M %p').replace('AM', 'am').replace('PM', 'pm'),
                source=src, markets=dict(GOLD=gold, **others))
    json.dump(data, open(PORTAL, 'w'), indent=1)

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
                                f"({type(e).__name__}) - the page shows the last good update; it retries every 5 minutes.")
                g['feed_error'] = True
                json.dump(old, open(PORTAL, 'w'), indent=1)
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

if __name__ == '__main__':
    safe_main()
