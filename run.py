"""Runs every 5 minutes (GitHub Actions). Replays today's gold signals and sends NEW ones to Telegram."""
import os, sys, json, requests, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine as E, feeds as F

SIZE = float(os.environ.get('ALERT_SIZE_OZ', '0.1'))
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sent.json')

def dubai(t): return F.broker_to_dubai(t).strftime('%-I:%M %p').lower()
def send(text):
    tok, chat = os.environ.get('TELEGRAM_BOT_TOKEN'), os.environ.get('TELEGRAM_CHAT_ID')
    if not tok or not chat: print('[no Telegram keys] ' + text); return True
    r = requests.post(f'https://api.telegram.org/bot{tok}/sendMessage', data={'chat_id': chat, 'text': text}, timeout=20)
    print('telegram', r.status_code, text.splitlines()[0]); return r.status_code == 200

def fmt(e, src):
    side = 'BUY' if e['dir'] == 1 else 'SELL'
    if e['type'] == 'ENTRY':
        return (f"GOLD {side} now  (entry {e['n']} today, day grade {e['grade']})\n"
                f"Signal price {e['px']:.2f}  [{src}]\n"
                f"Stop {e['stop']:.2f}  ({abs(e['px']-e['stop']):.1f} away)\n"
                f"Target {e['target']:.2f}  ({abs(e['target']-e['px']):.1f} away)\n"
                f"Move stop to break-even once price reaches {e['be_at']:.2f}\n"
                f"Size {SIZE} oz | open gold entries now: {e.get('open_now', 1)} | {dubai(e['t'])} Dubai")
    if e['type'] == 'BREAKEVEN':
        return f"GOLD {side} entry {e['n']}: move stop to {e['px']:.2f} (break-even) | {dubai(e['t'])} Dubai"
    if e['type'] == 'STOPPED':
        return f"GOLD {side} entry {e['n']}: stop hit | {dubai(e['t'])} Dubai"
    if e['type'] == 'TARGET':
        return f"GOLD {side} entry {e['n']}: TARGET hit {e['px']:.2f} | {dubai(e['t'])} Dubai"
    if e['type'] == 'EOD':
        return f"GOLD END OF DAY: close ALL open gold trades now | {dubai(e['t'])} Dubai"
    if e['type'] == 'NOTRADE':
        return f"GOLD: today is filtered out ({e['why']}) - no trades today | {dubai(e['t'])} Dubai"
    return str(e)

PORTAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'docs', 'data.json')
OTHER_MARKETS = [   # markets still being worked on - shown on the page, no signals yet
    dict(code='SILVER', name='Silver', status='NOT LIVE', note='Works only at ECN cost (~$0.005). Capital.com spread $0.05 is too wide.'),
    dict(code='USDJPY', name='USD/JPY', status='IN TESTING', note='Passed on RoboForex ECN cost. Capital.com cost not checked yet.'),
    dict(code='DE40', name='Germany 40 (DAX)', status='IN TESTING', note='Passed on RoboForex ECN cost. Capital.com cost not checked yet.'),
    dict(code='OIL', name='Oil (WTI)', status='NO SYSTEM YET', note='Day-trading tests failed so far.'),
    dict(code='US500', name='S&P 500', status='NO SYSTEM YET', note='Day-trading tests failed so far.'),
    dict(code='US100', name='Nasdaq 100', status='NO SYSTEM YET', note='Day-trading tests failed so far.'),
]
def write_portal(now, day, ev, src, yd, sd, m1):
    os.makedirs(os.path.dirname(PORTAL), exist_ok=True)
    old = json.load(open(PORTAL)) if os.path.exists(PORTAL) else {}
    oldg = (old.get('markets') or {}).get('GOLD', {})
    L = E.LAST or {}
    ents = []
    for e in [x for x in ev if x['type'] == 'ENTRY']:
        after = sorted([x for x in ev if x.get('n') == e['n'] and x['type'] != 'ENTRY'], key=lambda z: z['t'])
        status = 'open'; be = None
        for x in after:
            if x['type'] == 'BREAKEVEN': status = 'breakeven'; be = dubai(x['t'])
            if x['type'] == 'STOPPED': status = 'stopped'
            if x['type'] == 'BE_EXIT': status = 'scratch'
            if x['type'] == 'TARGET': status = 'target'
        if status in ('open', 'breakeven') and any(x['type'] == 'EOD' for x in ev): status = 'close_now'
        ents.append(dict(n=e['n'], time=dubai(e['t']), side='BUY' if e['dir'] == 1 else 'SELL', price=round(e['px'], 2),
                         stop=round(e['stop'], 2), target=round(e['target'], 2), be_at=round(e['be_at'], 2), be_to=round(e['be_to'], 2),
                         status=status, be_time=be))
    wd = now.dayofweek
    if wd >= 5: state, msg = 'closed', 'Market closed for the weekend'
    elif ents: state, msg = ('buy' if ents[0]['side'] == 'BUY' else 'sell'), ('Only BUY today' if ents[0]['side'] == 'BUY' else 'Only SELL today') + ' — new entries come while the first trade is in profit (until about 4 pm Dubai). Close everything at the end-of-day signal.'
    elif L.get('blocked'): state, msg = 'blocked', 'No trade today — the day filter blocked the first signal' + (' (watching for a second chance)' if L.get('alt') else '')
    elif now.hour >= 15: state, msg = 'none', 'No trade today — no first signal in the morning window'
    else: state, msg = 'waiting', 'Waiting for the first signal (window closes about 4 pm Dubai)'
    hist = [h for h in oldg.get('history', []) if h['date'] != str(day.date())]
    if wd < 5:
        hist.append(dict(date=str(day.date()), label=pd.Timestamp(day).strftime('%a %d %b'), state=state, entries=len(ents),
                         stopped=sum(x['status'] == 'stopped' for x in ents), targets=sum(x['status'] == 'target' for x in ents)))
    hist = sorted(hist, key=lambda h: h['date'])[-15:]
    spark = []
    if m1 is not None and len(m1):
        c5 = m1.c.resample('5min').last().dropna()
        spark = [[dubai(t), round(float(v), 2)] for t, v in c5.items()]
    last = float(m1.c.iloc[-1]) if m1 is not None and len(m1) else None
    first = float(m1.o.iloc[0]) if m1 is not None and len(m1) else None
    gold = dict(code='GOLD', name='Gold', symbol='XAU/USD', live=True, state=state, message=msg,
                grade=(L.get('grade') if ents else '-'), price=last, change=(None if last is None or first is None else round(last - first, 2)),
                open_now=sum(x['status'] in ('open', 'breakeven', 'close_now') for x in ents), size=SIZE,
                yields=yd, spx=sd, datr=(round(L['datr'], 2) if L.get('datr') else None), entries=ents, spark=spark, history=hist[::-1],
                stats=dict(winrate='79.6%', perday='9.6', days='59%', accuracy='61.5%', source='MT4 backtest 2020–2026'))
    data = dict(updated=F.broker_to_dubai(now).strftime('%a %d %b · %-I:%M %p').replace('AM', 'am').replace('PM', 'pm'),
                source=src, markets=dict(GOLD=gold, **{m['code']: m for m in OTHER_MARKETS}))
    json.dump(data, open(PORTAL, 'w'), indent=1)

def main():
    now = F.broker_now(); day = now.normalize()
    test = '--test' in sys.argv
    if now.dayofweek >= 5 and not test:
        write_portal(now, day, [], '-', 9, 9, None); print('weekend'); return
    feed, src = F.get_feed()
    h1 = feed.h1()
    h1 = h1[h1.index + pd.Timedelta(hours=1) <= now]                 # closed H1 bars only
    m1 = feed.m1_today(day); m1 = m1[m1.index + pd.Timedelta(minutes=1) <= now]
    yd, sd = F.macro_dir('^TNX', day), F.macro_dir('^GSPC', day)
    S = E.prepare(h1)
    ev = [e for e in E.replay_day(S, day, m1, yd, sd) if e['t'] <= now]
    ev += [x for x in E.manage(ev, m1, day) if x['t'] <= now]
    eod = day + (pd.Timedelta(hours=22, minutes=50) if day.dayofweek == 4 else pd.Timedelta(hours=23))
    closed = {x['n'] for x in ev if x['type'] in ('STOPPED', 'BE_EXIT', 'TARGET')}
    shut = {x['n']: x['t'] for x in ev if x['type'] in ('STOPPED', 'BE_EXIT', 'TARGET')}
    for e in ev:
        if e['type'] == 'ENTRY':
            e['open_now'] = sum(1 for z in ev if z['type'] == 'ENTRY' and z['t'] <= e['t'] and not (z['n'] in shut and shut[z['n']] <= e['t']))
    open_n = [e['n'] for e in ev if e['type'] == 'ENTRY' and e['n'] not in closed]
    if now >= eod and open_n: ev.append(dict(type='EOD', t=eod, dir=0, n=0))
    state = json.load(open(STATE)) if os.path.exists(STATE) else {}
    sent = set(state.get(str(day.date()), []))
    if test:
        last = m1.c.iloc[-1] if len(m1) else float('nan')
        send(f"GOLD alert system TEST OK [{src}]\nLast price {last:.2f} | broker day {day.date()} | yields dir {yd}, S&P dir {sd}\n"
             f"Signals so far today: {sum(e['type']=='ENTRY' for e in ev)} | {dubai(now)} Dubai")
    for e in sorted(ev, key=lambda z: z['t']):
        if e['type'] == 'BE_EXIT': continue
        key = f"{e['type']}|{e.get('n',0)}|{pd.Timestamp(e['t']).isoformat()}"
        if key in sent: continue
        if (now - pd.Timestamp(e['t'])) > pd.Timedelta(minutes=45) and e['type'] != 'EOD':   # too old to act on
            sent.add(key); continue
        if send(fmt(e, src)): sent.add(key)
    write_portal(now, day, ev, src, yd, sd, m1)
    state = {k: v for k, v in state.items() if k >= str((day - pd.Timedelta(days=5)).date())}
    state[str(day.date())] = sorted(sent)
    json.dump(state, open(STATE, 'w'), indent=0)
    print(f'{now} broker | {src} | entries today {sum(e["type"]=="ENTRY" for e in ev)} | sent {len(sent)}')

if __name__ == '__main__':
    main()
