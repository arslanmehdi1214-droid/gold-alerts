# Gold signals web page — GOLD_DAYTRADE v2.06

Runs by itself on GitHub every 5 minutes (Sunday evening to Friday night). No Mac, no VPS, no Claude needed.
Open the page from any phone or computer: https://arslanmehdi1214-droid.github.io/gold-alerts/

What it does every 5 minutes:
- reads gold prices from Capital.com (your broker's own prices) and replays today through the same rules as the
  tested MT4 EA v2.06 (engine206.py; checked: 99.3% of the EA's MT4 trades 2020–2026 reproduced),
- reads the day's outside values itself (US dollar index, VIX, US 10-year yield from Yahoo; Wikipedia "Gold" page views;
  gold-vs-dollar link from Capital.com EURUSD / USDJPY / GBPUSD),
- shows today's trades (entry, stop, no target, close at midnight Dubai) and keeps a LIVE JOURNAL of every signal
  (right-way-first %, days with trades, trades per weekday, result per ounce) next to the backtest numbers.
It never trades. You place the trades yourself on Capital.com.

Files: engine206.py (rules), inputs206.py (outside values), feeds.py (prices), run.py (runner, page + journal),
docs/index.html (page), docs/data.json (page data), docs/journal.json (journal), docs/inputs.json (daily values).
The old v1.9 engine (engine.py) is no longer used.

If something fails: the page says "Price feed problem" with the time and keeps the last good update; it retries every 5 minutes.
