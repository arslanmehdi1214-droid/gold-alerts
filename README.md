# Gold signals web page (GOLD_DAYTRADE v1.9, 5-min)

Runs by itself on GitHub every 5 minutes (Mon-Fri). No Mac, no VPS, no Claude needed.
It reads gold prices, runs the same rules as the tested MT4 EA, and updates your web page:
today's status (trading / blocked / waiting), every entry with stop, target and break-even level,
open entries, and the last 15 days. It never trades. You place the trades yourself on Capital.com.

## One-time setup (about 15 minutes)
1. Capital.com: turn on 2FA, then Settings -> API integrations -> Generate key (DEMO account). Copy the KEY and the custom password you set.
   (Skip this and it uses free Yahoo gold futures prices instead - 10 minutes delayed.)
2. GitHub: create a free account -> New repository -> name it  gold-alerts  -> PUBLIC -> Create.
3. Click "uploading an existing file" -> drag in: engine.py, feeds.py, run.py, requirements.txt, sent.json, README.md -> Commit.
4. Add file -> Create new file -> name  docs/index.html  -> paste everything from docs/index.html -> Commit.
   Add file -> Create new file -> name  docs/data.json  -> paste everything from docs/data.json -> Commit.
5. Add file -> Create new file -> name exactly  .github/workflows/gold_alerts.yml  -> paste everything from WORKFLOW_gold_alerts.yml -> Commit.
6. Settings -> Secrets and variables -> Actions -> New repository secret. Add (you type them, nobody else sees them):
   CAPITAL_API_KEY, CAPITAL_IDENTIFIER (your Capital.com login email), CAPITAL_API_PASSWORD (the key's custom password)
7. Settings -> Actions -> General -> Workflow permissions -> "Read and write" -> Save.
8. Settings -> Pages -> Source: "Deploy from a branch" -> Branch: main, folder: /docs -> Save.
9. Actions tab -> enable workflows -> "gold-alerts" -> Run workflow.

Your page: https://YOUR-GITHUB-NAME.github.io/gold-alerts/  (add it to your phone's home screen).
Tap "Turn on sound alerts" and keep the page open to hear a beep when a new signal or status change comes in.

If something fails: Actions tab -> open the red run -> copy the error text and send it to Claude.
