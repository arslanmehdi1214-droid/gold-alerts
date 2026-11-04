// Signal Desk — live price relay (Cloudflare Worker, free plan)
// Reads Capital.com's own prices for the desk markets and returns ONLY prices; /news = breaking headlines; /calendar = FF week;
// /demo = the Capital.com DEMO account the auto-trader uses (balance, open positions, today's closed P/L; read-only).
// Your Capital.com keys stay here as encrypted secrets; they never reach the desk page.
//
// Secrets to add in Cloudflare (Settings > Variables and Secrets), same values as the GitHub secrets:
//   CAPITAL_API_KEY, CAPITAL_IDENTIFIER, CAPITAL_API_PASSWORD
// Plain variable:  CAPITAL_DEMO = 1  (1 = demo server, like the desk now; 0 = live server)

const EPICS = ['GOLD', 'USDJPY', 'OIL_CRUDE', 'US100', 'US500', 'GBPUSD'];
const ALLOWED = ['https://arslanmehdi1214-droid.github.io', 'null']; // 'null' = opening the page from a file on your computer
const CACHE_SECONDS = 2;          // one Capital.com call serves every viewer for 2 seconds
let session = null;               // { cst, token, at } kept while the worker stays warm
let last = null;                  // { body, at } short memory cache (the Cache API does nothing on workers.dev)

function base(env) {
  return env.CAPITAL_DEMO === '0' ? 'https://api-capital.backend-capital.com' : 'https://demo-api-capital.backend-capital.com';
}

async function login(env) {
  const r = await fetch(base(env) + '/api/v1/session', {
    method: 'POST',
    headers: { 'X-CAP-API-KEY': env.CAPITAL_API_KEY, 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier: env.CAPITAL_IDENTIFIER, password: env.CAPITAL_API_PASSWORD, encryptedPassword: false }),
  });
  if (!r.ok) throw new Error('login ' + r.status);
  session = { cst: r.headers.get('CST'), token: r.headers.get('X-SECURITY-TOKEN'), at: Date.now() };
}

async function markets(env) {
  // Capital.com sessions expire after 10 minutes without use; renew at 8.
  if (!session || Date.now() - session.at > 8 * 60 * 1000) await login(env);
  let r = await fetch(base(env) + '/api/v1/markets?epics=' + EPICS.join(','), {
    headers: { 'X-SECURITY-TOKEN': session.token, CST: session.cst },
  });
  if (r.status === 401) { await login(env); r = await fetch(base(env) + '/api/v1/markets?epics=' + EPICS.join(','), { headers: { 'X-SECURITY-TOKEN': session.token, CST: session.cst } }); }
  if (!r.ok) throw new Error('markets ' + r.status);
  session.at = Date.now();
  const j = await r.json();
  const out = {};
  for (const m of j.marketDetails || []) {
    const s = m.snapshot || {}, epic = (m.instrument || {}).epic;
    if (!epic) continue;
    out[epic] = { bid: s.bid, ask: s.offer, mid: s.bid != null && s.offer != null ? (s.bid + s.offer) / 2 : null,
                  status: s.marketStatus, time: s.updateTime || null };
  }
  return out;
}

// Forex Factory week calendar (free). Fetched at most once an hour - their feed blocks frequent requests.
let cal = null;
async function calendar(req) {
  if (!cal || Date.now() - cal.at > 60 * 60 * 1000) {
    try {
      const r = await fetch('https://nfs.faireconomy.media/ff_calendar_thisweek.json', { headers: { 'User-Agent': 'Mozilla/5.0 (signal-desk)' } });
      if (r.ok) cal = { body: await r.text(), at: Date.now() };
    } catch (e) {}
  }
  return new Response(cal ? cal.body : '[]', { headers: cors(req) });
}

// Breaking news (free, no login): the public web pages of Telegram channels that post market headlines within seconds.
// Walter Bloomberg (= @DeItaone on X, the source Forex Factory's red-folder stories quote) and FinancialJuice.
const NEWS_CH = ['WalterBloomberg', 'FinancialJuice'];
const NEWS_SECONDS = 8;           // one read serves every viewer for 8 seconds
let news = null;
function unesc(t) {
  return t.replace(/<br\s*\/?>/g, ' ').replace(/<[^>]+>/g, '').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&')
          .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&nbsp;/g, ' ')
          .replace(/&#(\d+);/g, (m, n) => String.fromCodePoint(+n)).replace(/&#x([0-9a-f]+);/gi, (m, n) => String.fromCodePoint(parseInt(n, 16))).replace(/\s+/g, ' ').trim();
}
async function readChannel(ch) {
  const r = await fetch('https://t.me/s/' + ch, { headers: { 'User-Agent': 'Mozilla/5.0 (signal-desk)' } });
  if (!r.ok) throw new Error(ch + ' ' + r.status);
  const html = await r.text(), out = [];
  const parts = html.split('data-post="').slice(1);
  for (const p of parts) {
    const id = p.slice(0, p.indexOf('"'));
    const tm = /datetime="([^"]+)"/.exec(p), tx = /tgme_widget_message_text[^>]*>([\s\S]*?)<\/div>/.exec(p);
    if (!tm || !tx) continue;
    const text = unesc(tx[1]).replace(/\(\s*@WalterBloomberg\s*\)/i, '').replace(/\|\s*FJ\s*$/i, '').trim();
    if (text) out.push({ id, ch, t: tm[1], text, url: 'https://t.me/' + id });
  }
  return out;
}
async function newsRoute(req) {
  if (!news || Date.now() - news.at > NEWS_SECONDS * 1000) {
    const got = await Promise.allSettled(NEWS_CH.map(readChannel));
    const items = got.flatMap(g => g.status === 'fulfilled' ? g.value : []);
    const errs = got.filter(g => g.status !== 'fulfilled').map(g => String(g.reason));
    items.sort((a, b) => (a.t < b.t ? 1 : -1));
    if (items.length || !news) news = { body: JSON.stringify({ at: new Date().toISOString(), items: items.slice(0, 60), errors: errs }), at: Date.now() };
  }
  return new Response(news.body, { headers: cors(req) });
}

// Demo account (20 Oct): the Capital.com DEMO account the desk's auto-trader trades on - balance, open positions, today's closed P/L.
// Read-only here (the Worker never places or changes trades). Demo server only: CAPITAL_DEMO must be "1".
const DEMO_SECONDS = 4;
let demo = null;
async function capGet(env, path) {
  if (!session || Date.now() - session.at > 8 * 60 * 1000) await login(env);
  let r = await fetch(base(env) + path, { headers: { 'X-SECURITY-TOKEN': session.token, CST: session.cst } });
  if (r.status === 401) { await login(env); r = await fetch(base(env) + path, { headers: { 'X-SECURITY-TOKEN': session.token, CST: session.cst } }); }
  if (!r.ok) throw new Error(path.split('?')[0] + ' ' + r.status);
  session.at = Date.now();
  return r.json();
}
function brokerDayStartUtc() {
  // broker day = New York time + 7 h -> it starts at 17:00 New York the evening before
  const now = new Date();
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(now).map(x => [x.type, x.value]));
  const nyAsUtc = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour, +p.minute, +p.second);
  const offset = nyAsUtc - now.getTime();                       // New York offset vs UTC (ms, negative)
  let start = Date.UTC(+p.year, +p.month - 1, +p.day, 17, 0, 0) - offset;
  if (start > now.getTime()) start -= 86400000;
  return new Date(start);
}
async function demoRoute(req, env) {
  if (env.CAPITAL_DEMO === '0') return new Response(JSON.stringify({ error: 'demo route works on the demo server only' }), { status: 400, headers: cors(req) });
  if (!demo || Date.now() - demo.at > DEMO_SECONDS * 1000) {
    try {
      const a = await capGet(env, '/api/v1/accounts');
      const acc = (a.accounts || []).find(x => x.preferred) || (a.accounts || [])[0] || {};
      const p = await capGet(env, '/api/v1/positions');
      const positions = (p.positions || []).map(x => {
        const q = x.position || {}, m = x.market || {};
        return { dealId: q.dealId, epic: m.epic, name: m.instrumentName, direction: q.direction, size: q.size, level: q.level,
                 stop: q.stopLevel ?? null, profit: q.profitLevel ?? null, upl: q.upl, currency: q.currency, opened: q.createdDateUTC,
                 bid: m.bid, offer: m.offer };
      });
      const from = brokerDayStartUtc(), iso = d => d.toISOString().slice(0, 19);
      let closed = [], realized = 0, txErr = null;
      try {
        const secs = Math.max(60, Math.floor((Date.now() - from.getTime()) / 1000));
        let t;
        try { t = await capGet(env, '/api/v1/history/transactions?type=TRADE&lastPeriod=' + secs); }
        catch (e1) { t = await capGet(env, '/api/v1/history/transactions?type=TRADE&from=' + iso(from) + '&to=' + iso(new Date(Date.now() - 1000))); }
        closed = (t.transactions || []).map(x => ({ t: x.dateUtc, name: x.instrumentName, amount: parseFloat(x.size), currency: x.currency, note: x.note, ref: x.reference }));
        realized = closed.reduce((s, x) => s + (isFinite(x.amount) ? x.amount : 0), 0);
      } catch (e) { txErr = String(e.message || e); }
      const b = acc.balance || {};
      demo = { at: Date.now(), body: JSON.stringify({ at: new Date().toISOString(), account: { id: acc.accountId, name: acc.accountName, type: acc.accountType,
        currency: acc.currency, balance: b.balance, deposit: b.deposit, upl: b.profitLoss, available: b.available },
        positions, closed_today: closed, realized_today: realized, day_start_utc: from.toISOString(), errors: txErr ? [txErr] : [] }) };
    } catch (e) {
      session = null;
      return new Response(JSON.stringify({ error: String(e.message || e) }), { status: 502, headers: cors(req) });
    }
  }
  return new Response(demo.body, { headers: cors(req) });
}

function cors(req) {
  const o = req.headers.get('Origin') || '';
  return { 'Access-Control-Allow-Origin': ALLOWED.includes(o) ? o : ALLOWED[0], 'Vary': 'Origin',
           'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
}

export default {
  async fetch(req, env, ctx) {
    if (req.method === 'OPTIONS') return new Response(null, { headers: cors(req) });
    if (new URL(req.url).pathname === '/calendar') return calendar(req);
    if (new URL(req.url).pathname === '/news') return newsRoute(req);
    if (new URL(req.url).pathname === '/demo') return demoRoute(req, env);
    if (last && Date.now() - last.at < CACHE_SECONDS * 1000) return new Response(last.body, { headers: cors(req) });
    try {
      const body = JSON.stringify({ at: new Date().toISOString(), source: 'Capital.com', prices: await markets(env) });
      last = { body, at: Date.now() };
      return new Response(body, { headers: cors(req) });
    } catch (e) {
      session = null;
      return new Response(JSON.stringify({ error: String(e.message || e) }), { status: 502, headers: cors(req) });
    }
  },
};
