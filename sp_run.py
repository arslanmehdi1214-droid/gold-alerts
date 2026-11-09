"""S&P 500 (US500) PAPER signals for the page - version A (sp_engine.py; MT4-proven 22 Oct 2026, his run SP500_DAYTRADE v1.00:
2,330 trades 2020-01..2026-09, net $16,398 at $100 risk per leg, net/DD 6.23, worst day -$310). No phone alerts, no real money.
Called by run.py after the Nasdaq page, every minute. The day's Nasdaq picks come from docs/nq_picks.json (written by nq_run the same minute).
Files: docs/sp_min/YYYY-MM.npz (finished days of minute bars, broker clock, bid; if missing, the first run seeds the last 4 weeks from
Capital.com minutes, then each new day is added), docs/journal_sp.json (every paper trade), docs/data.json -> markets.US500 (the page)."""
import os, glob, json, time, requests, numpy as np, pandas as pd
import feeds as F, sp_engine as S
DEADLINE = time.time() + 240          # loop.py resets this every minute; the S&P part never holds up gold

HERE = os.path.dirname(os.path.abspath(__file__))
MIN = os.path.join(HERE, 'docs', 'sp_min'); JOUR = os.path.join(HERE, 'docs', 'journal_sp.json')
PORTAL = os.path.join(HERE, 'docs', 'data.json'); PICKS = os.path.join(HERE, 'docs', 'nq_picks.json')
STATE = os.path.join(HERE, 'docs', 'sp_state.json')                    # data-check memory (22 Oct)
PICK_LATE = pd.Timedelta(minutes=3)   # 22 Oct fix: a Nasdaq pick first seen more than 3 min after its own minute is ignored
EPIC = os.environ.get('CAPITAL_EPIC_SP', 'US500')
MIN_SPREAD = S.COST                   # the paper result never uses less than 0.8 index points per leg (as in the MT4 test)
PASS = dict(green=40.0, pf=1.15, months=3)
RULES = 'v1.23'
BACKTEST_104 = dict(direction='—', days='44.5% profit days / 87% traded', perday='1.37', win='53.4%', pf='1.32', net='+$16,896 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.04 (his run 24 Oct, spread 0.8 pt), 2020-01-01..2026-09-30, 2,416 trades (2,135 day + 281 night); '
                       'worst day -$315; net/DD 8.83; max DD $1,914')
BACKTEST_107 = dict(direction='—', days='49.87% profit days (n=1,554 days)', perday='—', win='—', pf='—', net='+$13,939.21 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.07 (his run 1 Nov, Magic 500109, spread 18, Every tick), 2019.10.12-2026.10.10, 2,362 trades; '
                       'max DD $2,377.37 (0.24%); net/DD 5.86; row18=1 (night leg Mon/Tue/Wed only), row19=1.0 (night stop mult, was 2.0), row20=true (Turn-of-Month day leg)')
BACKTEST_109 = dict(direction='—', days='—', perday='—', win='~68% of the 25 new Night V4 legs closed in profit', pf='—', net='+$14,896.29 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.08 (his run 3 Nov, Magic 500115, spread 18, Every tick), 2019.10.12-2026.10.31, 2,471 trades (+25 vs the '
                       '500114 baseline\'s 2,446); max DD $2,188.15 (0.22%, improved from 500114\'s $2,213.73); same 500114 rules (row18/19/20/23/24) PLUS '
                       'Night V4 (rows 25-27): a 3rd night trigger, no weekday restriction, on a weak last-hour close (252-day percentile of the 15:00-16:00 '
                       'NY return <= 0.30) combined with a last-hour volume spike (z-score vs its own trailing 20-day average >= 2.0) - isolating the 25 new '
                       'legs alone: net +$476.75, DD improved $25.58 vs 500114, ~68% closed in profit. WATCH ITEM: only 25 historical occurrences, 91-92% '
                       'already overlap the Night V2 VIX gate (row 21), 2022 a loss year inside the sample - treat as a refinement still proving itself, not '
                       'a settled edge; on the live page it needs ~2-4 weeks of its own Capital.com volume history before it can fire at all (see sp_run.py)')
BACKTEST_110 = dict(direction='—', days='—', perday='—', win='~72% of the 18 new Night V5 legs closed in profit', pf='—', net='+$15,298.06 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.10 (his run 3 Nov, Magic 500116, spread 18, Every tick), 2019.10.12-2026.10.31, 2,489 trades (+18 vs the '
                       '500115 baseline\'s 2,471); max DD $2,188.15 (0.22%, unchanged from 500115); same 500115 rules (row18/19/20/23/24/25-27) PLUS '
                       'Night V5 (rows 28-31): a 4th night trigger, no weekday restriction, on the US Dollar Index weakening over 5 days (252-day percentile '
                       'of the 5-day % change <= 0.20) combined with the market narrowing on both a 10-day AND a 20-day horizon (252-day percentile of the '
                       'RSP/SPY equal-weight/cap-weight ratio\'s 10-day and 20-day % change, both <= 0.20) - isolating the 18 new legs alone: net +$401.77, '
                       'DD unchanged vs 500115, ~72% closed in profit. WATCH ITEM: only 20 historical Python occurrences (18 confirmed in MT4 after '
                       'excluding nights V2/V3/V4 already took), 70% overlap the Night V2 VIX gate (vs 67.5% baseline - not VIX-in-disguise), 0 loss years '
                       'across 6 calendar years, survives a stricter trim-robustness check than any earlier leg - treat as a refinement still proving '
                       'itself, not a settled edge. Unlike Night V4, this data (Yahoo Finance DXY/RSP/SPY) is available from day one - no live warm-up '
                       'needed (see dxyrs_today() in sp_run.py).')
BACKTEST_111 = dict(direction='—', days='—', perday='—', win='~79% of the 14 new Night V6 legs closed in profit', pf='—', net='+$15,376.13 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.11 (his run 4 Nov, Magic 500117, spread 18, Every tick), 2018.01.01-2026.10.31, 2,503 trades (+14 vs the '
                       '500116 baseline\'s 2,489, all 14 long-side - V6 is BUY only); max DD $2,188.15 (0.22%, unchanged from 500116); same 500116 rules '
                       '(row18/19/20/23/24/25-27/28-31) PLUS Night V6 (rows 32-34): a 5th night trigger, no weekday restriction, on the broad '
                       'trade-weighted US Dollar index (FRED DTWEXBGS, 26-currency basket) being broadly weak (252-day percentile of its LEVEL <= 0.15) '
                       'combined with the pan-European STOXX50E index having a shock move the prior session (252-day percentile of its |daily % close '
                       'move| >= 0.85) - isolating the 14 new legs alone: net +$436.68, DD unchanged vs 500116, ~79% closed in profit (matches the Python '
                       'hardening estimate almost exactly). WATCH ITEM: only 24 historical Python occurrences (14 confirmed in MT4 after excluding nights '
                       'V2-V5 already took), long-only (no short leg tested), moderate date clustering (a 5-night cluster in Apr-May 2026) - treat as a '
                       'refinement still proving itself, not a settled edge. Like Night V5, this data (FRED DTWEXBGS + Yahoo Finance ^STOXX50E) is '
                       'available from day one - no live warm-up needed (see dtwexstoxx_today() in sp_run.py).')
BACKTEST_112 = dict(direction='—', days='—', perday='—', win='63.16% of the 78 new Night V7 legs closed in profit (48W/28L)', pf='—', net='+$16,133.31 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.12 (his run 4 Nov, Magic 500119, spread 18, Every tick), 2018.01.01-2026.10.31, 2,581 trades (+78 vs the '
                       '500117 baseline\'s 2,503, all long - V7 is BUY only); max DD $2,155.51 (0.21%, DOWN from 500117\'s $2,188.15 - the first leg where '
                       'DD actually falls, not just holds steady); same 500117 rules (row18/19/20/23/24/25-27/28-31/32-34) PLUS Night V7 (rows 35-37): a '
                       '6th night trigger, no weekday restriction, on the materials sector (XLB) being relatively weak vs SPY (252-day percentile of the '
                       'XLB/SPY ratio LEVEL <= 0.30) combined with the communications-services sector (XLC) rallying sharply vs SPY (252-day percentile '
                       'of the 10-day % change in the XLC/SPY ratio >= 0.85) - isolating the 78 new legs alone: net +$757.18, DD improved $32.64 vs 500117, '
                       '63.16% closed in profit (a touch below the Python hardening estimate of 68.8%, flagged honestly). WATCH ITEM: 93 historical Python '
                       'occurrences (biggest sample of any night trigger this project; 78 confirmed in MT4 after excluding nights V2-V6 already took, '
                       'after an initial 0-trade run traced to a stale/uncompiled .ex4 and fixed by a recompile), moderate date clustering (a 15-night May '
                       '2020 episode and a 12-night Sep 2025 episode) - treat as a refinement still proving itself, not a settled edge. Like Night V5/V6, '
                       'this data (Yahoo Finance XLB/XLC/SPY) is available from day one - no live warm-up needed (see mt_cm_today() in sp_run.py).')
BACKTEST_113 = dict(direction='—', days='—', perday='—', win='60.0% of the 40 new Night V8 legs closed in profit (24W/16L)', pf='—', net='+$16,213.81 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.13 (his run 5 Nov, Magic 500121, spread 18, Every tick), 2018.01.01-2026.10.31, 2,621 trades (+40 vs the '
                       '500119 baseline\'s 2,581, all long - V8 is BUY only); max DD $2,122.32 (0.21%, down slightly from 500119\'s $2,155.51, normal '
                       'diversification, not a leak); same 500119 rules (row18/19/20/23/24/25-27/28-31/32-34/35-37) PLUS Night V8 (rows 38-40): a 7th '
                       'night trigger, no weekday restriction, on credit markets quietly de-risking (252-day percentile of the 10-day % change in the '
                       'HYG/LQD ratio - junk bonds underperforming investment-grade - <= 0.15) combined with the industrials sector (XLI) relatively '
                       'weak vs SPY (252-day percentile of the 10-day % change in the XLI/SPY ratio <= 0.30) - isolating the 40 new legs alone: net '
                       '+$80.50, DD down slightly vs 500119, 60.0% closed in profit (8.6pp below the Python hardening estimate of 68.6%, the widest gap '
                       'of any leg, flagged honestly). WATCH ITEM (thinnest edge of any leg built so far, $2.01/trade avg): 65 historical Python '
                       'occurrences, 40 confirmed in MT4 after excluding nights V2-V7 already took, exact 40/40 date+profit reconciliation (no '
                       'lot-rounding gap) - treat as a refinement still proving itself, not a settled edge, more so than any prior leg. Like Night V5-V7, '
                       'this data (Yahoo Finance HYG/LQD/XLI/SPY) is available from day one - no live warm-up needed (see cq_in_today() in sp_run.py).')
BACKTEST_114 = dict(direction='—', days='—', perday='—', win='75.76% of the 33 new Night V9 legs closed in profit (25W/8L)', pf='—', net='+$16,872.72 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.14 (his run 5 Nov, Magic 500123, spread 18, Every tick), 2018.01.01-2026.10.31, 2,654 trades (+33 vs the '
                       '500121 baseline\'s 2,621, all long - V9 is BUY only, EXACT match to the Python prediction); max DD $2,118.92 (0.21%, slightly down '
                       'from 500121\'s $2,122.32, normal diversification, not a leak); same 500121 rules (row18/19/20/23/24/25-27/28-31/32-34/35-37/38-40) '
                       'PLUS Night V9 (rows 41-43): an 8th night trigger, no weekday restriction, on the Treasury duration curve steepening sharply '
                       '(252-day percentile of the 10-day % change in the TLT/IEF ratio >= 0.70 - long-duration Treasuries rallying harder than '
                       'intermediate, the bond market pricing in rate cuts or a growth scare) combined with the tech sector (XLK) being relatively weak '
                       'vs SPY (252-day percentile of the 10-day % change in the XLK/SPY ratio <= 0.20) - isolating the 33 new legs alone: net +$658.91, '
                       'DD down slightly vs 500121, 75.76% closed in profit (only 0.76pp off the Python hardening estimate of 75.0% - the tightest '
                       'Python-to-MT4 match of any leg built in this project). CONFIRMED-STRONG, not a thin watch item like V8: 40 historical Python '
                       'occurrences, 33 confirmed in MT4 after excluding nights V2-V8 already took, EXACT fire-count match to Python, $19.97/trade avg '
                       '(far above V8\'s thin $2.01/trade, back in line with V6/V7-grade edges). This data (Yahoo Finance TLT/IEF/XLK/SPY) is available '
                       'from day one - no live warm-up needed (see du_tk_today() in sp_run.py).')
BACKTEST_115 = dict(direction='—', days='—', perday='—', win='64.86% of the 37 new Night V10 legs closed in profit (24W/13L)', pf='—', net='+$17,433.26 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.15 (his run 5 Nov, Magic 500125, spread 18, Every tick), 2018.01.01-2026.10.31, 2,691 trades (+37 vs the '
                       '500123 baseline\'s 2,654, all long - V10 is BUY only); max DD $2,083.65 (0.21%, down again from 500123\'s $2,118.92 - the 5th '
                       'straight leg with DD flat-or-falling, look-ahead-checked and cleared each time); same 500123 rules (row18/19/20/23/24/25-27/28-31/'
                       '32-34/35-37/38-40/41-43) PLUS Night V10 (rows 44-46): a 9th night trigger, no weekday restriction, on the bank/leveraged-loan '
                       'sector weakening fast vs high-yield bonds (252-day percentile of the 10-day % change in the BKLN/HYG ratio <= 0.15 - a '
                       'duration-favoring/dovish credit backdrop) combined with CFTC leveraged-money positioning in the S&P E-mini futures already '
                       'net-long/bullish (52-week percentile of the leveraged-money net position, 3-day publication lag applied, >= 0.70) - isolating '
                       'the 37 new legs alone: net +$560.54, DD down slightly vs 500123, 64.86% closed in profit (within 0.8pp of the Python '
                       'collision-adjusted estimate of 65.7% - among the tightest Python-to-MT4 matches of any leg built in this project). '
                       'CONFIRMED-STRONG, not a thin watch item like V8: 45 historical Python occurrences, 37 confirmed in MT4 after excluding nights '
                       'V2-V9 already took (within 2 trades of the Python prediction), $15.15/trade avg (back in line with V6/V7/V9-grade edges). This '
                       'data (Yahoo Finance BKLN/HYG, free) + CFTC\'s public Socrata API (publicreporting.cftc.gov, free, no key) is available from day '
                       'one - no live warm-up needed (see bk_es_today() in sp_run.py).')
BACKTEST_116 = dict(direction='—', days='—', perday='—', win='78.0% of the 41 new Night V12 legs closed in profit (32W/9L)', pf='—', net='+$18,334.53 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.17 (his run 6 Nov, Magic 500129, spread 18, Every tick), 2018.01.01-2026.10.31, 2,732 trades (+41 vs the '
                       '500128 baseline\'s 2,691, all long - V12 is BUY only); max DD $1,908.28 (0.19%, down again from 500128\'s $2,083.65 - the biggest '
                       'single-leg DD drop of any leg yet, look-ahead-checked and cleared); same 500128 rules (row18/19/20/23/24/25-27/28-31/32-34/35-37/'
                       '38-40/41-43/44-46) PLUS Night V12 (rows 50-52): a 10th night trigger (row 47-49 "Night V11" MT4-confirmed 5 Nov but PARKED by his '
                       'call, never pushed here - V12 is built straight on top of V10), no weekday restriction, on DJIA leveraged-money futures '
                       'positioning (CFTC Traders in Financial Futures, "DJIA Consolidated") shifting bullish fast (52-week percentile of the 4-report '
                       'change in the net position, normalized by open interest, 3-day publication lag applied, >= 0.70) combined with crypto risk-off '
                       '(252-day percentile of the 10-day % change in the ETH-USD/BTC-USD ratio <= 0.20) - isolating the 41 new legs alone: net +$901.27, '
                       'DD down $175.37 vs 500128, 78.0% closed in profit (close to the 44 net-new Python estimate after the full V3-V10 collision count). '
                       'STRONGEST CONFIRMED LEG OF THE PROJECT on every measure - best win rate, best $/trade ($21.98), biggest single-leg profit added, '
                       'biggest DD improvement - his words, this beats V10\'s "best of the best." This data (CFTC\'s public Socrata API, '
                       'publicreporting.cftc.gov, free, no key) + Yahoo Finance ETH-USD/BTC-USD (free) is available from day one - no live warm-up needed '
                       '(see djia_cr_today() in sp_run.py).')
BACKTEST_117 = dict(direction='—', days='—', perday='—', win='77.27% of the 44 new Night V13 legs closed in profit (34W/10L)', pf='—', net='+$19,056.52 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.18 (his run 6 Nov, Magic 500131, spread 18, Every tick), 2018.01.01-2026.10.31, 2,776 trades (+44 vs the '
                       '500130 baseline\'s 2,732, all long - V13 is BUY only); max DD $1,877.39 (0.19%, down $30.89 vs 500130\'s $1,908.28 - essentially '
                       'flat/slightly improved, look-ahead-checked and cleared); same 500130 rules (row18/19/20/23/24/25-27/28-31/32-34/35-37/38-40/41-43/'
                       '44-46/50-52) PLUS Night V13 (rows 53-55): an 11th night trigger (row 47-49 "Night V11" MT4-confirmed 5 Nov but PARKED by his call, '
                       'never pushed here - V13 is built straight on top of V12), no weekday restriction, on MSCI Emerging-Markets equity-index futures '
                       'leveraged-money positioning (CFTC Traders in Financial Futures, 3-way-renamed MSCI EM series concatenated) already extreme-bullish/'
                       'long (52-week percentile of the net position LEVEL, 3-day publication lag applied, >= 0.85) combined with the communications-'
                       'services sector underperforming the index (252-day percentile of the 10-day % change in the XLC/SPY ratio <= 0.30) - isolating the '
                       '44 new legs alone: net +$721.99, DD down $30.89 vs 500130, 77.27% closed in profit (0.23pp off the 40 net-new Python estimate\'s '
                       '77.5% win rate - one of the tightest Python-to-MT4 matches of any leg built in this project). Highest net-new coverage fraction of '
                       'the whole project (80%), lowest outlier concentration of any strong candidate since the live desk was built. This data (CFTC\'s '
                       'public Socrata API, publicreporting.cftc.gov, free, no key) + Yahoo Finance XLC/SPY (free) is available from day one - no live '
                       'warm-up needed (see msciem_cm_today() in sp_run.py).')
BACKTEST_118 = dict(direction='—', days='—', perday='—', win='75.0% of the 32 new Night V14 legs closed in profit (24W/8L)', pf='—', net='+$19,448.58 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.20 (his run 7 Nov, Magic 500133, spread 18, Every tick), 2018.01.02-2026.10.30, 2,807 trades (+32 vs the '
                       '500132 baseline\'s 2,775, all long - V14 is BUY only); max DD $1,877.39 (0.19%, unchanged vs 500132 - flat, look-ahead-checked and '
                       'cleared - profit up with DD flat, not the up-profit-AND-down-DD leak pattern); same 500132 rules (row18/19/20/23/24/25-27/28-31/'
                       '32-34/35-37/38-40/41-43/44-46/50-52/53-55) PLUS Night V14 (rows 56-58): a 12th night trigger (row 47-49 "Night V11" MT4-confirmed '
                       '5 Nov but PARKED by his call, never pushed here - V14 is built straight on top of V13), no weekday restriction, on Brazilian Real '
                       'futures leveraged-money positioning (CFTC Traders in Financial Futures) shifting bullish fast (52-week percentile of the 4-report '
                       'SHIFT in the net position, 3-day publication lag applied, >= 0.85) combined with UST 2-Year Note futures leveraged-money '
                       'positioning (same 4-report-shift method, CFTC Feb-2022 rename concatenated) falling fast (<= 0.20) - isolating the 32 new legs '
                       'alone: net +$292.71, DD unchanged vs 500132, 75.0% closed in profit (above Python\'s 69.0% pool-level estimate). Round 71\'s best - '
                       'cleanest screen-to-pass ratio of the project, but thinner $/trade ($9.15) than V12/V13 and misses 3 of its 8 covered years '
                       '(2019/2023/2026) - a real but more caveated leg. This data (CFTC\'s public Socrata API, publicreporting.cftc.gov, free, no key, '
                       'both legs COT-only - no price-ratio fetch needed this time) is available from day one - no live warm-up needed (see '
                       'brlfx_ust2y_today() in sp_run.py).')
BACKTEST_119 = dict(direction='—', days='—', perday='—', win='58.0% of the 69 new Night V16+V18 legs closed in profit (40W/29L)', pf='—', net='+$19,809.13 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.21 (his run 8 Nov, Magic 500139, spread 18, Every tick), 2018.01.01-2026.10.31, 2,876 trades (+69 vs the '
                       '500135 baseline\'s 2,807); max DD $1,756.74 (0.17%, DOWN from 500135\'s $1,877.39 - look-ahead-checked and cleared, matches the '
                       'same benign profit-up/DD-down pattern already cleared for V7/V12/V13, not a fresh leak); same 500135 rules PLUS Night V16 (rows '
                       '62-64, UST-5yr-Note-futures leveraged-money COT 4-report-shift falling fast <= 0.15 combined with the SAME credit-de-risking '
                       'HYG/LQD feature already used by V8, <= 0.30 - Round 67\'s best, parked since) and Night V18 (rows 68-70, Micro-Bitcoin-futures '
                       'leveraged-money COT 4-report-shift <= 0.30 combined with the NG=F/CL=F ratio LEVEL >= 0.85 - Round 73\'s best); Night V17 (rows '
                       '65-67, Round 72\'s best survivor) MT4-tested separately (500137: net +$46.32 on 27 new legs, 55.6% win, DD UP to $1,984.99) and '
                       'PARKED by his call, never ported here. Isolating V16 alone (500136 vs 500135): net +$374.04, DD down to $1,756.74, 30 new legs, '
                       '63.3% win (19W/11L). Isolating V18 alone (500138 vs 500135): net +$198.74, DD unchanged $1,877.39, 39 new legs, 56.4% win '
                       '(22W/17L). Combined (V16+V18 both on, 500139): the two legs can both qualify on the same broker-night (code-order mutual '
                       'exclusion, V16 checked first) - net new trades is the full sum of the two solo tests (30+39=69, no frequency lost to overlap), '
                       'win split shifts by 1 trade vs the solo sum (a single overlap night going the other way), still 58.0% overall - a modest, real '
                       'add on top of V14, thinner edge than V9/V10/V12/V13. This data (CFTC\'s public Socrata API, publicreporting.cftc.gov, free, no '
                       'key) + Yahoo Finance HYG/LQD (already fetched for V8) + NG=F/CL=F (free) is available from day one - no live warm-up needed (see '
                       'ust5y_cq_today()/mbtc_ng_today() in sp_run.py).')
BACKTEST = dict(direction='—', days='—', perday='—', win='58.7% of the 109 new Night V19-V23 legs closed in profit (64W/45L)', pf='—', net='+$863.74 at $100 risk per leg',
                source='MT4 test SP500_DAYTRADE v1.22 (his run 8 Nov, Magic 500148 vs 500147 LIVE control, spread 18, Every tick), 2018.01.02-2026.10.30, '
                       '2,984 trades (+109 vs the 500147 live-baseline control\'s 2,875); max DD $1,636.39 (0.16%, DOWN from 500147\'s $1,756.74 - look-'
                       'ahead-checked and cleared, matches the same benign profit-up/DD-down pattern already cleared for V7/V12/V13/V16+V18, not a fresh '
                       'leak); 500147/500148 are the actual LIVE v1.19 config (V3-V10+V12-V14+V16+V18 on, V11/V15/V17 off - NOT the older v1.18 baseline '
                       'used for each leg\'s individual solo test below) PLUS all five new legs (rows 71-85): Night V19 (ultbond_cot_pct>=0.85 & msciem_'
                       'cot_pct>=0.85, Round 74), Night V20 (es_am_chg4_pct>=0.85 & cp_chg10<=0.20, Round 75), Night V21 (vixf_oth_chg4_pct>=0.85 & '
                       'chffx_cot_chg4_pct<=0.20, Round 76), Night V22 (ust2y_nr_chg4_pct<=0.15 & msciem_cot_chg4_pct<=0.20, Round 78), Night V23 '
                       '(uti2_nr_chg4_pct<=0.15 & tr_chg10<=0.20, Round 81). Individual solo tests (each vs the OLDER v1.18-confirmed 500140 baseline, '
                       'before V16/V18 were added - his "stack 5 then test together" process): V19 alone (500141): net +$108.95, DD flat $1,877.39 (0.19%), +35 legs '
                       '(weak, new-leg win 48.57% - 17W/18L, caveated 3rd touch of msciem_cot_pct, same base condition as live V13). V20 alone (500142): net +$398.02, DD down to '
                       '$1,854.63 (0.18%), +25 legs, 64.0% win (16W/9L). V21 alone (500143): net +$328.29, DD down to $1,786.43 (0.18%), +31 legs, 67.7% '
                       'win (21W/10L) - cleanest/zero-overlap pick. V22 alone (500144): net +$220.07, DD down to $1,852.20 (0.18%), +23 legs, 65.2% win '
                       '(15W/8L) - 3rd touch of msciem COT, caveated. V23 alone (500145): net +$191.72, DD ~flat at $1,870.76 (0.19%), +27 legs, 66.7% win '
                       '(18W/9L) - cleanest-hardened pick of the whole stack, zero feature reuse. Combined all-5-on against that same older v1.18 baseline '
                       '(500146): net +$1,135.58, DD down to $1,757.04 (0.17%), +129 legs, 60.5% win (78W/51L) - roughly additive with the four strong '
                       'legs\' sum, confirming no cannibalization. Reconfirmed here (500147/500148) on the TRUE live v1.19 baseline: net +$863.74, DD down '
                       'to $1,636.39 (0.16%), +109 legs, 58.7% win (64W/45L) - the number actually ported. This data (CFTC\'s public Socrata API, '
                       'publicreporting.cftc.gov, free, no key) + Yahoo Finance XLP/XTN/SPY (free) is available from day one - no live warm-up needed (see '
                       'ultbond_msciem_today()/es_am_cp_today()/vixfoth_chffx_today()/ust2ynr_msciemchg_today()/uti2nr_tr_today() in sp_run.py).')
CBOE = os.path.join(HERE, 'docs', 'cboe_sp.json')          # v1.04: the day's high-fear flag (decided once per broker day)
CBOE_URL = 'https://cdn.cboe.com/api/global/us_indices/daily_prices/{}_History.csv'
CBOE_Q = 'https://cdn.cboe.com/api/global/delayed_quotes/quotes/_{}.json'
GW = os.path.join(HERE, 'docs', 'gw_sp.json')              # v1.08: cached gold (GC=F) + WTI (CL=F) daily closes for the Night V3 combo trigger
LH_SEED = os.path.join(HERE, 'docs', 'sp_lh_seed.json')     # v1.09: static seed, last-hour % return per date from the MT4 backtest (RoboForex,
                                                             # Sep 2019 on) - committed once, never changes; no volume (see lh_today())
LH_LIVE = os.path.join(HERE, 'docs', 'sp_lh_live.json')     # v1.09: one row per finished day since Night V4 went live - return AND volume,
                                                             # both computed from the dashboard's own stored Capital.com minute history
DXYRS = os.path.join(HERE, 'docs', 'dxyrs_sp.json')         # v1.10: cached US Dollar Index + RSP/SPY daily closes for the Night V5 trigger
DTWEXSTOXX = os.path.join(HERE, 'docs', 'dtwexstoxx_sp.json')  # v1.11: cached FRED broad-dollar-index + STOXX50E daily closes for the Night V6 trigger
MTCM = os.path.join(HERE, 'docs', 'mtcm_sp.json')           # v1.12: cached materials/communications/SPY daily closes for the Night V7 trigger
CQIN = os.path.join(HERE, 'docs', 'cqin_sp.json')            # v1.13: cached HYG/LQD/XLI/SPY daily closes for the Night V8 trigger
DUTK = os.path.join(HERE, 'docs', 'dutk_sp.json')             # v1.14: cached TLT/IEF/XLK/SPY daily closes for the Night V9 trigger
BKES = os.path.join(HERE, 'docs', 'bkes_sp.json')             # v1.15: cached BKLN/HYG daily closes + CFTC COT S&P E-mini leveraged-money net position for the Night V10 trigger
MSCIEMCM = os.path.join(HERE, 'docs', 'msciemcm_sp.json')    # v1.17: cached XLC/SPY daily closes + CFTC COT MSCI-EM-futures leveraged-money net position (LEVEL) for the Night V13 trigger
BRLUST2Y = os.path.join(HERE, 'docs', 'brlust2y_sp.json')    # v1.18: cached CFTC COT Brazilian-Real + UST-2yr-Note leveraged-money net positions (both 4-report SHIFT) for the Night V14 trigger
UST5YCQ = os.path.join(HERE, 'docs', 'ust5ycq_sp.json')      # v1.19: cached CFTC COT UST-5yr-Note leveraged-money net position (4-report SHIFT) + HYG/LQD daily closes for the Night V16 trigger
UST5Y_MKT = ('5-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE', 'UST 5Y NOTE - CHICAGO BOARD OF TRADE')  # CFTC Feb-2022 rename, concatenated
MBTCNG = os.path.join(HERE, 'docs', 'mbtcng_sp.json')        # v1.19: cached CFTC COT Micro-Bitcoin leveraged-money net position (4-report SHIFT) + NG=F/CL=F daily closes for the Night V18 trigger
MBTC_MKT = 'MICRO BITCOIN - CHICAGO MERCANTILE EXCHANGE'
COT_URL = 'https://publicreporting.cftc.gov/resource/gpe5-46if.json'  # CFTC Socrata API, "Traders in Financial Futures - Futures Only", free, no key needed
COT_MKT = 'S&P 500 Consolidated - CHICAGO MERCANTILE EXCHANGE'
DJIACR = os.path.join(HERE, 'docs', 'djiacr_sp.json')         # v1.16: cached CFTC COT DJIA leveraged-money net position + ETH-USD/BTC-USD daily closes for the Night V12 trigger
DJIA_MKT = 'DJIA Consolidated - CHICAGO BOARD OF TRADE'
MSCIEM_MKT = ('MSCI EMERGING MKTS MINI INDEX - ICE FUTURES U.S.', 'MSCI EMERGING MKTS INDEX - ICE FUTURES U.S.', 'MSCI EM INDEX - ICE FUTURES U.S.')  # CFTC Feb-2022 3-way rename, concatenated
BRL_MKT = 'BRAZILIAN REAL - CHICAGO MERCANTILE EXCHANGE'
UST2Y_MKT = ('2-YEAR U.S. TREASURY NOTES - CHICAGO BOARD OF TRADE', 'UST 2Y NOTE - CHICAGO BOARD OF TRADE')  # CFTC Feb-2022 rename, concatenated
ULTBONDMSCIEM = os.path.join(HERE, 'docs', 'ultbondmsciem_sp.json')  # v1.23: cached CFTC COT Ultra-T-Bond leveraged-money net position (LEVEL) + MSCI-EM leveraged-money net position (LEVEL, independent fetch from msciem_cm_today()) for the Night V19 trigger
ULTBOND_MKT = ('ULTRA U.S. TREASURY BONDS - CHICAGO BOARD OF TRADE', 'ULTRA UST BOND - CHICAGO BOARD OF TRADE')  # CFTC Feb-2022 rename, concatenated
ESAMCP = os.path.join(HERE, 'docs', 'esamcp_sp.json')          # v1.23: cached CFTC COT S&P-E-mini ASSET-MANAGER net position (4-report SHIFT) + XLP/SPY daily closes for the Night V20 trigger
VIXFOTHCHFFX = os.path.join(HERE, 'docs', 'vixfothchffx_sp.json')  # v1.23: cached CFTC COT VIX-futures OTHER-REPORTABLES net position + Swiss-Franc leveraged-money net position (both 4-report SHIFT) for the Night V21 trigger
VIXF_MKT = 'VIX FUTURES - CBOE FUTURES EXCHANGE'
CHF_MKT = 'SWISS FRANC - CHICAGO MERCANTILE EXCHANGE'
UST2YNRMSCIEMCHG = os.path.join(HERE, 'docs', 'ust2ynrmsciemchg_sp.json')  # v1.23: cached CFTC COT UST-2yr-Note NON-REPORTABLES net position + MSCI-EM leveraged-money net position (both 4-report SHIFT) for the Night V22 trigger
UTI2NRTR = os.path.join(HERE, 'docs', 'uti2nrtr_sp.json')      # v1.23: cached CFTC COT E-mini-S&P-Utilities NON-REPORTABLES net position (4-report SHIFT) + XTN/SPY daily closes for the Night V23 trigger
UTI2_MKT = 'E-MINI S&P UTILITIES INDEX - CHICAGO MERCANTILE EXCHANGE'
DISAGG_URL = 'https://publicreporting.cftc.gov/resource/72hh-3qpy.json'  # CFTC Socrata API, "Commitments of Traders - Disaggregated Futures Only", free, no key needed (Other-Reportables/Swap-Dealer categories, absent from the Traders-in-Financial-Futures dataset used above)
LEGACY_URL = 'https://publicreporting.cftc.gov/resource/6dca-aqww.json'  # CFTC Socrata API, "Commitments of Traders - Legacy, Futures Only", free, no key needed (Commercial/Non-Commercial categories, absent from both datasets above)
SUGAR_MKT = 'SUGAR NO. 11 - ICE FUTURES U.S.'
FC_MKT = 'FEEDER CATTLE - CHICAGO MERCANTILE EXCHANGE'
DXYF_MKT = ('U.S. DOLLAR INDEX - ICE FUTURES U.S.', 'USD INDEX - ICE FUTURES U.S.')  # CFTC Feb-2022 rename, concatenated
EURJPYL_MKT = 'EURO FX/JAPANESE YEN XRATE - CHICAGO MERCANTILE EXCHANGE'
SGOTHFY = os.path.join(HERE, 'docs', 'sgothfy_sp.json')        # v1.24: cached CFTC COT Sugar-No.11 (Disaggregated, OTHER-REPORTABLES net position, LEVEL) + XLF/SPY daily closes for the Night V25 trigger
FCSWCQ = os.path.join(HERE, 'docs', 'fcswcq_sp.json')          # v1.24: cached CFTC COT Feeder-Cattle (Disaggregated, SWAP-DEALER net position, 4-report SHIFT) + HYG/LQD daily closes for the Night V26 trigger
VIXLCOMMDXYFNR = os.path.join(HERE, 'docs', 'vixlcommdxyfnr_sp.json')  # v1.24: cached CFTC COT VIX-futures (Legacy, COMMERCIAL net position) + USD-Index-futures (Legacy, NON-REPORTABLES net position), both 4-report SHIFT, for the Night V27 trigger
EURJPYNCOMMBT = os.path.join(HERE, 'docs', 'eurjpyncommbt_sp.json')  # v1.24: cached CFTC COT EUR/JPY-cross-futures (Legacy, NON-COMMERCIAL net position, 4-report SHIFT) + BTC-USD daily closes for the Night V28 trigger
FRED_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'   # free, no API key needed

def _cboe_series(sym, col):
    import io
    r = requests.get(CBOE_URL.format(sym), timeout=20); r.raise_for_status()
    x = pd.read_csv(io.StringIO(r.text)); x['DATE'] = pd.to_datetime(x.DATE, format='%m/%d/%Y')
    return x.set_index('DATE')[col if col in x.columns else x.columns[-1]].astype(float)

def _yahoo_daily_close(sym, period='2y'):
    import yfinance as yf
    d = yf.download(sym, period=period, interval='1d', progress=False, auto_adjust=False)
    if isinstance(d.columns, pd.MultiIndex): d.columns = [c[0] for c in d.columns]
    s = d['Close'].dropna().astype(float); s.index = pd.DatetimeIndex(s.index).tz_localize(None).normalize(); return s

def _fred_daily_close(series_id):
    """v1.11: FRED's public CSV endpoint (no API key, no rate-limit auth needed) - columns observation_date,<series_id>; FRED marks
    a missing business day '.' (holiday-aligned series), dropped here same as Yahoo's own gaps."""
    r = requests.get(FRED_URL.format(series_id), timeout=20); r.raise_for_status()
    import io
    x = pd.read_csv(io.StringIO(r.text))
    s = pd.to_numeric(x[series_id], errors='coerce')
    s.index = pd.DatetimeIndex(pd.to_datetime(x['observation_date'])).normalize()
    return s.dropna().astype(float)

def gw_today(day):
    """v1.08 Night V3: gold+WTI daily closes (cached in docs/gw_sp.json, refreshed once per broker day - same once-a-day shape as
    stress_today()'s Cboe cache). Returns a DataFrame indexed by date with gc_pct/cl_pct (each commodity's 252-day rolling
    percentile rank of |daily % close move|, >= 120 days warm-up) for combo_flag() in sp_engine.py, or None on a fetch failure
    (Night V3 then simply does not fire that night - same fail-safe shape as the Cboe fetch for the existing night leg)."""
    c = loadj(GW, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        gc = pd.Series([np.nan if x is None else x for x in c['gc']], index=idx)
        cl = pd.Series([np.nan if x is None else x for x in c['cl']], index=idx)
    else:
        try:
            gc = _yahoo_daily_close('GC=F'); cl = _yahoo_daily_close('CL=F')
            idx = gc.index.union(cl.index); gc = gc.reindex(idx); cl = cl.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     gc=[None if pd.isna(x) else float(x) for x in gc], cl=[None if pd.isna(x) else float(x) for x in cl], at=str(pd.Timestamp.utcnow()))
            dumpj(c, GW, indent=1)
        except Exception:
            return None
    gc_pct = gc.pct_change().abs().rolling(252, min_periods=120).rank(pct=True)
    cl_pct = cl.pct_change().abs().rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(gc_pct=gc_pct, cl_pct=cl_pct))

def dxyrs_today(day):
    """v1.10 Night V5: US Dollar Index (DX-Y.NYB) + RSP/SPY ratio daily closes (cached in docs/dxyrs_sp.json, refreshed once per
    broker day - same once-a-day shape as gw_today()). Returns a DataFrame indexed by date with dxy_chg5_pct (252-day rolling
    percentile of the 5-day % change in DXY - low = dollar weakening), rs_chg10_pct and rs_chg20_pct (252-day rolling percentile
    of the 10-day and 20-day % change in the RSP/SPY equal-weight/cap-weight ratio - low = breadth narrowing) for v5_flag() in
    sp_engine.py, or None on a fetch failure (Night V5 then simply does not fire that night - same fail-safe shape as gw_today())."""
    c = loadj(DXYRS, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        dxy = pd.Series([np.nan if x is None else x for x in c['dxy']], index=idx)
        rsp = pd.Series([np.nan if x is None else x for x in c['rsp']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
    else:
        try:
            dxy = _yahoo_daily_close('DX-Y.NYB'); rsp = _yahoo_daily_close('RSP'); spy = _yahoo_daily_close('SPY')
            idx = dxy.index.union(rsp.index).union(spy.index); dxy = dxy.reindex(idx); rsp = rsp.reindex(idx); spy = spy.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     dxy=[None if pd.isna(x) else float(x) for x in dxy], rsp=[None if pd.isna(x) else float(x) for x in rsp],
                     spy=[None if pd.isna(x) else float(x) for x in spy], at=str(pd.Timestamp.utcnow()))
            dumpj(c, DXYRS, indent=1)
        except Exception:
            return None
    dxy_chg5_pct = dxy.pct_change(5).rolling(252, min_periods=120).rank(pct=True)
    rs = rsp / spy
    rs_chg10_pct = rs.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    rs_chg20_pct = rs.pct_change(20).rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(dxy_chg5_pct=dxy_chg5_pct, rs_chg10_pct=rs_chg10_pct, rs_chg20_pct=rs_chg20_pct))

def dtwexstoxx_today(day):
    """v1.11 Night V6: FRED broad trade-weighted dollar index (DTWEXBGS) + pan-European STOXX50E daily closes (cached in
    docs/dtwexstoxx_sp.json, refreshed once per broker day - same once-a-day shape as gw_today()/dxyrs_today()). Returns a
    DataFrame indexed by date with dtwex_lvl_pct (252-day rolling percentile of the DTWEXBGS LEVEL itself - not a change, unlike
    V5's dxy_chg5_pct - low = dollar broadly weak) and stoxx_shock_pct (252-day rolling percentile of STOXX50E's |daily % close
    move| - high = a European equity shock) for v6_flag() in sp_engine.py, or None on a fetch failure (Night V6 then simply does
    not fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(DTWEXSTOXX, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        dtwex = pd.Series([np.nan if x is None else x for x in c['dtwex']], index=idx)
        stoxx = pd.Series([np.nan if x is None else x for x in c['stoxx']], index=idx)
    else:
        try:
            dtwex = _fred_daily_close('DTWEXBGS'); stoxx = _yahoo_daily_close('^STOXX50E')
            idx = dtwex.index.union(stoxx.index); dtwex = dtwex.reindex(idx); stoxx = stoxx.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     dtwex=[None if pd.isna(x) else float(x) for x in dtwex], stoxx=[None if pd.isna(x) else float(x) for x in stoxx],
                     at=str(pd.Timestamp.utcnow()))
            dumpj(c, DTWEXSTOXX, indent=1)
        except Exception:
            return None
    dtwex_lvl_pct = dtwex.rolling(252, min_periods=120).rank(pct=True)
    stoxx_shock_pct = stoxx.pct_change().abs().rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(dtwex_lvl_pct=dtwex_lvl_pct, stoxx_shock_pct=stoxx_shock_pct))

def mt_cm_today(day):
    """v1.12 Night V7: materials (XLB) + communications services (XLC) + SPY daily closes (cached in docs/mtcm_sp.json,
    refreshed once per broker day - same once-a-day shape as dxyrs_today()/dtwexstoxx_today()). Returns a DataFrame
    indexed by date with mt_lvl_pct (252-day rolling percentile of the XLB/SPY ratio LEVEL itself - not a change, same
    framing as V6's dtwex_lvl_pct - low = materials/cyclicals relatively weak) and cm_chg10_pct (252-day rolling
    percentile of the 10-day % change in the XLC/SPY ratio - high = communications services rallying sharply vs the
    index) for v7_flag() in sp_engine.py, or None on a fetch failure (Night V7 then simply does not fire that night -
    same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(MTCM, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        xlb = pd.Series([np.nan if x is None else x for x in c['xlb']], index=idx)
        xlc = pd.Series([np.nan if x is None else x for x in c['xlc']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
    else:
        try:
            xlb = _yahoo_daily_close('XLB'); xlc = _yahoo_daily_close('XLC'); spy = _yahoo_daily_close('SPY')
            idx = xlb.index.union(xlc.index).union(spy.index); xlb = xlb.reindex(idx); xlc = xlc.reindex(idx); spy = spy.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     xlb=[None if pd.isna(x) else float(x) for x in xlb], xlc=[None if pd.isna(x) else float(x) for x in xlc],
                     spy=[None if pd.isna(x) else float(x) for x in spy], at=str(pd.Timestamp.utcnow()))
            dumpj(c, MTCM, indent=1)
        except Exception:
            return None
    mt = xlb / spy; cm = xlc / spy
    mt_lvl_pct = mt.rolling(252, min_periods=120).rank(pct=True)
    cm_chg10_pct = cm.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(mt_lvl_pct=mt_lvl_pct, cm_chg10_pct=cm_chg10_pct))

def cq_in_today(day):
    """v1.13 Night V8: high-yield (HYG) + investment-grade (LQD) + industrials (XLI) + SPY daily closes (cached in
    docs/cqin_sp.json, refreshed once per broker day - same once-a-day shape as mt_cm_today()). Returns a DataFrame
    indexed by date with cq_chg10_pct (252-day rolling percentile of the 10-day % change in the HYG/LQD ratio - low =
    junk bonds underperforming investment-grade, i.e. credit markets de-risking) and in_chg10_pct (252-day rolling
    percentile of the 10-day % change in the XLI/SPY ratio - low = industrials/cyclicals relatively weak) for
    v8_flag() in sp_engine.py, or None on a fetch failure (Night V8 then simply does not fire that night - same
    fail-safe shape as the other night-trigger fetches)."""
    c = loadj(CQIN, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        hyg = pd.Series([np.nan if x is None else x for x in c['hyg']], index=idx)
        lqd = pd.Series([np.nan if x is None else x for x in c['lqd']], index=idx)
        xli = pd.Series([np.nan if x is None else x for x in c['xli']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
    else:
        try:
            hyg = _yahoo_daily_close('HYG'); lqd = _yahoo_daily_close('LQD'); xli = _yahoo_daily_close('XLI'); spy = _yahoo_daily_close('SPY')
            idx = hyg.index.union(lqd.index).union(xli.index).union(spy.index)
            hyg = hyg.reindex(idx); lqd = lqd.reindex(idx); xli = xli.reindex(idx); spy = spy.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     hyg=[None if pd.isna(x) else float(x) for x in hyg], lqd=[None if pd.isna(x) else float(x) for x in lqd],
                     xli=[None if pd.isna(x) else float(x) for x in xli], spy=[None if pd.isna(x) else float(x) for x in spy], at=str(pd.Timestamp.utcnow()))
            dumpj(c, CQIN, indent=1)
        except Exception:
            return None
    cq = hyg / lqd; inr = xli / spy
    cq_chg10_pct = cq.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    in_chg10_pct = inr.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(cq_chg10_pct=cq_chg10_pct, in_chg10_pct=in_chg10_pct))

def du_tk_today(day):
    """v1.14 Night V9: long-duration Treasury (TLT) + intermediate Treasury (IEF) + tech sector (XLK) + SPY daily
    closes (cached in docs/dutk_sp.json, refreshed once per broker day - same once-a-day shape as cq_in_today()).
    Returns a DataFrame indexed by date with du_chg10_pct (252-day rolling percentile of the 10-day % change in the
    TLT/IEF ratio - high = the duration curve steepening sharply, long bonds rallying harder than intermediate) and
    tk_chg10_pct (252-day rolling percentile of the 10-day % change in the XLK/SPY ratio - low = tech sector
    relatively weak vs the index) for v9_flag() in sp_engine.py, or None on a fetch failure (Night V9 then simply
    does not fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(DUTK, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        tlt = pd.Series([np.nan if x is None else x for x in c['tlt']], index=idx)
        ief = pd.Series([np.nan if x is None else x for x in c['ief']], index=idx)
        xlk = pd.Series([np.nan if x is None else x for x in c['xlk']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
    else:
        try:
            tlt = _yahoo_daily_close('TLT'); ief = _yahoo_daily_close('IEF'); xlk = _yahoo_daily_close('XLK'); spy = _yahoo_daily_close('SPY')
            idx = tlt.index.union(ief.index).union(xlk.index).union(spy.index)
            tlt = tlt.reindex(idx); ief = ief.reindex(idx); xlk = xlk.reindex(idx); spy = spy.reindex(idx)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     tlt=[None if pd.isna(x) else float(x) for x in tlt], ief=[None if pd.isna(x) else float(x) for x in ief],
                     xlk=[None if pd.isna(x) else float(x) for x in xlk], spy=[None if pd.isna(x) else float(x) for x in spy], at=str(pd.Timestamp.utcnow()))
            dumpj(c, DUTK, indent=1)
        except Exception:
            return None
    du = tlt / ief; tk = xlk / spy
    du_chg10_pct = du.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    tk_chg10_pct = tk.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    return pd.DataFrame(dict(du_chg10_pct=du_chg10_pct, tk_chg10_pct=tk_chg10_pct))

def bk_es_today(day):
    """v1.15 Night V10: bank/leveraged-loan ETF (BKLN) + high-yield bond ETF (HYG) daily closes, PLUS the CFTC's weekly
    Traders in Financial Futures report for "S&P 500 Consolidated" (leveraged-money net position in the E-mini S&P
    futures) - all cached in docs/bkes_sp.json, refreshed once per broker day (same once-a-day shape as cq_in_today()/
    du_tk_today()). A 3-day publication lag is applied to the COT data (report Tuesday, published the following
    Friday - the same method already used for the parked Round 57 VIX-futures-COT candidate) so nothing is
    look-ahead: each weekly reading only becomes usable from its real publish date, forward-filled onto the daily
    index until the next report publishes. Returns a DataFrame indexed by date with bk_chg10_pct (252-day rolling
    percentile of the 10-day % change in the BKLN/HYG ratio - low = bank loans weakening fast vs high-yield bonds, a
    duration-favoring/dovish credit backdrop) and es_cot_pct (52-week rolling percentile of the leveraged-money net
    position - long minus short - in the S&P E-mini futures, as of its publish date - high = already net-long/
    bullish positioning) for v10_flag() in sp_engine.py, or None on a fetch failure (Night V10 then simply does not
    fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(BKES, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        bkln = pd.Series([np.nan if x is None else x for x in c['bkln']], index=idx)
        hyg = pd.Series([np.nan if x is None else x for x in c['hyg']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            bkln = _yahoo_daily_close('BKLN'); hyg = _yahoo_daily_close('HYG')
            idx = bkln.index.union(hyg.index); bkln = bkln.reindex(idx); hyg = hyg.reindex(idx)
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short',
                '$where': f"market_and_exchange_names='{COT_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([float(x['lev_money_positions_long']) - float(x['lev_money_positions_short']) for x in cj], index=cot_dates)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     bkln=[None if pd.isna(x) else float(x) for x in bkln], hyg=[None if pd.isna(x) else float(x) for x in hyg],
                     cot_dates=[str(t.date()) for t in cot_dates], cot_net=[None if pd.isna(x) else float(x) for x in cot_net], at=str(pd.Timestamp.utcnow()))
            dumpj(c, BKES, indent=1)
        except Exception:
            return None
    bk = bkln / hyg
    bk_chg10_pct = bk.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_pct_weekly = cot_net.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_pct_weekly.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)   # report Tue -> published Fri (nothing look-ahead)
    es_cot_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(bk_chg10_pct=bk_chg10_pct, es_cot_pct=es_cot_pct))

def djia_cr_today(day):
    """v1.16 Night V12: CFTC's weekly Traders in Financial Futures report for "DJIA Consolidated" (leveraged-money
    net position in DJIA futures, normalized by open interest) PLUS ETH-USD/BTC-USD daily closes - all cached in
    docs/djiacr_sp.json, refreshed once per broker day (same once-a-day shape as cq_in_today()/du_tk_today()/
    bk_es_today()). A 3-day publication lag is applied to the COT data (report Tuesday, published the following
    Friday - same method as bk_es_today()/Round 69) so nothing is look-ahead: each weekly reading only becomes
    usable from its real publish date, forward-filled onto the daily index until the next report publishes.
    Returns a DataFrame indexed by date with djia_cot_chg4_pct (52-week rolling percentile of the 4-report SHIFT
    in the DJIA leveraged-money net position - long minus short, over open interest - high = positioning turning
    bullish fast) and cr_chg10_pct (252-day rolling percentile of the 10-day % change in the ETH-USD/BTC-USD
    ratio - low = crypto risk-off) for v12_flag() in sp_engine.py, or None on a fetch failure (Night V12 then
    simply does not fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(DJIACR, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        eth = pd.Series([np.nan if x is None else x for x in c['eth']], index=idx)
        btc = pd.Series([np.nan if x is None else x for x in c['btc']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            eth = _yahoo_daily_close('ETH-USD'); btc = _yahoo_daily_close('BTC-USD')
            idx = eth.index.union(btc.index); eth = eth.reindex(idx); btc = btc.reindex(idx)
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{DJIA_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     eth=[None if pd.isna(x) else float(x) for x in eth], btc=[None if pd.isna(x) else float(x) for x in btc],
                     cot_dates=[str(t.date()) for t in cot_dates], cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, DJIACR, indent=1)
        except Exception:
            return None
    cr = eth / btc
    cr_chg10_pct = cr.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)   # report Tue -> published Fri (nothing look-ahead)
    djia_cot_chg4_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(djia_cot_chg4_pct=djia_cot_chg4_pct, cr_chg10_pct=cr_chg10_pct))

def msciem_cm_today(day):
    """v1.17 Night V13: CFTC's weekly Traders in Financial Futures report for the 3-way-renamed MSCI Emerging-
    Markets equity-index futures series (leveraged-money net position, normalized by open interest) PLUS XLC
    (communications services) + SPY daily closes - all cached in docs/msciemcm_sp.json, refreshed once per broker
    day (same once-a-day shape as mt_cm_today()/bk_es_today()/djia_cr_today()). A 3-day publication lag is applied
    to the COT data (report Tuesday, published the following Friday - same method as every prior COT leg) so
    nothing is look-ahead. Returns a DataFrame indexed by date with msciem_cot_pct (52-week rolling percentile of
    the leveraged-money net position LEVEL itself - not a 4-report shift like V9/V12 - high = already positioned
    extreme-bullish/long) and cm_chg10_pct (252-day rolling percentile of the 10-day % change in the XLC/SPY
    ratio - low = communications services underperforming the index) for v13_flag() in sp_engine.py, or None on a
    fetch failure (Night V13 then simply does not fire that night - same fail-safe shape as the other
    night-trigger fetches)."""
    c = loadj(MSCIEMCM, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        xlc = pd.Series([np.nan if x is None else x for x in c['xlc']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            xlc = _yahoo_daily_close('XLC'); spy = _yahoo_daily_close('SPY')
            idx = xlc.index.union(spy.index); xlc = xlc.reindex(idx); spy = spy.reindex(idx)
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(MSCIEM_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index()
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     xlc=[None if pd.isna(x) else float(x) for x in xlc], spy=[None if pd.isna(x) else float(x) for x in spy],
                     cot_dates=[str(t.date()) for t in cot_dates], cot_net=[None if pd.isna(x) else float(x) for x in cot_net], at=str(pd.Timestamp.utcnow()))
            dumpj(c, MSCIEMCM, indent=1)
        except Exception:
            return None
    cm = xlc / spy
    cm_chg10_pct = cm.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_pct_weekly = cot_net.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_pct_weekly.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)   # report Tue -> published Fri (nothing look-ahead)
    msciem_cot_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(msciem_cot_pct=msciem_cot_pct, cm_chg10_pct=cm_chg10_pct))

def brlfx_ust2y_today(day):
    """v1.18 Night V14: CFTC's weekly Traders in Financial Futures report for Brazilian Real futures (leveraged-
    money net position, normalized by open interest) AND UST 2-Year Note futures (same, CFTC Feb-2022 rename
    concatenated) - both COT-only, no price-ratio leg needed this time (unlike V9/V12/V13) - cached in
    docs/brlust2y_sp.json, refreshed once per broker day (same once-a-day shape as djia_cr_today()/
    msciem_cm_today()). A 3-day publication lag is applied to both series (report Tuesday, published the
    following Friday - same method as every prior COT leg) so nothing is look-ahead. The daily index itself is
    borrowed from SPY's trading calendar (no price values used, just the calendar) so both series land on real
    trading days. Returns a DataFrame indexed by date with brlfx_cot_chg4_pct (52-week rolling percentile of the
    4-report SHIFT in the Brazilian Real leveraged-money net position - high = positioning turning bullish fast)
    and ust2y_cot_chg4_pct (same 4-report-shift method, UST 2yr Note futures - low = 2yr-note positioning falling
    fast) for v14_flag() in sp_engine.py, or None on a fetch failure (Night V14 then simply does not fire that
    night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(BRLUST2Y, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        brl_dates = pd.to_datetime(c['brl_dates']); brl_net4 = pd.Series([np.nan if x is None else float(x) for x in c['brl_net']], index=brl_dates)
        ust_dates = pd.to_datetime(c['ust_dates']); ust_net4 = pd.Series([np.nan if x is None else float(x) for x in c['ust_net']], index=ust_dates)
    else:
        try:
            idx = _yahoo_daily_close('SPY').index
            r1 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{BRL_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r1.raise_for_status(); bj = r1.json()
            brl_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in bj])
            brl_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in bj], index=brl_dates)
            brl_net = brl_net.sort_index(); brl_net4 = brl_net.diff(4)
            r2 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(UST2Y_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r2.raise_for_status(); uj = r2.json()
            ust_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in uj])
            ust_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in uj], index=ust_dates)
            ust_net = ust_net.sort_index(); ust_net4 = ust_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     brl_dates=[str(t.date()) for t in brl_net4.index], brl_net=[None if pd.isna(x) else float(x) for x in brl_net4],
                     ust_dates=[str(t.date()) for t in ust_net4.index], ust_net=[None if pd.isna(x) else float(x) for x in ust_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, BRLUST2Y, indent=1)
        except Exception:
            return None
    brl_net4_pct = brl_net4.rolling(52, min_periods=26).rank(pct=True)
    brl_avail = brl_net4_pct.copy(); brl_avail.index = brl_avail.index + pd.Timedelta(days=3)
    brlfx_cot_chg4_pct = brl_avail.reindex(idx, method='ffill')
    ust_net4_pct = ust_net4.rolling(52, min_periods=26).rank(pct=True)
    ust_avail = ust_net4_pct.copy(); ust_avail.index = ust_avail.index + pd.Timedelta(days=3)
    ust2y_cot_chg4_pct = ust_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(brlfx_cot_chg4_pct=brlfx_cot_chg4_pct, ust2y_cot_chg4_pct=ust2y_cot_chg4_pct))

def ust5y_cq_today(day):
    """v1.19 Night V16: CFTC's weekly Traders in Financial Futures report for UST 5-Year Note futures (leveraged-
    money net position, normalized by open interest, CFTC Feb-2022 rename concatenated) PLUS the SAME HYG/LQD
    credit-quality fetch already used for Night V8 (cq_in_today() above) - cached in docs/ust5ycq_sp.json,
    refreshed once per broker day (same once-a-day shape as djia_cr_today()/msciem_cm_today()/brlfx_ust2y_today()).
    A 3-day publication lag is applied to the COT data (report Tuesday, published the following Friday - same
    method as every prior COT leg) so nothing is look-ahead. Returns a DataFrame indexed by date with
    ust5y_cot_chg4_pct (52-week rolling percentile of the 4-report SHIFT in the UST 5yr-Note leveraged-money net
    position - low = positioning falling fast) and cq_chg10_pct (252-day rolling percentile of the 10-day % change
    in the HYG/LQD ratio - low = credit de-risking, reused straight from cq_in_today() rather than re-fetched) for
    v16_flag() in sp_engine.py, or None on a fetch failure (Night V16 then simply does not fire that night - same
    fail-safe shape as the other night-trigger fetches)."""
    cqdf = cq_in_today(day)
    if cqdf is None: return None
    c = loadj(UST5YCQ, {})
    if c.get('day') == str(day.date()) and 'cot_dates' in c:
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(UST5Y_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index(); cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), cot_dates=[str(t.date()) for t in cot_net4.index],
                     cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, UST5YCQ, indent=1)
        except Exception:
            return None
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    ust5y_cot_chg4_pct = cot_avail.reindex(cqdf.index, method='ffill')
    return pd.DataFrame(dict(ust5y_cot_chg4_pct=ust5y_cot_chg4_pct, cq_chg10_pct=cqdf.cq_chg10_pct))

def mbtc_ng_today(day):
    """v1.19 Night V18: CFTC's weekly Traders in Financial Futures report for Micro Bitcoin futures (leveraged-
    money net position, normalized by open interest) PLUS natural gas (NG=F) + WTI (CL=F) daily closes - cached
    in docs/mbtcng_sp.json, refreshed once per broker day (same once-a-day shape as djia_cr_today()/
    ust5y_cq_today()). A 3-day publication lag is applied to the COT data (report Tuesday, published the
    following Friday - same method as every prior COT leg) so nothing is look-ahead. Returns a DataFrame indexed
    by date with mbtc_cot_chg4_pct (52-week rolling percentile of the 4-report SHIFT in the Micro-Bitcoin
    leveraged-money net position - low = positioning shifting slow) and ng_lvl_pct (252-day rolling percentile of
    the NG=F/CL=F ratio LEVEL, not a change - high = natural gas relatively strong vs WTI) for v18_flag() in
    sp_engine.py, or None on a fetch failure (Night V18 then simply does not fire that night - same fail-safe
    shape as the other night-trigger fetches)."""
    c = loadj(MBTCNG, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        ng = pd.Series([np.nan if x is None else x for x in c['ng']], index=idx)
        cl = pd.Series([np.nan if x is None else x for x in c['cl']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            ng = _yahoo_daily_close('NG=F'); cl = _yahoo_daily_close('CL=F')
            idx = ng.index.union(cl.index); ng = ng.reindex(idx); cl = cl.reindex(idx)
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{MBTC_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index(); cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     ng=[None if pd.isna(x) else float(x) for x in ng], cl=[None if pd.isna(x) else float(x) for x in cl],
                     cot_dates=[str(t.date()) for t in cot_net4.index], cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, MBTCNG, indent=1)
        except Exception:
            return None
    ng_ratio = ng / cl
    ng_lvl_pct = ng_ratio.rolling(252, min_periods=120).rank(pct=True)
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    mbtc_cot_chg4_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(mbtc_cot_chg4_pct=mbtc_cot_chg4_pct, ng_lvl_pct=ng_lvl_pct))

def ultbond_msciem_today(day):
    """v1.23 Night V19: CFTC's weekly Traders in Financial Futures report for Ultra U.S. Treasury Bond futures
    (leveraged-money net position LEVEL, normalized by open interest, CFTC Feb-2022 rename concatenated) AND
    MSCI Emerging-Markets equity-index futures (SAME leveraged-money LEVEL feature already fetched for V13 via
    msciem_cm_today(), fetched independently here rather than shared, so this leg stays self-contained like
    every other V-leg) - both COT-only, no price-ratio leg needed (same shape as brlfx_ust2y_today() above).
    Cached in docs/ultbondmsciem_sp.json, refreshed once per broker day. A 3-day publication lag is applied to
    both series (report Tuesday, published the following Friday - same method as every prior COT leg) so
    nothing is look-ahead. The daily index is borrowed from SPY's trading calendar (no price values used, just
    the calendar) so both series land on real trading days. Returns a DataFrame indexed by date with
    ultbond_cot_pct (52-week rolling percentile of the Ultra-T-Bond leveraged-money net position LEVEL - high =
    already positioned extreme-long duration) and msciem_cot_pct (same LEVEL method, MSCI-EM futures - high =
    already positioned extreme-long) for v19_flag() in sp_engine.py, or None on a fetch failure (Night V19 then
    simply does not fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(ULTBONDMSCIEM, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        ub_dates = pd.to_datetime(c['ub_dates']); ub_pct = pd.Series([np.nan if x is None else float(x) for x in c['ub_pct']], index=ub_dates)
        em_dates = pd.to_datetime(c['em_dates']); em_pct = pd.Series([np.nan if x is None else float(x) for x in c['em_pct']], index=em_dates)
    else:
        try:
            idx = _yahoo_daily_close('SPY').index
            r1 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(ULTBOND_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r1.raise_for_status(); uj = r1.json()
            ub_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in uj])
            ub_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in uj], index=ub_dates)
            ub_net = ub_net.sort_index(); ub_pct = ub_net.rolling(52, min_periods=26).rank(pct=True)
            r2 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(MSCIEM_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r2.raise_for_status(); ej = r2.json()
            em_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in ej])
            em_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in ej], index=em_dates)
            em_net = em_net.sort_index(); em_pct = em_net.rolling(52, min_periods=26).rank(pct=True)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     ub_dates=[str(t.date()) for t in ub_pct.index], ub_pct=[None if pd.isna(x) else float(x) for x in ub_pct],
                     em_dates=[str(t.date()) for t in em_pct.index], em_pct=[None if pd.isna(x) else float(x) for x in em_pct], at=str(pd.Timestamp.utcnow()))
            dumpj(c, ULTBONDMSCIEM, indent=1)
        except Exception:
            return None
    ub_avail = ub_pct.copy(); ub_avail.index = ub_avail.index + pd.Timedelta(days=3)
    ultbond_cot_pct = ub_avail.reindex(idx, method='ffill')
    em_avail = em_pct.copy(); em_avail.index = em_avail.index + pd.Timedelta(days=3)
    msciem_cot_pct = em_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(ultbond_cot_pct=ultbond_cot_pct, msciem_cot_pct=msciem_cot_pct))

def es_am_cp_today(day):
    """v1.23 Night V20: CFTC's weekly Traders in Financial Futures report for the S&P 500 E-mini (ASSET-MANAGER
    net position, 4-report SHIFT, normalized by open interest - real-money/institutional cohort, distinct from
    the leveraged-money category used everywhere else) PLUS the XLP (consumer staples) + SPY daily closes
    (cached in docs/esamcp_sp.json, refreshed once per broker day - same once-a-day shape as mt_cm_today()). A
    3-day publication lag is applied to the COT data (report Tuesday, published the following Friday - same
    method as every prior COT leg) so nothing is look-ahead. Returns a DataFrame indexed by date with
    es_am_chg4_pct (52-week rolling percentile of the 4-report SHIFT in the Asset-Manager net position - high =
    real-money positioning shifting fast-bullish) and cp_chg10_pct (252-day rolling percentile of the 10-day %
    change in the XLP/SPY ratio - low = consumer staples underperforming the index) for v20_flag() in
    sp_engine.py, or None on a fetch failure (Night V20 then simply does not fire that night - same fail-safe
    shape as the other night-trigger fetches)."""
    c = loadj(ESAMCP, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        xlp = pd.Series([np.nan if x is None else x for x in c['xlp']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            xlp = _yahoo_daily_close('XLP'); spy = _yahoo_daily_close('SPY')
            idx = xlp.index.union(spy.index); xlp = xlp.reindex(idx); spy = spy.reindex(idx)
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,asset_mgr_positions_long,asset_mgr_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{COT_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['asset_mgr_positions_long']) - float(x['asset_mgr_positions_short'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index(); cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     xlp=[None if pd.isna(x) else float(x) for x in xlp], spy=[None if pd.isna(x) else float(x) for x in spy],
                     cot_dates=[str(t.date()) for t in cot_net4.index], cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, ESAMCP, indent=1)
        except Exception:
            return None
    cp_ratio = xlp / spy
    cp_chg10_pct = cp_ratio.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    es_am_chg4_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(es_am_chg4_pct=es_am_chg4_pct, cp_chg10_pct=cp_chg10_pct))

def vixfoth_chffx_today(day):
    """v1.23 Night V21: CFTC's weekly Traders in Financial Futures report for VIX futures (OTHER-REPORTABLES
    net position, 4-report SHIFT - smaller reportable hedgers, distinct cohort from leveraged-money) AND Swiss
    Franc futures (LEVERAGED-MONEY net position, same 4-report-shift method) - both COT-only, no price-ratio
    leg needed (same shape as brlfx_ust2y_today() above). Cached in docs/vixfothchffx_sp.json, refreshed once
    per broker day. A 3-day publication lag is applied to both series (report Tuesday, published the following
    Friday - same method as every prior COT leg) so nothing is look-ahead. The daily index is borrowed from
    SPY's trading calendar (no price values used, just the calendar) so both series land on real trading days.
    Returns a DataFrame indexed by date with vixf_oth_chg4_pct (high = Other-Reportables shifting fast toward
    net-long-vol) and chffx_cot_chg4_pct (low = safe-haven-currency positioning shifting fast-bearish) for
    v21_flag() in sp_engine.py, or None on a fetch failure (Night V21 then simply does not fire that night -
    same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(VIXFOTHCHFFX, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        vf_dates = pd.to_datetime(c['vf_dates']); vf_net4 = pd.Series([np.nan if x is None else float(x) for x in c['vf_net']], index=vf_dates)
        ch_dates = pd.to_datetime(c['ch_dates']); ch_net4 = pd.Series([np.nan if x is None else float(x) for x in c['ch_net']], index=ch_dates)
    else:
        try:
            idx = _yahoo_daily_close('SPY').index
            r1 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,other_rept_positions_long,other_rept_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{VIXF_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r1.raise_for_status(); vj = r1.json()
            vf_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in vj])
            vf_net = pd.Series([(float(x['other_rept_positions_long']) - float(x['other_rept_positions_short'])) / float(x['open_interest_all']) for x in vj], index=vf_dates)
            vf_net = vf_net.sort_index(); vf_net4 = vf_net.diff(4)
            r2 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{CHF_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r2.raise_for_status(); hj = r2.json()
            ch_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in hj])
            ch_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in hj], index=ch_dates)
            ch_net = ch_net.sort_index(); ch_net4 = ch_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     vf_dates=[str(t.date()) for t in vf_net4.index], vf_net=[None if pd.isna(x) else float(x) for x in vf_net4],
                     ch_dates=[str(t.date()) for t in ch_net4.index], ch_net=[None if pd.isna(x) else float(x) for x in ch_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, VIXFOTHCHFFX, indent=1)
        except Exception:
            return None
    vf_net4_pct = vf_net4.rolling(52, min_periods=26).rank(pct=True)
    vf_avail = vf_net4_pct.copy(); vf_avail.index = vf_avail.index + pd.Timedelta(days=3)
    vixf_oth_chg4_pct = vf_avail.reindex(idx, method='ffill')
    ch_net4_pct = ch_net4.rolling(52, min_periods=26).rank(pct=True)
    ch_avail = ch_net4_pct.copy(); ch_avail.index = ch_avail.index + pd.Timedelta(days=3)
    chffx_cot_chg4_pct = ch_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(vixf_oth_chg4_pct=vixf_oth_chg4_pct, chffx_cot_chg4_pct=chffx_cot_chg4_pct))

def ust2ynr_msciemchg_today(day):
    """v1.23 Night V22: CFTC's weekly Traders in Financial Futures report for UST 2-Year Note futures (NON-
    REPORTABLES net position, 4-report SHIFT - small speculators/retail, CFTC Feb-2022 rename concatenated) AND
    MSCI Emerging-Markets equity-index futures (LEVERAGED-MONEY net position, same 4-report-shift method - the
    SHIFT variant of the SAME underlying series used as a LEVEL by V13/V19, fetched independently here, a
    genuinely different transform) - both COT-only, no price-ratio leg needed (same shape as brlfx_ust2y_today()
    above). Cached in docs/ust2ynrmsciemchg_sp.json, refreshed once per broker day. A 3-day publication lag is
    applied to both series (report Tuesday, published the following Friday - same method as every prior COT
    leg) so nothing is look-ahead. The daily index is borrowed from SPY's trading calendar (no price values
    used, just the calendar) so both series land on real trading days. Returns a DataFrame indexed by date with
    ust2y_nr_chg4_pct (low = retail 2yr-note positioning falling fast) and msciem_cot_chg4_pct (low = MSCI-EM
    leveraged-money positioning falling fast) for v22_flag() in sp_engine.py, or None on a fetch failure (Night
    V22 then simply does not fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(UST2YNRMSCIEMCHG, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        u2_dates = pd.to_datetime(c['u2_dates']); u2_net4 = pd.Series([np.nan if x is None else float(x) for x in c['u2_net']], index=u2_dates)
        em_dates = pd.to_datetime(c['em_dates']); em_net4 = pd.Series([np.nan if x is None else float(x) for x in c['em_net']], index=em_dates)
    else:
        try:
            idx = _yahoo_daily_close('SPY').index
            r1 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,nonrept_positions_long_all,nonrept_positions_short_all,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(UST2Y_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r1.raise_for_status(); uj = r1.json()
            u2_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in uj])
            u2_net = pd.Series([(float(x['nonrept_positions_long_all']) - float(x['nonrept_positions_short_all'])) / float(x['open_interest_all']) for x in uj], index=u2_dates)
            u2_net = u2_net.sort_index(); u2_net4 = u2_net.diff(4)
            r2 = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,lev_money_positions_long,lev_money_positions_short,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(MSCIEM_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r2.raise_for_status(); ej = r2.json()
            em_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in ej])
            em_net = pd.Series([(float(x['lev_money_positions_long']) - float(x['lev_money_positions_short'])) / float(x['open_interest_all']) for x in ej], index=em_dates)
            em_net = em_net.sort_index(); em_net4 = em_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     u2_dates=[str(t.date()) for t in u2_net4.index], u2_net=[None if pd.isna(x) else float(x) for x in u2_net4],
                     em_dates=[str(t.date()) for t in em_net4.index], em_net=[None if pd.isna(x) else float(x) for x in em_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, UST2YNRMSCIEMCHG, indent=1)
        except Exception:
            return None
    u2_net4_pct = u2_net4.rolling(52, min_periods=26).rank(pct=True)
    u2_avail = u2_net4_pct.copy(); u2_avail.index = u2_avail.index + pd.Timedelta(days=3)
    ust2y_nr_chg4_pct = u2_avail.reindex(idx, method='ffill')
    em_net4_pct = em_net4.rolling(52, min_periods=26).rank(pct=True)
    em_avail = em_net4_pct.copy(); em_avail.index = em_avail.index + pd.Timedelta(days=3)
    msciem_cot_chg4_pct = em_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(ust2y_nr_chg4_pct=ust2y_nr_chg4_pct, msciem_cot_chg4_pct=msciem_cot_chg4_pct))

def uti2nr_tr_today(day):
    """v1.23 Night V23: CFTC's weekly Traders in Financial Futures report for the E-mini S&P Utilities sector
    futures (NON-REPORTABLES net position, 4-report SHIFT - small speculators/retail) PLUS the XTN (transports)
    + SPY daily closes (cached in docs/uti2nrtr_sp.json, refreshed once per broker day - same once-a-day shape
    as mt_cm_today()). A 3-day publication lag is applied to the COT data (report Tuesday, published the
    following Friday - same method as every prior COT leg) so nothing is look-ahead. Returns a DataFrame
    indexed by date with uti2_nr_chg4_pct (52-week rolling percentile of the 4-report SHIFT in the retail net
    position in Utilities-sector futures - low = retail positioning falling fast) and tr_chg10_pct (252-day
    rolling percentile of the 10-day % change in the XTN/SPY ratio - low = transports underperforming the
    index) for v23_flag() in sp_engine.py, or None on a fetch failure (Night V23 then simply does not fire that
    night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(UTI2NRTR, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        xtn = pd.Series([np.nan if x is None else x for x in c['xtn']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            xtn = _yahoo_daily_close('XTN'); spy = _yahoo_daily_close('SPY')
            idx = xtn.index.union(spy.index); xtn = xtn.reindex(idx); spy = spy.reindex(idx)
            r = requests.get(COT_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,nonrept_positions_long_all,nonrept_positions_short_all,open_interest_all',
                '$where': f"market_and_exchange_names='{UTI2_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['nonrept_positions_long_all']) - float(x['nonrept_positions_short_all'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index(); cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     xtn=[None if pd.isna(x) else float(x) for x in xtn], spy=[None if pd.isna(x) else float(x) for x in spy],
                     cot_dates=[str(t.date()) for t in cot_net4.index], cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, UTI2NRTR, indent=1)
        except Exception:
            return None
    tr_ratio = xtn / spy
    tr_chg10_pct = tr_ratio.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    uti2_nr_chg4_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(uti2_nr_chg4_pct=uti2_nr_chg4_pct, tr_chg10_pct=tr_chg10_pct))

def sgoth_fy_today(day):
    """v1.24 Night V25: CFTC's weekly Disaggregated Commitments of Traders report for Sugar No. 11 futures
    (OTHER-REPORTABLES net position LEVEL, normalized by open interest - a category that only exists in the
    Disaggregated report, not the Traders-in-Financial-Futures dataset used by every prior COT leg) PLUS the
    XLF (financials sector) + SPY daily closes (cached in docs/sgothfy_sp.json, refreshed once per broker day
    - same once-a-day shape as uti2nr_tr_today()). A 3-day publication lag is applied to the COT data (report
    Tuesday, published the following Friday - same method as every prior COT leg) so nothing is look-ahead.
    Returns a DataFrame indexed by date with sg_oth_pct (52-week rolling percentile of the Sugar Other-
    Reportables net position LEVEL - high = this cohort already positioned net-long sugar) and fy_chg10_pct
    (252-day rolling percentile of the 10-day % change in the XLF/SPY ratio - low = financials underperforming
    the index) for v25_flag() in sp_engine.py, or None on a fetch failure (Night V25 then simply does not
    fire that night - same fail-safe shape as the other night-trigger fetches)."""
    c = loadj(SGOTHFY, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        xlf = pd.Series([np.nan if x is None else x for x in c['xlf']], index=idx)
        spy = pd.Series([np.nan if x is None else x for x in c['spy']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            xlf = _yahoo_daily_close('XLF'); spy = _yahoo_daily_close('SPY')
            idx = xlf.index.union(spy.index); xlf = xlf.reindex(idx); spy = spy.reindex(idx)
            r = requests.get(DISAGG_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,other_rept_positions_long,other_rept_positions_short,open_interest_all',
                '$where': f"market_and_exchange_names='{SUGAR_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['other_rept_positions_long']) - float(x['other_rept_positions_short'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index()
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     xlf=[None if pd.isna(x) else float(x) for x in xlf], spy=[None if pd.isna(x) else float(x) for x in spy],
                     cot_dates=[str(t.date()) for t in cot_net.index], cot_net=[None if pd.isna(x) else float(x) for x in cot_net], at=str(pd.Timestamp.utcnow()))
            dumpj(c, SGOTHFY, indent=1)
        except Exception:
            return None
    fy_ratio = xlf / spy
    fy_chg10_pct = fy_ratio.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_pct = cot_net.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    sg_oth_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(sg_oth_pct=sg_oth_pct, fy_chg10_pct=fy_chg10_pct))

def fcsw_cq_today(day):
    """v1.24 Night V26: CFTC's weekly Disaggregated Commitments of Traders report for Feeder Cattle futures
    (SWAP-DEALER net position, 4-report SHIFT, normalized by open interest - a category that only exists in
    the Disaggregated report) PLUS the SAME HYG/LQD credit-quality fetch already used for Night V8/V16
    (cq_in_today() above) - cached in docs/fcswcq_sp.json, refreshed once per broker day (same once-a-day
    shape as ust5y_cq_today()). A 3-day publication lag is applied to the COT data (report Tuesday, published
    the following Friday - same method as every prior COT leg) so nothing is look-ahead. Returns a DataFrame
    indexed by date with fc_sw_chg4_pct (52-week rolling percentile of the 4-report SHIFT in the Feeder-Cattle
    Swap-Dealer net position - high = positioning rising fast) and cq_chg10_pct (252-day rolling percentile of
    the 10-day % change in the HYG/LQD ratio - low = credit de-risking, reused straight from cq_in_today()
    rather than re-fetched) for v26_flag() in sp_engine.py, or None on a fetch failure (Night V26 then simply
    does not fire that night - same fail-safe shape as the other night-trigger fetches)."""
    cqdf = cq_in_today(day)
    if cqdf is None: return None
    c = loadj(FCSWCQ, {})
    if c.get('day') == str(day.date()) and 'cot_dates' in c:
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            r = requests.get(DISAGG_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,swap_positions_long_all,swap__positions_short_all,open_interest_all',
                '$where': f"market_and_exchange_names='{FC_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['swap_positions_long_all']) - float(x['swap__positions_short_all'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index(); cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), cot_dates=[str(t.date()) for t in cot_net4.index],
                     cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, FCSWCQ, indent=1)
        except Exception:
            return None
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    fc_sw_chg4_pct = cot_avail.reindex(cqdf.index, method='ffill')
    return pd.DataFrame(dict(fc_sw_chg4_pct=fc_sw_chg4_pct, cq_chg10_pct=cqdf.cq_chg10_pct))

def vixlcomm_dxyfnr_today(day):
    """v1.24 Night V27: CFTC's weekly LEGACY Commitments of Traders report for VIX futures (COMMERCIAL net
    position, 4-report SHIFT - a category that only exists in the Legacy report, not the Traders-in-
    Financial-Futures dataset used by V21's vixfoth_chffx_today()) AND the US-Dollar-Index futures
    (NON-REPORTABLES net position, same 4-report-shift method, CFTC rename Feb-2022 concatenated) - both
    COT-only, no price-ratio leg needed (same shape as brlfx_ust2y_today() above). Cached in
    docs/vixlcommdxyfnr_sp.json, refreshed once per broker day. A 3-day publication lag is applied to both
    series (report Tuesday, published the following Friday - same method as every prior COT leg) so nothing
    is look-ahead. The daily index is borrowed from SPY's trading calendar (no price values used, just the
    calendar) so both series land on real trading days. Returns a DataFrame indexed by date with
    vixl_comm_chg4_pct (high = VIX-futures commercial hedgers shifting fast toward net-long-vol) and
    dxyf_nr_chg4_pct (high = Dollar-Index retail positioning shifting fast-bullish) for v27_flag() in
    sp_engine.py, or None on a fetch failure (Night V27 then simply does not fire that night - same fail-safe
    shape as the other night-trigger fetches)."""
    c = loadj(VIXLCOMMDXYFNR, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        vl_dates = pd.to_datetime(c['vl_dates']); vl_net4 = pd.Series([np.nan if x is None else float(x) for x in c['vl_net']], index=vl_dates)
        dx_dates = pd.to_datetime(c['dx_dates']); dx_net4 = pd.Series([np.nan if x is None else float(x) for x in c['dx_net']], index=dx_dates)
    else:
        try:
            idx = _yahoo_daily_close('SPY').index
            r1 = requests.get(LEGACY_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,comm_positions_long_all,comm_positions_short_all,open_interest_all',
                '$where': f"market_and_exchange_names='{VIXF_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r1.raise_for_status(); vj = r1.json()
            vl_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in vj])
            vl_net = pd.Series([(float(x['comm_positions_long_all']) - float(x['comm_positions_short_all'])) / float(x['open_interest_all']) for x in vj], index=vl_dates)
            vl_net = vl_net.sort_index(); vl_net4 = vl_net.diff(4)
            r2 = requests.get(LEGACY_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,nonrept_positions_long_all,nonrept_positions_short_all,open_interest_all',
                '$where': "market_and_exchange_names in ('" + "','".join(DXYF_MKT) + "')",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r2.raise_for_status(); dj = r2.json()
            dx_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in dj])
            dx_net = pd.Series([(float(x['nonrept_positions_long_all']) - float(x['nonrept_positions_short_all'])) / float(x['open_interest_all']) for x in dj], index=dx_dates)
            dx_net = dx_net.sort_index(); dx_net4 = dx_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     vl_dates=[str(t.date()) for t in vl_net4.index], vl_net=[None if pd.isna(x) else float(x) for x in vl_net4],
                     dx_dates=[str(t.date()) for t in dx_net4.index], dx_net=[None if pd.isna(x) else float(x) for x in dx_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, VIXLCOMMDXYFNR, indent=1)
        except Exception:
            return None
    vl_net4_pct = vl_net4.rolling(52, min_periods=26).rank(pct=True)
    vl_avail = vl_net4_pct.copy(); vl_avail.index = vl_avail.index + pd.Timedelta(days=3)
    vixl_comm_chg4_pct = vl_avail.reindex(idx, method='ffill')
    dx_net4_pct = dx_net4.rolling(52, min_periods=26).rank(pct=True)
    dx_avail = dx_net4_pct.copy(); dx_avail.index = dx_avail.index + pd.Timedelta(days=3)
    dxyf_nr_chg4_pct = dx_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(vixl_comm_chg4_pct=vixl_comm_chg4_pct, dxyf_nr_chg4_pct=dxyf_nr_chg4_pct))

def eurjpyncomm_bt_today(day):
    """v1.24 Night V28: CFTC's weekly LEGACY Commitments of Traders report for EUR/JPY cross-rate futures
    (NON-COMMERCIAL net position, 4-report SHIFT - a category that only exists in the Legacy report) PLUS
    Bitcoin (BTC-USD) daily closes (cached in docs/eurjpyncommbt_sp.json, refreshed once per broker day - same
    once-a-day shape as uti2nr_tr_today(), except the second leg is a standalone price series, not a ratio).
    A 3-day publication lag is applied to the COT data (report Tuesday, published the following Friday - same
    method as every prior COT leg) so nothing is look-ahead. Returns a DataFrame indexed by date with
    eurjpyl_ncomm_chg4_pct (52-week rolling percentile of the 4-report SHIFT in the EUR/JPY-cross
    Non-Commercial net position - low = speculative positioning falling fast) and bt_chg10_pct (252-day
    rolling percentile of Bitcoin's own 10-day % change - high = Bitcoin rising fast) for v28_flag() in
    sp_engine.py, or None on a fetch failure (Night V28 then simply does not fire that night - same fail-safe
    shape as the other night-trigger fetches)."""
    c = loadj(EURJPYNCOMMBT, {})
    if c.get('day') == str(day.date()) and 'dates' in c:
        idx = pd.to_datetime(c['dates'])
        bt = pd.Series([np.nan if x is None else x for x in c['bt']], index=idx)
        cot_dates = pd.to_datetime(c['cot_dates']); cot_net4 = pd.Series([np.nan if x is None else float(x) for x in c['cot_net']], index=cot_dates)
    else:
        try:
            bt = _yahoo_daily_close('BTC-USD'); idx = bt.index
            r = requests.get(LEGACY_URL, params={
                '$select': 'report_date_as_yyyy_mm_dd,noncomm_positions_long_all,noncomm_positions_short_all,open_interest_all',
                '$where': f"market_and_exchange_names='{EURJPYL_MKT}'",
                '$order': 'report_date_as_yyyy_mm_dd ASC', '$limit': 5000}, timeout=20)
            r.raise_for_status(); cj = r.json()
            cot_dates = pd.to_datetime([x['report_date_as_yyyy_mm_dd'] for x in cj])
            cot_net = pd.Series([(float(x['noncomm_positions_long_all']) - float(x['noncomm_positions_short_all'])) / float(x['open_interest_all']) for x in cj], index=cot_dates)
            cot_net = cot_net.sort_index(); cot_net4 = cot_net.diff(4)
            c = dict(day=str(day.date()), dates=[str(t.date()) for t in idx],
                     bt=[None if pd.isna(x) else float(x) for x in bt],
                     cot_dates=[str(t.date()) for t in cot_net4.index], cot_net=[None if pd.isna(x) else float(x) for x in cot_net4], at=str(pd.Timestamp.utcnow()))
            dumpj(c, EURJPYNCOMMBT, indent=1)
        except Exception:
            return None
    bt_chg10_pct = bt.pct_change(10).rolling(252, min_periods=120).rank(pct=True)
    cot_net4_pct = cot_net4.rolling(52, min_periods=26).rank(pct=True)
    cot_avail = cot_net4_pct.copy(); cot_avail.index = cot_avail.index + pd.Timedelta(days=3)
    eurjpyl_ncomm_chg4_pct = cot_avail.reindex(idx, method='ffill')
    return pd.DataFrame(dict(eurjpyl_ncomm_chg4_pct=eurjpyl_ncomm_chg4_pct, bt_chg10_pct=bt_chg10_pct))

def lasthour_stats(b):
    """v1.09 Night V4: b = one finished broker day's minute bars (o h l c v). Returns (ret, vol) for the 22:00-23:00 broker window
    (= 15:00-16:00 NY, the same window the backtest's lh_pct/lhvol_z were built from), or (None, None) if that window has no bars.
    ret = % price return, open of the window's first bar -> close of its last bar. vol = sum of lastTradedVolume over the window
    (NaN bars treated as 0; None if the whole window has no volume data, e.g. months saved before this went live)."""
    hm = b.index.hour * 60 + b.index.minute
    w = b[(hm >= 22 * 60) & (hm < 23 * 60)]
    if not len(w) or not w.o.iloc[0]: return None, None
    ret = float(w.c.iloc[-1] / w.o.iloc[0] - 1)
    vol = float(np.nansum(w.v.values)) if w.v.notna().any() else None
    return ret, vol

def lh_today(day, hist):
    """v1.09 Night V4: extends docs/sp_lh_live.json with every newly-finished day's own last-hour return+volume (from `hist`, the
    dashboard's stored minute history - cheap, only new days since the last call are computed), merges the return series onto the
    static backtest seed (docs/sp_lh_seed.json), and returns a DataFrame indexed by date with lh_pct (252-day rolling percentile
    of the return, >=120 days warm-up - active from day one via the seed) and lhvol_z (z-score of the last hour's volume vs its
    own trailing 20-day average, >=10 days warm-up - starts with nothing and fills in naturally over the dashboard's own first
    ~2-4 live weeks, since Capital.com's volume count is a different scale to the RoboForex data the seed uses, so it is
    deliberately NOT seeded - see the v1.09 header note in sp_engine.py)."""
    seed = loadj(LH_SEED, {'dates': [], 'ret': []})
    live = loadj(LH_LIVE, {'dates': [], 'ret': [], 'vol': []})
    last_live = pd.Timestamp(live['dates'][-1]) if live['dates'] else None
    days = sorted(set(hist.index.normalize()))
    changed = False
    for d in days:
        if d >= day: continue                                                        # only finished days strictly before the one being decided
        if last_live is not None and d <= last_live: continue
        b = hist[(hist.index >= d) & (hist.index < d + pd.Timedelta(days=1))]
        ret, vol = lasthour_stats(b)
        if ret is None: continue
        live['dates'].append(str(d.date())); live['ret'].append(ret); live['vol'].append(vol); changed = True
    if changed: dumpj(live, LH_LIVE, indent=1)
    if not live['dates']: return None
    idx_s = pd.to_datetime(seed['dates']); idx_l = pd.to_datetime(live['dates'])
    ret = pd.concat([pd.Series(seed.get('ret', []), index=idx_s), pd.Series(live['ret'], index=idx_l)])
    ret = ret[~ret.index.duplicated(keep='last')].sort_index()
    vol = pd.Series(live['vol'], index=idx_l).sort_index()
    lh_pct = ret.rolling(252, min_periods=120).rank(pct=True)
    vmean = vol.rolling(20, min_periods=10).mean(); vstd = vol.rolling(20, min_periods=10).std()
    lhvol_z = (vol - vmean) / vstd
    return pd.DataFrame(dict(lh_pct=lh_pct, lhvol_z=lhvol_z))

def stress_today(day, now):
    """v1.04 night-leg flag for broker day `day` (cached in docs/cboe_sp.json). The last close before the day must be the previous NY
    weekday; if the Cboe file does not have it yet, today's delayed quote (the 4:15 pm close) is used for that date."""
    c = loadj(CBOE, {})
    if c.get('day') == str(day.date()) and 'stress' in c: return c['stress'], c
    try:
        V = pd.DataFrame(dict(vix=_cboe_series('VIX', 'CLOSE'), v3m=_cboe_series('VIX3M', 'CLOSE'), vvix=_cboe_series('VVIX', 'VVIX'))).dropna()
        prev = (pd.Timestamp(day) - pd.offsets.BDay(1)).normalize(); added = False
        if V.index.max() < prev:
            q = {}
            for sym, k in (('VIX', 'vix'), ('VIX3M', 'v3m'), ('VVIX', 'vvix')):
                r = requests.get(CBOE_Q.format(sym), timeout=20); r.raise_for_status(); q[k] = float(r.json()['data']['current_price'])
            V.loc[prev] = [q['vix'], q['v3m'], q['vvix']]; added = True
        f, d = S.stress_flag(V, day)
        c = dict(day=str(day.date()), stress=bool(f), detail=d, quote_used=added, at=str(now))
        dumpj(c, CBOE, indent=1); return c['stress'], c
    except Exception as e:
        return None, dict(error=f'{type(e).__name__}: {str(e)[:100]}')

def loadj(p, d):
    try: return json.load(open(p))
    except Exception: return d
def dumpj(o, p, **kw):
    tmp = p + '.tmp'
    with open(tmp, 'w') as f: json.dump(o, f, **kw)
    os.replace(tmp, p)
def dubai(t): return F.broker_to_dubai(pd.Timestamp(t)).strftime('%-I:%M %p').lower()

# ---------------- data checks (22 Oct fix) ----------------
# Finished days: saved only when reasonably complete (>= 85% of the usual minute count for that weekday in the stored history); otherwise
# retried next run without moving on. A day is called a holiday (or a short day, saved as it is) only after 3 tries at least 30 min apart.
# Today: newest closed bar older than 3 min, or a hole of more than 3 missing minutes (during market hours) = feed error
# (the card keeps the last good update). A hole that is still there 5 min after it was first seen is taken as a hole in the source itself.
FULL_SHARE, TRIES, TRY_GAP, LATE, HOLE_OK = 0.85, 3, pd.Timedelta(minutes=30), pd.Timedelta(minutes=3), pd.Timedelta(minutes=5)
OPEN_HM = 75                          # market hours checked: 01:15 broker .. the day end (23:00, Fri 22:50)

class FeedError(RuntimeError):
    pass

def load_state(): return loadj(STATE, {})
def save_state(st): dumpj(st, STATE, indent=1)

def usual_count(hist, d):
    """usual number of minute bars of a stored day on d's weekday (median of the last 8 such days; else of the last 20 days)."""
    if hist is None or not len(hist): return None
    c = hist.groupby(hist.index.normalize()).size()
    same = c[c.index.dayofweek == d.dayofweek].iloc[-8:]
    if len(same) >= 2: return float(same.median())
    return float(c.iloc[-20:].median()) if len(c) >= 3 else None

def judge_day(st, key, n, usual, now):
    """-> 'save' (complete), 'short' (still partial after 3 tries: saved as it is), 'holiday' (< 60 bars after 3 tries) or 'wait'."""
    tries = st.setdefault('tries', {})
    if n >= (60 if usual is None else max(60, FULL_SHARE * usual)):
        tries.pop(key, None); return 'save'
    t = tries.setdefault(key, [])
    if not t or pd.Timestamp(now) - pd.Timestamp(t[-1]) >= TRY_GAP: t.append(str(now))
    if len(t) < TRIES: return 'wait'
    tries.pop(key, None)
    return 'holiday' if n < 60 else 'short'

def feed_check(b, now, eod, st, key):
    """None if today's closed bars look complete, else the reason (market hours only)."""
    hm = now.hour * 60 + now.minute
    if now >= eod or hm < OPEN_HM: return None
    if not len(b): return 'no price bars received for today'
    age = now - (b.index[-1] + pd.Timedelta(minutes=1))
    if age > LATE: return f'newest closed price bar ({dubai(b.index[-1])} Dubai) is {age.total_seconds() / 60:.0f} min old'
    w = b.index                                          # holes anywhere today (a missing 900-minute chunk too), not only the last hour
    gaps = [(a, c) for a, c in zip(w[:-1], w[1:]) if c - a - pd.Timedelta(minutes=1) > LATE]
    st0 = now.normalize() + pd.Timedelta(minutes=OPEN_HM)
    if w[0] > st0: gaps = [(st0, w[0])] + gaps             # first bar of the day missing
    day = str(now.normalize().date()); seen = st.setdefault('holes', {}).setdefault(key, {})
    for k in [k for k in seen if not k.startswith(day)]: seen.pop(k)
    bad = []
    for a, c in gaps:
        k = str(a); seen.setdefault(k, str(now))
        if now - pd.Timestamp(seen[k]) < HOLE_OK: bad.append(f'{dubai(a)}-{dubai(c)}')
    return f'price bars missing between {", ".join(bad)} Dubai' if bad else None

def load_month(f):
    if not os.path.exists(f): return None
    z = np.load(f)
    v = z['v'] if 'v' in z.files else np.full(len(z['t']), np.nan)   # v1.09: months saved before Night V4 have no volume column - NaN, not a crash
    return pd.DataFrame({'o': z['o'], 'h': z['h'], 'l': z['l'], 'c': z['c'], 'v': v}, index=pd.DatetimeIndex(z['t'].astype('datetime64[m]')))
def load_hist():
    fr = [load_month(f) for f in sorted(glob.glob(os.path.join(MIN, '*.npz')))]
    fr = [x for x in fr if x is not None]
    if not fr: raise RuntimeError('docs/sp_min history missing')
    return pd.concat(fr).sort_index()
def save_day(bars):
    os.makedirs(MIN, exist_ok=True); per = bars.index[0].strftime('%Y-%m'); f = os.path.join(MIN, per + '.npz')
    b = bars.copy()
    if 'v' not in b.columns: b['v'] = np.nan                          # v1.09: callers that still pass o/h/l/c only still work
    old = load_month(f); d = pd.concat([old, b[['o', 'h', 'l', 'c', 'v']]]) if old is not None else b[['o', 'h', 'l', 'c', 'v']]
    d = d[~d.index.duplicated(keep='last')].sort_index(); tmp = f + '.part'
    with open(tmp, 'wb') as fh:
        np.savez_compressed(fh, t=d.index.values.astype('datetime64[m]').astype(np.int64), o=d.o.values, h=d.h.values, l=d.l.values, c=d.c.values, v=d.v.values)
    os.replace(tmp, f)

EPIC_NOW = [EPIC]; _TRIED = [False]
def find_epic(feed):
    """Look up the US 500 epic in Capital.com's market list (used only if the default name is refused)."""
    r = requests.get(f'{feed.base}/api/v1/markets', headers=feed.h, timeout=20, params={'searchTerm': 'US 500'}); r.raise_for_status()
    for mkt in r.json().get('markets', []):
        nm = str(mkt.get('instrumentName', '')).lower()
        if ('us 500' in nm or 's&p' in nm) and 'future' not in nm:
            EPIC_NOW[0] = mkt['epic']; print('S&P epic found:', EPIC_NOW[0]); return
    raise RuntimeError('US 500 not found in Capital.com markets - set CAPITAL_EPIC_SP')

def minutes(feed, start_b, end_b):
    """Capital.com US 500 minute bars between two broker times: index broker time, Bid o/h/l/c + spread (ask close - bid close)."""
    if feed.h is None: feed.login()
    to_utc = lambda b: (pd.Timestamp(b) - pd.Timedelta(hours=7)).tz_localize(F.NY, ambiguous=False, nonexistent='shift_forward').tz_convert('UTC').tz_localize(None)
    t0, end = to_utc(start_b), to_utc(end_b); out = []
    while t0 < end:
        if time.time() > DEADLINE: raise TimeoutError('S&P time budget used up - next run continues')
        t1 = min(end, t0 + pd.Timedelta(minutes=900))
        r = requests.get(f'{feed.base}/api/v1/prices/{EPIC_NOW[0]}', headers=feed.h, timeout=20,
                         params={'resolution': 'MINUTE', 'max': 1000, 'from': t0.strftime('%Y-%m-%dT%H:%M:%S'), 'to': t1.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 200:
            for p in r.json().get('prices', []):
                ask = (p.get('closePrice') or {}).get('ask')
                out.append((p['snapshotTimeUTC'], p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                            np.nan if ask is None else ask - p['closePrice']['bid'], p.get('lastTradedVolume')))   # v1.09: volume, for Night V4's lhvol_z
        elif r.status_code == 404 and 'epic' in r.text.lower() and not _TRIED[0]:
            _TRIED[0] = True; find_epic(feed); continue
        elif r.status_code not in (400, 404):
            r.raise_for_status()
        t0 = t1; time.sleep(0.15)
    if not out: return pd.DataFrame(columns=['o', 'h', 'l', 'c', 'sp', 'v'], index=pd.DatetimeIndex([]), dtype=float)
    d = pd.DataFrame(out, columns=['t', 'o', 'h', 'l', 'c', 'sp', 'v']).drop_duplicates('t')
    d.index = F.utc_to_broker(pd.to_datetime(d.t)); d = d[d.index.dayofweek < 5]
    return d[['o', 'h', 'l', 'c', 'sp', 'v']].astype(float).sort_index()

def catch_up(feed, hist, day, get=None, now=None, st=None):
    """Add every finished weekday after the last stored day and before `day` (Capital.com minutes), only when complete (judge_day).
    Returns (added, pending): pending = the day still being retried (nothing after it is added yet)."""
    get = get or minutes; now = now or F.broker_now(); st = {} if st is None else st
    last = hist.index[-1].normalize(); added = []; hol = st.setdefault('holidays', [])
    while last + pd.Timedelta(days=1) < day:
        nxt = last + pd.Timedelta(days=1)
        if nxt.dayofweek < 5 and str(nxt.date()) not in hol:
            b = get(feed, nxt, nxt + pd.Timedelta(days=1)); b = b[(b.index >= nxt) & (b.index < nxt + pd.Timedelta(days=1))]
            u = usual_count(hist.iloc[-60 * 1500:], nxt); v = judge_day(st, str(nxt.date()), len(b), u, now)
            if v in ('save', 'short'):
                save_day(b); hist = pd.concat([hist, b[['o', 'h', 'l', 'c']]]); added.append(str(nxt.date()) + (' (short day)' if v == 'short' else ''))
            elif v == 'holiday': hol.append(str(nxt.date())); added.append(str(nxt.date()) + ' (no prices - holiday)')
            else: return added, [f'{nxt.date()}: {len(b)} of ~{u or 60:.0f} minute bars so far - retrying']
        last = nxt
    hol[:] = [h for h in hol if h >= str((day - pd.Timedelta(days=90)).date())]
    return added, []

def seed(feed, day, get):
    """No stored history yet: fetch the last 4 weeks of finished weekdays from Capital.com and keep the reasonably complete ones
    (>= 85% of the median minute count of the fetched days; 22 Oct fix). Later days come through catch_up."""
    got = []
    for d in pd.bdate_range(day - pd.Timedelta(days=28), day - pd.Timedelta(days=1)):
        b = get(feed, d, d + pd.Timedelta(days=1)); b = b[(b.index >= d) & (b.index < d + pd.Timedelta(days=1))]
        if len(b) >= 60: got.append(b)
    if not got: return
    med = float(np.median([len(b) for b in got]))
    for b in got:
        if len(b) >= FULL_SHARE * med: save_day(b)

def row(t, b, now, sp):
    st = t['status']; nite = bool(t.get('night'))
    res = None if t['pts'] is None else round(t['pts'], 1)
    live = None
    if st == 'open' and len(b):
        pxn = float(b.c.values[-1]); live = round(t['dir'] * (pxn - t['entry']) - sp, 1)
    return dict(time=dubai(t['t']), side='BUY' if t['dir'] == 1 else 'SELL', name=t['name'], src='Night' if nite else ('TOM' if t['src'] == 2 else ('Nasdaq' if t['src'] == 0 else 'S&P')), leg=t['leg'], night=nite,
                price=round(t['entry'], 1), entry=round(t['entry'], 1), stop=round(t['stop'], 1), stop0=round(t['stop0'], 1), stop_pts=round(t['sd'], 1),
                half_px=None, half=False, size='full', status=st,
                exit=None if t['exit'] is None else round(t['exit'], 1), exit_time=None if t['exit_t'] is None else dubai(t['exit_t']),
                res=res, res_sized=res, r=None if t['r'] is None else round(t['r'], 3), r_sized=None if t['r'] is None else round(t['r'], 3),
                live=live, spread=round(sp, 2))

def summary(J, day=None):
    D3 = [d for d in J.get('days', []) if d.get('rules') == RULES]
    if not D3: return dict(since=None, trades=0, rules=RULES)
    allt = [t for d in D3 for t in d['trades']]; rr = [t['res'] for t in allt if t.get('res') is not None]
    start = D3[0]['date']; end = str((day or pd.Timestamp(D3[-1]['date'])).date())
    wd = max(1, len(pd.bdate_range(start, end))); tdays = sum(1 for d in D3 if d['trades'])
    gp, gl = sum(p for p in rr if p > 0), -sum(p for p in rr if p < 0)
    return dict(since=pd.Timestamp(start).strftime('%d %b %Y'), weekdays=wd, trades=len(allt), days=round(100 * tdays / wd, 1), perday=round(len(allt) / wd, 2),
                closed=len(rr), win=(round(100 * sum(p > 0 for p in rr) / len(rr), 1) if rr else None), pf=(round(gp / gl, 2) if gl > 0 else None),
                net=round(sum(rr), 1) if rr else None, rules=RULES, direction=None,
                green=round(100 * sum(1 for d in D3 if sum(t.get('res') or 0 for t in d['trades']) > 0) / wd, 1))

def jdays(J): return J.get('days', [])[-30:][::-1]

def base_card(A=None):
    note = ('14-day range ' + ('—' if A is None else f'{A:,.0f} pts') + ' · stop 0.75 x range' + ('' if A is None else f' (= {0.75 * A:,.0f} pts)') +
            ' · no half-close · the day\'s first signal sets BUY or SELL, later signals the same way add (max 3 trades) · v1.04: no 2nd/3rd trade from '
            '11:00 am New York or once the day is up half a stop · signals: Nasdaq desk signals copied in US hours + S&P 9:40 am New York move, yesterday '
            'high/low sweep, big move by 10 am New York · close 3:30 pm New York · NIGHT trade on high-fear nights (VIX above VIX3M, or VIX / VVIX in '
            'their 1-year top 10%): BUY 6:01 pm New York (v1.07: Mon/Tue/Wed broker-days only), stop 1 x range (v1.07, was 2x), close 10:00 am New York · '
            'v1.07 TURN-OF-MONTH: on the last broker weekday of the month and the first 3 of the next, BUY 9:30 am New York, stop 0.75 x range, close 3:30 pm '
            'New York - only on a day with no other S&P trade · v1.08 NIGHT V3: a 2nd, independent night trigger (only fires when the night trade above does '
            'not - never both), broker-day Wed/Thu/Fri only, on a gold+WTI combined overnight shock (the smaller of gold\'s and WTI\'s own 252-day-percentile '
            '|daily move|, from 2 days before, >= 0.70): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as the night leg '
            'above · v1.09 NIGHT V4: a 3rd, independent night trigger (only fires when the two night trades above do not - never more than one a night), no '
            'weekday restriction, on a weak last-hour close (252-day percentile of the 15:00-16:00 New York return <= 0.30) combined with a last-hour volume '
            'spike (z-score vs its own trailing 20-day average >= 2.0): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as the '
            'other night trades. WATCH ITEM (only 25 historical occurrences, mostly overlapping the VIX night trade above) - needs ~2-4 weeks of its own '
            'live volume history before it can fire at all · v1.10 NIGHT V5: a 4th, independent night trigger (only fires when the three night trades above '
            'do not - never more than one a night), no weekday restriction, on the US Dollar Index weakening over 5 days (252-day percentile of the 5-day % '
            'change <= 0.20) combined with the market narrowing on both a 10-day AND a 20-day horizon (252-day percentile of the RSP/SPY equal-weight/'
            'cap-weight ratio\'s 10-day and 20-day % change, both <= 0.20): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as '
            'the other night trades. WATCH ITEM (20 historical Python occurrences, 18 confirmed in MT4) - unlike Night V4, this data is available from day '
            'one, no live warm-up needed · v1.11 NIGHT V6: a 5th, independent night trigger (only fires when the four night trades above do not - never '
            'more than one a night), no weekday restriction, on the broad trade-weighted US Dollar index (FRED DTWEXBGS, 26-currency basket) being broadly '
            'weak (252-day percentile of its level <= 0.15) combined with the pan-European STOXX50E index having a shock move the prior session (252-day '
            'percentile of its |daily % close move| >= 0.85): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as the other '
            'night trades. WATCH ITEM (24 historical Python occurrences, 14 confirmed in MT4) - like Night V5, this data is available from day one, no '
            'live warm-up needed · v1.12 NIGHT V7: a 6th, independent night trigger (only fires when the five night trades above do not - never more '
            'than one a night), no weekday restriction, on the materials sector (XLB) being relatively weak vs SPY (252-day percentile of the XLB/SPY '
            'ratio level <= 0.30) combined with the communications-services sector (XLC) rallying sharply vs SPY (252-day percentile of the 10-day % '
            'change in the XLC/SPY ratio >= 0.85): BUY 6:01 pm New York, stop 1 x range, close 10:00 am New York - same mechanics as the other night '
            'trades. WATCH ITEM (93 historical Python occurrences, the biggest sample of any night trigger this project; 78 confirmed in MT4) - like '
            'Night V5/V6, this data is available from day one, no live warm-up needed')
    return dict(code='US500', name='S&P 500', symbol='US500 · Capital.com US 500', live=False, paper=True, status='Paper', version=RULES,
                unit='pts', dp=1, stats=BACKTEST, pass_bar=PASS, day_note=note,
                what_note='Tracks whether live S&P signals do as well as the v1.12 MT4 test (500109 + Night V3 + Night V4 + Night V5 + Night V6 + Night V7). Decision after about 3 months.',
                cost_note='Results are index points per trade after 0.8 points of cost (Capital.com spread + slippage).',
                net_label='Net points (v1.12 rules)')

def picks_for(day, now, jd, record=True):
    """Today's Nasdaq desk picks [(nasdaq minute, side)] (22 Oct fix). Each pick's FIRST-SEEN time is kept in the journal day (picks_seen);
    a pick first seen more than 3 minutes after its own minute is ignored (a late Nasdaq pick can no longer flip the day).
    Returns (accepted picks, note or None, stale: the picks file is older than 3 minutes in US hours)."""
    seen = jd.setdefault('picks_seen', {}); note = None; stale = False
    if record:
        p = loadj(PICKS, {})
        if p.get('day') == str(day.date()):
            for t, s in p.get('picks', []): seen.setdefault(f'{pd.Timestamp(t)}|{int(s)}', str(now))
        else: note = 'Nasdaq picks for today not written yet'
        hm = now.hour * 60 + now.minute
        if S.US_LO <= hm < S.US_HI:
            try: age = now - pd.Timestamp(p.get('at'))
            except Exception: age = None
            if p.get('day') != str(day.date()) or age is None or age > PICK_LATE:
                stale = True; note = 'Nasdaq picks file ' + ('missing' if age is None else f'{age.total_seconds() / 60:.0f} min old') + ' - Nasdaq signals may be missed'
    acc, late = [], []
    for k, fs in seen.items():
        t, s = k.rsplit('|', 1); t = pd.Timestamp(t)
        (acc if pd.Timestamp(fs) - t <= PICK_LATE else late).append((t, int(s)))
    if late: note = (note + '; ' if note else '') + f'{len(late)} late Nasdaq pick(s) ignored'
    return sorted(acc), note, stale

def legs_now(b, A, pH, pL, picks, day, day_done, jd):
    """The day's legs (22 Oct fix): legs already shown stay exactly as shown (legs_frozen: time, side, entry, stop distance), even if a
    recompute would not make them; a new leg is added only on the side of the shown legs and while there are fewer than 3."""
    fz = jd.get('legs_frozen', []); out = []; keys = set()
    for f in fz:
        t = pd.Timestamp(f['t']); j = int(b.index.searchsorted(t, side='right')) - 1
        if j < 0: continue
        out.append(dict(j=j, t=t, dir=int(f['dir']), src=int(f['src']), name=f['name'], leg=int(f['leg']), entry=float(f['entry']), sd=float(f['sd']),
                        A=float(f['sd']) / S.SM)); keys.add((str(t), int(f['dir']), f['name']))
    side = out[0]['dir'] if out else 0
    for g in S.legs_of_day(b, A, pH, pL, picks, day, day_done=day_done) if np.isfinite(A) else []:
        if (str(b.index[g['j']]), g['dir'], g['name']) in keys: continue
        if side == 0: side = g['dir']
        if g['dir'] != side or len(out) >= S.LEGS: continue
        out.append(dict(g, leg=len(out) + 1))
    return out

def freeze_legs(jd, trades):
    jd['legs_frozen'] = [dict(t=str(t['t']), dir=int(t['dir']), src=int(t['src']), name=t['name'], leg=int(t['leg']), entry=float(t['entry']), sd=float(t['sd']))
                         for t in trades if not t.get('night')]          # v1.04: the night leg is rebuilt each run from the day's stress flag

def compute(hist, b, day, now, picks, sp, jd):
    """One broker day: b = its closed bars (o h l c). Returns the managed legs (frozen ones kept)."""
    eod = day + pd.Timedelta(minutes=S.eod_minutes(day)); xt = day + pd.Timedelta(minutes=S.X_MIN)
    if not len(b):
        if jd.get('legs_frozen'): raise FeedError('no price bars for a day that already has trades')
        return []
    A, pH, pL = S.day_ctx(hist[hist.index < day].iloc[-40 * 1500:], day)
    legs = legs_now(b[['o', 'h', 'l', 'c']], A, pH, pL, picks, day, bool(now >= eod), jd)
    trades = S.manage(b[['o', 'h', 'l', 'c']], legs, A, day, sp, now_done=bool(now >= eod))
    if jd.get('stress'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod)) + trades     # v1.04 night leg (v1.07: Mon/Tue/Wed only, stop 1.0x range - gated above)
    elif jd.get('v3'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.08 Night V3: gold+WTI combo night (Wed/Thu/Fri only, gated below) -
                                            name='Night long (gold+WTI overnight shock)', src=3) + trades                 # never both: only fires when the regular stress-night leg above did NOT
    elif jd.get('v4'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.09 Night V4: weak-close + volume-spike night (gated below) -
                                            name='Night long (weak-close + volume-spike)', src=4) + trades                # never with the other two: only fires when stress AND v3 above did NOT
    elif jd.get('v5'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.10 Night V5: dollar-weak + breadth-narrow night (gated below) -
                                            name='Night long (dollar-weak + breadth-narrow)', src=5) + trades              # never with the other three: only fires when stress, V3 and V4 above did NOT
    elif jd.get('v6'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.11 Night V6: dollar-basket-weak + Europe-shock night (gated below) -
                                            name='Night long (dollar-basket-weak + Europe-shock)', src=6) + trades         # never with the other four: only fires when stress, V3, V4 and V5 above did NOT
    elif jd.get('v7'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.12 Night V7: materials-weak + communications-rally night (gated below) -
                                            name='Night long (materials-weak + communications-rally)', src=7) + trades     # never with the other five: only fires when stress, V3, V4, V5 and V6 above did NOT
    elif jd.get('v8'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.13 Night V8: credit-de-risking + industrials-weak night (gated below) -
                                            name='Night long (credit-de-risking + industrials-weak)', src=8) + trades      # never with the other six: only fires when stress, V3, V4, V5, V6 and V7 above did NOT
    elif jd.get('v9'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),                # v1.14 Night V9: duration-curve-steepening + tech-weak night (gated below) -
                                            name='Night long (duration-curve-steepening + tech-weak)', src=9) + trades     # never with the other seven: only fires when stress, V3, V4, V5, V6, V7 and V8 above did NOT
    elif jd.get('v10'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.15 Night V10: bank-loan-weak + E-mini COT net-long night (gated below) -
                                            name='Night long (bank-loan-weak + E-mini COT net-long)', src=10) + trades      # never with the other eight: only fires when stress, V3-V9 above did NOT
    elif jd.get('v12'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.16 Night V12: DJIA-COT-bullish-fast + crypto-risk-off night (gated below) -
                                            name='Night long (DJIA-COT-bullish-fast + crypto-risk-off)', src=12) + trades   # never with the other nine: only fires when stress, V3-V10 above did NOT
    elif jd.get('v13'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.17 Night V13: MSCI-EM-COT-extreme-long + communications-weak night (gated below) -
                                            name='Night long (MSCI-EM-COT-extreme-long + communications-weak)', src=13) + trades  # never with the other ten: only fires when stress, V3-V10, V12 above did NOT
    elif jd.get('v14'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.18 Night V14: Brazilian-Real-COT-bullish-fast + UST-2yr-COT-falling-fast night (gated below) -
                                            name='Night long (Brazilian-Real-COT-bullish-fast + UST-2yr-COT-falling-fast)', src=14) + trades  # never with the other eleven: only fires when stress, V3-V10, V12, V13 above did NOT
    elif jd.get('v16'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.19 Night V16: UST5yr-COT-falling-fast + credit-de-risking night (gated below) -
                                            name='Night long (UST5yr-COT-falling-fast + credit-de-risking)', src=16) + trades  # never with the other twelve: only fires when stress, V3-V10, V12-V14 above did NOT
    elif jd.get('v18'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.19 Night V18: Micro-Bitcoin-COT-slow + nat-gas-vs-WTI-divergence night (gated below) -
                                            name='Night long (Micro-Bitcoin-COT-slow + nat-gas-vs-WTI-divergence)', src=18) + trades  # never with the other thirteen: only fires when stress, V3-V10, V12-V14, V16 above did NOT
    elif jd.get('v19'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.23 Night V19: Ultra-T-Bond-COT-extreme-long + MSCI-EM-COT-extreme-long night (gated below) -
                                            name='Night long (Ultra-T-Bond-COT-extreme-long + MSCI-EM-COT-extreme-long)', src=19) + trades  # never with the other fourteen: only fires when stress, V3-V10, V12-V14, V16, V18 above did NOT
    elif jd.get('v20'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.23 Night V20: ES-asset-manager-COT-fast-bullish + staples-weak night (gated below) -
                                            name='Night long (ES-asset-manager-COT-fast-bullish + staples-weak)', src=20) + trades  # never with the other fifteen: only fires when stress, V3-V10, V12-V14, V16, V18-V19 above did NOT
    elif jd.get('v21'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.23 Night V21: VIX-other-reportables-COT-fast-long-vol + CHF-COT-fast-bearish night (gated below) -
                                            name='Night long (VIX-other-reportables-COT-fast-long-vol + CHF-COT-fast-bearish)', src=21) + trades  # never with the other sixteen: only fires when stress, V3-V10, V12-V14, V16, V18-V20 above did NOT
    elif jd.get('v22'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.23 Night V22: UST2yr-retail-COT-falling-fast + MSCI-EM-COT-falling-fast night (gated below) -
                                            name='Night long (UST2yr-retail-COT-falling-fast + MSCI-EM-COT-falling-fast)', src=22) + trades  # never with the other seventeen: only fires when stress, V3-V10, V12-V14, V16, V18-V21 above did NOT
    elif jd.get('v23'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.23 Night V23: Utilities-retail-COT-falling-fast + transports-weak night (gated below) -
                                            name='Night long (Utilities-retail-COT-falling-fast + transports-weak)', src=23) + trades  # never with the other eighteen: only fires when stress, V3-V10, V12-V14, V16, V18-V22 above did NOT
    elif jd.get('v25'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.24 Night V25: Sugar-COT-net-long + financials-weak night (gated below; V24 skipped - net-negative, not ported) -
                                            name='Night long (Sugar-COT-net-long + financials-weak)', src=25) + trades    # never with the other nineteen: only fires when stress, V3-V10, V12-V14, V16, V18-V23 above did NOT
    elif jd.get('v26'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.24 Night V26: Feeder-Cattle-COT-rising-fast + credit-de-risking night (gated below) -
                                            name='Night long (Feeder-Cattle-COT-rising-fast + credit-de-risking)', src=26) + trades  # never with the other twenty: only fires when stress, V3-V10, V12-V14, V16, V18-V23, V25 above did NOT
    elif jd.get('v27'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.24 Night V27: VIX-Legacy-commercial-COT-fast-long-vol + Dollar-Index-COT-fast-bullish night (gated below) -
                                            name='Night long (VIX-Legacy-commercial-COT-fast-long-vol + Dollar-Index-COT-fast-bullish)', src=27) + trades  # never with the other twenty-one: only fires when stress, V3-V10, V12-V14, V16, V18-V23, V25-V26 above did NOT
    elif jd.get('v28'): trades = S.night_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod),               # v1.24 Night V28: EURJPY-Legacy-noncommercial-COT-falling-fast + Bitcoin-rising-fast night (gated below) -
                                            name='Night long (EURJPY-Legacy-noncommercial-COT-falling-fast + Bitcoin-rising-fast)', src=28) + trades  # never with the other twenty-two: only fires when stress, V3-V10, V12-V14, V16, V18-V23, V25-V27 above did NOT
    if not trades and S.tom_window(day) and np.isfinite(A) and now.hour * 60 + now.minute >= S.TOM_DECIDE:
        trades = S.tom_leg(b[['o', 'h', 'l', 'c']], A, day, sp, now_done=bool(now >= eod)) + trades                        # v1.07 row20: only once no other S&P leg has fired by 17:00 broker
    for t in trades:                                     # past the close time but no bar there yet: close at the last price
        xt_ = day + pd.Timedelta(minutes=S.NIGHT_OUT) if t.get('night') else xt
        if t['status'] == 'open' and now >= xt_ + pd.Timedelta(minutes=1) and len(b):
            ex = float(b.c.values[-1]); t.update(status='eod', exit=ex, exit_t=b.index[-1], pts=t['dir'] * (ex - t['entry']) - sp)
            t['r'] = t['pts'] / t['sd']
    return trades

def finish_old_days(J, hist, day, st):
    """22 Oct fix: a journal day left non-final (the desk stopped before its close) is re-run on its stored full day and closed
    (shown legs kept, only the picks it had accepted)."""
    done = []
    for jd in J.get('days', []):
        if jd.get('final') or jd.get('rules') != RULES or jd['date'] >= str(day.date()): continue
        d = pd.Timestamp(jd['date']); nd = d + pd.Timedelta(days=1)
        if jd['date'] in st.get('holidays', []): jd['final'] = True; done.append(jd['date']); continue
        b = hist[(hist.index >= d) & (hist.index < nd)]
        if not len(b) or d < day - pd.Timedelta(days=10): continue            # not stored yet (catch-up retries) / too old to redo
        picks, _, _ = picks_for(d, nd, jd, record=False)
        sp = max([MIN_SPREAD] + [float(t.get('spread') or 0) for t in jd.get('trades', [])])
        trades = compute(hist, b, d, nd, picks, sp, jd); freeze_legs(jd, trades)
        rows = [row(t, b, nd, sp) for t in trades]
        dr = [r for r in rows if not r.get('night')]
        jd.update(trades=rows, side=(dr[0]['side'] if dr else None), final=True, finished_late=True); done.append(jd['date'])
    return done

def main(feed=None, get=None, now=None):
    global DEADLINE; DEADLINE = time.time() + 75     # 22 Oct fix: own 75 s time budget per market (no shared window)
    now = now or F.broker_now(); day = now.normalize()
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {})
    J = loadj(JOUR, dict(start=None, days=[]))
    if now.dayofweek >= 5:
        prev = mk.get('US500') or {}
        mk['US500'] = dict({k: v for k, v in prev.items() if k not in ('status', 'note')}, **base_card(), state='closed', message='Market closed for the weekend.',
                           entries=[], journal=summary(J), jdays=jdays(J), feed_error=False)
        dumpj(old, PORTAL, indent=1); print('S&P: weekend'); return
    get = get or minutes
    if feed is None:
        if not os.environ.get('CAPITAL_API_KEY'): raise RuntimeError('S&P paper needs the Capital.com prices')
        feed = F.Capital()
    st = load_state()
    try: hist = load_hist()
    except RuntimeError: seed(feed, day, get); hist = load_hist()
    added, pend = catch_up(feed, hist, day, get, now, st); save_state(st)
    if pend: raise FeedError('minute history not complete yet (' + '; '.join(pend) + ')')
    if added: hist = load_hist()
    fin = finish_old_days(J, hist, day, st)
    if fin: J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    b = get(feed, day, now); b = b[(b.index >= day) & (b.index + pd.Timedelta(minutes=1) <= now)]
    eod = day + pd.Timedelta(minutes=S.eod_minutes(day)); xt = day + pd.Timedelta(minutes=S.X_MIN)
    bad = feed_check(b, now, eod, st, 'US500'); save_state(st)
    if bad: raise FeedError(bad)                         # 22 Oct fix: an empty / stale fetch is a feed error (last good card kept), not 'no trades'
    spread = float(np.nanmedian(b.sp.values)) if len(b) and np.isfinite(b.sp.values).any() else None
    sp = max(MIN_SPREAD, spread or 0.0)
    jd = next((d for d in J['days'] if d['date'] == str(day.date())), None) or {}
    picks, pnote, pstale = picks_for(day, now, jd)
    stress, cinfo = stress_today(day, now)               # v1.04: decided once per day; only a decision made by 01:06 broker can open the night leg
    if 'stress' not in jd and stress is not None:
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        ok_day = day.dayofweek <= S.NIGHT_DOW_MAX                      # v1.07 row18: night leg only Mon/Tue/Wed
        jd['stress'] = bool(stress) and ok_time and ok_day
        if stress and not jd['stress']:
            jd['stress_note'] = ('high-fear night, but the check ran after 6:06 pm New York - no night trade' if not ok_time
                                 else 'high-fear night, but v1.07 only trades the night leg Mon/Tue/Wed - no night trade')
    if 'v3' not in jd and 'stress' in jd:                 # v1.08 Night V3: decided once per day, only once stress is already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        G = None if jd['stress'] else gw_today(day)       # don't even fetch gold/WTI on a night the stress leg already took
        fired, ginfo = S.combo_flag(G, day) if G is not None else (False, {})
        jd['v3'] = bool(fired) and ok_time and not jd['stress']
        if ginfo: jd['v3_detail'] = ginfo
        if G is None and not jd['stress'] and day.dayofweek in S.V3_DOW:
            jd['v3_note'] = 'gold/WTI data unavailable this run - no Night V3 check'
    if 'v4' not in jd and 'v3' in jd:                      # v1.09 Night V4: decided once per day, only once stress+v3 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Sdf = None if (jd['stress'] or jd['v3']) else lh_today(day, hist)
        fired, linfo = S.v4_flag(Sdf, day) if Sdf is not None else (False, {})
        jd['v4'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3']
        if linfo: jd['v4_detail'] = linfo
        if Sdf is None and not jd['stress'] and not jd['v3']:
            jd['v4_note'] = 'no Night V4 check (volume history still warming up, or data unavailable)'
    if 'v5' not in jd and 'v4' in jd:                       # v1.10 Night V5: decided once per day, only once stress+v3+v4 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Xdf = None if (jd['stress'] or jd['v3'] or jd['v4']) else dxyrs_today(day)
        fired, xinfo = S.v5_flag(Xdf, day) if Xdf is not None else (False, {})
        jd['v5'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4']
        if xinfo: jd['v5_detail'] = xinfo
        if Xdf is None and not jd['stress'] and not jd['v3'] and not jd['v4']:
            jd['v5_note'] = 'dollar/breadth data unavailable this run - no Night V5 check'
    if 'v6' not in jd and 'v5' in jd:                       # v1.11 Night V6: decided once per day, only once stress+v3+v4+v5 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Ydf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5']) else dtwexstoxx_today(day)
        fired, yinfo = S.v6_flag(Ydf, day) if Ydf is not None else (False, {})
        jd['v6'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5']
        if yinfo: jd['v6_detail'] = yinfo
        if Ydf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5']:
            jd['v6_note'] = 'broad-dollar/STOXX data unavailable this run - no Night V6 check'
    if 'v7' not in jd and 'v6' in jd:                       # v1.12 Night V7: decided once per day, only once stress+v3+v4+v5+v6 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Zdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6']) else mt_cm_today(day)
        fired, zinfo = S.v7_flag(Zdf, day) if Zdf is not None else (False, {})
        jd['v7'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6']
        if zinfo: jd['v7_detail'] = zinfo
        if Zdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6']:
            jd['v7_note'] = 'materials/communications data unavailable this run - no Night V7 check'
    if 'v8' not in jd and 'v7' in jd:                       # v1.13 Night V8: decided once per day, only once stress+v3+v4+v5+v6+v7 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Wdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7']) else cq_in_today(day)
        fired, winfo = S.v8_flag(Wdf, day) if Wdf is not None else (False, {})
        jd['v8'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7']
        if winfo: jd['v8_detail'] = winfo
        if Wdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7']:
            jd['v8_note'] = 'credit/industrials data unavailable this run - no Night V8 check'
    if 'v9' not in jd and 'v8' in jd:                       # v1.14 Night V9: decided once per day, only once stress+v3+v4+v5+v6+v7+v8 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Tdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8']) else du_tk_today(day)
        fired, tinfo = S.v9_flag(Tdf, day) if Tdf is not None else (False, {})
        jd['v9'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8']
        if tinfo: jd['v9_detail'] = tinfo
        if Tdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8']:
            jd['v9_note'] = 'duration/tech data unavailable this run - no Night V9 check'
    if 'v10' not in jd and 'v9' in jd:                      # v1.15 Night V10: decided once per day, only once stress+v3+v4+v5+v6+v7+v8+v9 are already known (mutual exclusion)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Ydf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9']) else bk_es_today(day)
        fired, yinfo = S.v10_flag(Ydf, day) if Ydf is not None else (False, {})
        jd['v10'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9']
        if yinfo: jd['v10_detail'] = yinfo
        if Ydf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9']:
            jd['v10_note'] = 'bank-loan/COT data unavailable this run - no Night V10 check'
    if 'v12' not in jd and 'v10' in jd:                     # v1.16 Night V12: decided once per day, only once stress+v3-v10 are already known (mutual exclusion; row47-49 "V11" was never ported here - confirmed but parked)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Qdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10']) else djia_cr_today(day)
        fired, qinfo = S.v12_flag(Qdf, day) if Qdf is not None else (False, {})
        jd['v12'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10']
        if qinfo: jd['v12_detail'] = qinfo
        if Qdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10']:
            jd['v12_note'] = 'DJIA COT/crypto data unavailable this run - no Night V12 check'
    if 'v13' not in jd and 'v12' in jd:                     # v1.17 Night V13: decided once per day, only once stress+v3-v10+v12 are already known (mutual exclusion; row47-49 "V11" was never ported here - confirmed but parked)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Rdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12']) else msciem_cm_today(day)
        fired, rinfo = S.v13_flag(Rdf, day) if Rdf is not None else (False, {})
        jd['v13'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12']
        if rinfo: jd['v13_detail'] = rinfo
        if Rdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12']:
            jd['v13_note'] = 'MSCI-EM COT/communications data unavailable this run - no Night V13 check'
    if 'v14' not in jd and 'v13' in jd:                     # v1.18 Night V14: decided once per day, only once stress+v3-v10+v12+v13 are already known (mutual exclusion; row47-49 "V11" was never ported here - confirmed but parked)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Tdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13']) else brlfx_ust2y_today(day)
        fired, tinfo = S.v14_flag(Tdf, day) if Tdf is not None else (False, {})
        jd['v14'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13']
        if tinfo: jd['v14_detail'] = tinfo
        if Tdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13']:
            jd['v14_note'] = 'Brazilian-Real/UST-2yr COT data unavailable this run - no Night V14 check'
    if 'v16' not in jd and 'v14' in jd:                     # v1.19 Night V16: decided once per day, only once stress+v3-v10+v12-v14 are already known (mutual exclusion; row47-49 "V11" and rows65-67 "V17" never ported here - confirmed but parked)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Udf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14']) else ust5y_cq_today(day)
        fired, uinfo = S.v16_flag(Udf, day) if Udf is not None else (False, {})
        jd['v16'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14']
        if uinfo: jd['v16_detail'] = uinfo
        if Udf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14']:
            jd['v16_note'] = 'UST-5yr-Note COT/credit data unavailable this run - no Night V16 check'
    if 'v18' not in jd and 'v16' in jd:                     # v1.19 Night V18: decided once per day, only once stress+v3-v10+v12-v14+v16 are already known (mutual exclusion; row47-49 "V11" and rows65-67 "V17" never ported here - confirmed but parked)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Mdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16']) else mbtc_ng_today(day)
        fired, minfo = S.v18_flag(Mdf, day) if Mdf is not None else (False, {})
        jd['v18'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16']
        if minfo: jd['v18_detail'] = minfo
        if Mdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16']:
            jd['v18_note'] = 'Micro-Bitcoin COT/natural-gas data unavailable this run - no Night V18 check'
    if 'v19' not in jd and 'v18' in jd:                     # v1.23 Night V19: decided once per day, only once stress+v3-v10+v12-v14+v16+v18 are already known (mutual exclusion; row47-49 "V11" and rows65-67 "V17" never ported here - confirmed but parked)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Udf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18']) else ultbond_msciem_today(day)
        fired, uinfo = S.v19_flag(Udf, day) if Udf is not None else (False, {})
        jd['v19'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18']
        if uinfo: jd['v19_detail'] = uinfo
        if Udf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18']:
            jd['v19_note'] = 'Ultra-T-Bond/MSCI-EM COT data unavailable this run - no Night V19 check'
    if 'v20' not in jd and 'v19' in jd:                     # v1.23 Night V20: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v19 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Edf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19']) else es_am_cp_today(day)
        fired, einfo = S.v20_flag(Edf, day) if Edf is not None else (False, {})
        jd['v20'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19']
        if einfo: jd['v20_detail'] = einfo
        if Edf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19']:
            jd['v20_note'] = 'S&P-asset-manager-COT/staples data unavailable this run - no Night V20 check'
    if 'v21' not in jd and 'v20' in jd:                     # v1.23 Night V21: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v20 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Xdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20']) else vixfoth_chffx_today(day)
        fired, xinfo = S.v21_flag(Xdf, day) if Xdf is not None else (False, {})
        jd['v21'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20']
        if xinfo: jd['v21_detail'] = xinfo
        if Xdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20']:
            jd['v21_note'] = 'VIX-other-reportables/Swiss-Franc COT data unavailable this run - no Night V21 check'
    if 'v22' not in jd and 'v21' in jd:                     # v1.23 Night V22: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v21 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Ydf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20'] or jd['v21']) else ust2ynr_msciemchg_today(day)
        fired, yinfo = S.v22_flag(Ydf, day) if Ydf is not None else (False, {})
        jd['v22'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21']
        if yinfo: jd['v22_detail'] = yinfo
        if Ydf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21']:
            jd['v22_note'] = 'UST2yr-retail/MSCI-EM-shift COT data unavailable this run - no Night V22 check'
    if 'v23' not in jd and 'v22' in jd:                     # v1.23 Night V23: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v22 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Zdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20'] or jd['v21'] or jd['v22']) else uti2nr_tr_today(day)
        fired, zinfo = S.v23_flag(Zdf, day) if Zdf is not None else (False, {})
        jd['v23'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22']
        if zinfo: jd['v23_detail'] = zinfo
        if Zdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22']:
            jd['v23_note'] = 'Utilities-retail-COT/transports data unavailable this run - no Night V23 check'
    # v1.24: Night V24 (gold-Swap-Dealer + eurfx-Asset-Mgr) was built, MT4-tested, and FOUND NET-NEGATIVE vs
    # Control (-$51.93 over 32 trades, 9 Nov) - deliberately NOT ported here. V25-V28 (tested net-positive)
    # pick up the v22/v23 chain directly, so V24's slot in the mutual-exclusion ordering is simply skipped.
    if 'v25' not in jd and 'v23' in jd:                     # v1.24 Night V25: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v23 are already known (V24 skipped - net-negative, not ported)
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Sdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20'] or jd['v21'] or jd['v22'] or jd['v23']) else sgoth_fy_today(day)
        fired, sinfo = S.v25_flag(Sdf, day) if Sdf is not None else (False, {})
        jd['v25'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23']
        if sinfo: jd['v25_detail'] = sinfo
        if Sdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23']:
            jd['v25_note'] = 'Sugar-COT/financials data unavailable this run - no Night V25 check'
    if 'v26' not in jd and 'v25' in jd:                     # v1.24 Night V26: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v23+v25 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Fdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20'] or jd['v21'] or jd['v22'] or jd['v23'] or jd['v25']) else fcsw_cq_today(day)
        fired, finfo = S.v26_flag(Fdf, day) if Fdf is not None else (False, {})
        jd['v26'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23'] and not jd['v25']
        if finfo: jd['v26_detail'] = finfo
        if Fdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23'] and not jd['v25']:
            jd['v26_note'] = 'Feeder-cattle-COT/credit data unavailable this run - no Night V26 check'
    if 'v27' not in jd and 'v26' in jd:                     # v1.24 Night V27: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v23+v25-v26 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Ldf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20'] or jd['v21'] or jd['v22'] or jd['v23'] or jd['v25'] or jd['v26']) else vixlcomm_dxyfnr_today(day)
        fired, linfo = S.v27_flag(Ldf, day) if Ldf is not None else (False, {})
        jd['v27'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23'] and not jd['v25'] and not jd['v26']
        if linfo: jd['v27_detail'] = linfo
        if Ldf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23'] and not jd['v25'] and not jd['v26']:
            jd['v27_note'] = 'VIX-Legacy-commercial-COT/Dollar-Index-COT data unavailable this run - no Night V27 check'
    if 'v28' not in jd and 'v27' in jd:                     # v1.24 Night V28: decided once per day, only once stress+v3-v10+v12-v14+v16+v18-v23+v25-v27 are already known
        ok_time = now.hour * 60 + now.minute <= S.NIGHT_IN + 5
        Jdf = None if (jd['stress'] or jd['v3'] or jd['v4'] or jd['v5'] or jd['v6'] or jd['v7'] or jd['v8'] or jd['v9'] or jd['v10'] or jd['v12'] or jd['v13'] or jd['v14'] or jd['v16'] or jd['v18'] or jd['v19'] or jd['v20'] or jd['v21'] or jd['v22'] or jd['v23'] or jd['v25'] or jd['v26'] or jd['v27']) else eurjpyncomm_bt_today(day)
        fired, jinfo = S.v28_flag(Jdf, day) if Jdf is not None else (False, {})
        jd['v28'] = bool(fired) and ok_time and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23'] and not jd['v25'] and not jd['v26'] and not jd['v27']
        if jinfo: jd['v28_detail'] = jinfo
        if Jdf is None and not jd['stress'] and not jd['v3'] and not jd['v4'] and not jd['v5'] and not jd['v6'] and not jd['v7'] and not jd['v8'] and not jd['v9'] and not jd['v10'] and not jd['v12'] and not jd['v13'] and not jd['v14'] and not jd['v16'] and not jd['v18'] and not jd['v19'] and not jd['v20'] and not jd['v21'] and not jd['v22'] and not jd['v23'] and not jd['v25'] and not jd['v26'] and not jd['v27']:
            jd['v28_note'] = 'EURJPY-Legacy-noncommercial-COT/Bitcoin data unavailable this run - no Night V28 check'
    trades = compute(hist, b, day, now, picks, sp, jd)
    freeze_legs(jd, trades)
    rows = [row(t, b, now, sp) for t in trades]; drows = [r for r in rows if not r.get('night')]; nrow = [r for r in rows if r.get('night')]
    last = float(b.c.iloc[-1]) if len(b) else None; first = float(b.o.iloc[0]) if len(b) else None
    spark = []
    if len(b):
        g5 = b[['o', 'h', 'l', 'c']].resample('5min').agg({'o': 'first', 'h': 'max', 'l': 'min', 'c': 'last'}).dropna()
        spark = [[F.broker_to_dubai(t).strftime('%-I:%M %p').lower(), round(float(r.c), 1), round(float(r.o), 1), round(float(r.h), 1), round(float(r.l), 1)] for t, r in g5.iterrows()]
    if J.get('start') is None: J['start'] = str(day.date())
    J['days'] = sorted([d for d in J['days'] if d['date'] != str(day.date())] +
                       [dict({k: jd[k] for k in ('picks_seen', 'legs_frozen', 'stress', 'stress_note', 'v3', 'v3_note', 'v3_detail', 'v4', 'v4_note', 'v4_detail', 'v5', 'v5_note', 'v5_detail', 'v6', 'v6_note', 'v6_detail', 'v7', 'v7_note', 'v7_detail', 'v8', 'v8_note', 'v8_detail', 'v9', 'v9_note', 'v9_detail', 'v10', 'v10_note', 'v10_detail', 'v12', 'v12_note', 'v12_detail', 'v13', 'v13_note', 'v13_detail', 'v14', 'v14_note', 'v14_detail', 'v16', 'v16_note', 'v16_detail', 'v18', 'v18_note', 'v18_detail', 'v19', 'v19_note', 'v19_detail', 'v20', 'v20_note', 'v20_detail', 'v21', 'v21_note', 'v21_detail', 'v22', 'v22_note', 'v22_detail', 'v23', 'v23_note', 'v23_detail') if k in jd}, date=str(day.date()), rules=RULES,
                             label=day.strftime('%a %d %b'), side=(drows[0]['side'] if drows else None), trades=rows, final=bool(now >= eod))],
                      key=lambda d: d['date'])
    J['summary'] = summary(J, day); dumpj(J, JOUR, indent=1)
    A = trades[0]['A'] if trades else S.day_ctx(hist[hist.index < day].iloc[-40 * 1500:], day)[0]
    if drows:
        op = [r for r in drows if r['status'] == 'open']; state = drows[0]['side'].lower()
        msg = (f"PAPER {drows[0]['side']} day: {len(drows)} trade{'s' if len(drows) > 1 else ''} today ({len(op)} running). Only {drows[0]['side']} signals count "
               f"today (max 3; no 2nd/3rd trade from 11:00 am New York or once the day is up half a stop). Each trade keeps its stop, no half-close; everything "
               f"closes at {dubai(xt)} Dubai (3:30 pm New York).")
    elif now >= xt: state, msg = 'none', 'No paper day trade today.'
    else: state, msg = 'waiting', (f'Waiting for the first day signal (from {dubai(day + pd.Timedelta(minutes=16 * 60 + 40))} Dubai: 9:40 am New York move, '
                                   'Nasdaq signals; earlier: yesterday high/low sweep).')
    if nrow:                                             # v1.04 night leg (v1.08: or Night V3 - jd['v3']; v1.09: or Night V4 - jd['v4']; v1.10: or Night V5 - jd['v5']; v1.11: or Night V6 - jd['v6']; v1.12: or Night V7 - jd['v7']; v1.13: or Night V8 - jd['v8']; v1.14: or Night V9 - jd['v9']; v1.15: or Night V10 - jd['v10']; v1.16: or Night V12 - jd['v12']; v1.17: or Night V13 - jd['v13']; v1.18: or Night V14 - jd['v14']; v1.19: or Night V16 - jd['v16']; or Night V18 - jd['v18'])
        n_ = nrow[0]; label = ('EURJPY-Legacy-noncommercial-COT-falling-fast + Bitcoin-rising-fast' if jd.get('v28') else ('VIX-Legacy-commercial-COT-fast-long-vol + Dollar-Index-COT-fast-bullish' if jd.get('v27') else ('Feeder-Cattle-COT-rising-fast + credit-de-risking' if jd.get('v26') else ('Sugar-COT-net-long + financials-weak' if jd.get('v25') else ('Utilities-retail-COT-falling-fast + transports-weak' if jd.get('v23') else ('UST2yr-retail-COT-falling-fast + MSCI-EM-COT-falling-fast' if jd.get('v22') else ('VIX-other-reportables-COT-fast-long-vol + CHF-COT-fast-bearish' if jd.get('v21') else ('ES-asset-manager-COT-fast-bullish + staples-weak' if jd.get('v20') else ('Ultra-T-Bond-COT-extreme-long + MSCI-EM-COT-extreme-long' if jd.get('v19') else ('Micro-Bitcoin-COT-slow + nat-gas-vs-WTI-divergence' if jd.get('v18') else ('UST5yr-COT-falling-fast + credit-de-risking' if jd.get('v16') else ('Brazilian-Real-COT-bullish-fast + UST-2yr-COT-falling-fast' if jd.get('v14') else ('MSCI-EM-COT-extreme-long + communications-weak' if jd.get('v13') else ('DJIA-COT-bullish-fast + crypto-risk-off' if jd.get('v12') else ('bank-loan-weak + E-mini COT net-long' if jd.get('v10') else ('duration-curve-steepening + tech-weak' if jd.get('v9') else ('credit-de-risking + industrials-weak' if jd.get('v8') else ('materials-weak + communications-rally' if jd.get('v7') else ('dollar-basket-weak + Europe-shock' if jd.get('v6') else ('dollar-weak + breadth-narrow' if jd.get('v5') else ('weak-close + volume-spike' if jd.get('v4') else ('gold+WTI shock' if jd.get('v3') else 'high-fear night'))))))))))))))))))))))
        msg = (f"NIGHT BUY ({label}) at {n_['time']} Dubai, stop {n_['stop']}, " +
               (f"closes at {dubai(day + pd.Timedelta(minutes=S.NIGHT_OUT))} Dubai (10:00 am New York). " if n_['status'] == 'open' else f"closed ({n_['status']}). ") + msg)
        if state in ('none', 'waiting') and n_['status'] == 'open': state = 'buy'
    elif jd.get('stress_note'): msg += ' (' + jd['stress_note'] + '.)'
    elif jd.get('stress') is False and jd.get('v3') is False and jd.get('v4') is False and jd.get('v5') is False and jd.get('v6') is False and jd.get('v7') is False and jd.get('v8') is False and jd.get('v9') is False and jd.get('v10') is False and jd.get('v12') is False and jd.get('v13') is False and jd.get('v14') is False and jd.get('v16') is False and jd.get('v18') is False and jd.get('v19') is False and jd.get('v20') is False and jd.get('v21') is False and jd.get('v22') is False and jd.get('v23') is False and jd.get('v25') is False and jd.get('v26') is False and jd.get('v27') is False and jd.get('v28') is False: msg += ' No night trade today (not a high-fear night, no gold+WTI shock, no weak-close + volume spike, no dollar-weak + breadth-narrow, no dollar-basket-weak + Europe-shock, no materials-weak + communications-rally, no credit-de-risking + industrials-weak, no duration-curve-steepening + tech-weak, no bank-loan-weak + E-mini COT net-long, no DJIA-COT-bullish-fast + crypto-risk-off, no MSCI-EM-COT-extreme-long + communications-weak, no Brazilian-Real-COT-bullish-fast + UST-2yr-COT-falling-fast, no UST5yr-COT-falling-fast + credit-de-risking, no Micro-Bitcoin-COT-slow + nat-gas-vs-WTI-divergence, no Ultra-T-Bond-COT-extreme-long + MSCI-EM-COT-extreme-long, no ES-asset-manager-COT-fast-bullish + staples-weak, no VIX-other-reportables-COT-fast-long-vol + CHF-COT-fast-bearish, no UST2yr-retail-COT-falling-fast + MSCI-EM-COT-falling-fast, no Utilities-retail-COT-falling-fast + transports-weak, no Sugar-COT-net-long + financials-weak, no Feeder-Cattle-COT-rising-fast + credit-de-risking, no VIX-Legacy-commercial-COT-fast-long-vol + Dollar-Index-COT-fast-bullish, no EURJPY-Legacy-noncommercial-COT-falling-fast + Bitcoin-rising-fast).'
    elif jd.get('v3_note'): msg += ' (' + jd['v3_note'] + '.)'
    elif jd.get('v4_note'): msg += ' (' + jd['v4_note'] + '.)'
    elif jd.get('v5_note'): msg += ' (' + jd['v5_note'] + '.)'
    elif jd.get('v6_note'): msg += ' (' + jd['v6_note'] + '.)'
    elif jd.get('v7_note'): msg += ' (' + jd['v7_note'] + '.)'
    elif jd.get('v8_note'): msg += ' (' + jd['v8_note'] + '.)'
    elif jd.get('v9_note'): msg += ' (' + jd['v9_note'] + '.)'
    elif jd.get('v10_note'): msg += ' (' + jd['v10_note'] + '.)'
    elif jd.get('v12_note'): msg += ' (' + jd['v12_note'] + '.)'
    elif jd.get('v13_note'): msg += ' (' + jd['v13_note'] + '.)'
    elif jd.get('v14_note'): msg += ' (' + jd['v14_note'] + '.)'
    elif jd.get('v16_note'): msg += ' (' + jd['v16_note'] + '.)'
    elif jd.get('v18_note'): msg += ' (' + jd['v18_note'] + '.)'
    elif jd.get('v19_note'): msg += ' (' + jd['v19_note'] + '.)'
    elif jd.get('v20_note'): msg += ' (' + jd['v20_note'] + '.)'
    elif jd.get('v21_note'): msg += ' (' + jd['v21_note'] + '.)'
    elif jd.get('v22_note'): msg += ' (' + jd['v22_note'] + '.)'
    elif jd.get('v23_note'): msg += ' (' + jd['v23_note'] + '.)'
    elif jd.get('v25_note'): msg += ' (' + jd['v25_note'] + '.)'
    elif jd.get('v26_note'): msg += ' (' + jd['v26_note'] + '.)'
    elif jd.get('v27_note'): msg += ' (' + jd['v27_note'] + '.)'
    elif jd.get('v28_note'): msg += ' (' + jd['v28_note'] + '.)'
    elif stress is None: msg += f" (Night-trade check: Cboe data not available - {cinfo.get('error', '')}.)"
    if pnote and now.hour * 60 + now.minute >= S.US_LO: msg += f' ({pnote}.)'
    mk['US500'] = dict(base_card(A if A == A else None), state=state, message=msg, price=last, change=(None if last is None or first is None else round(last - first, 1)),
                       entries=rows, spark=spark, journal=J['summary'], jdays=jdays(J), feed_error=False, picks_stale=pstale, epic=EPIC_NOW[0], close_at=dubai(xt),
                       history_note=f"history to {hist.index[-1].date()} ({hist.index.normalize().nunique()} days)" + (f" · added {', '.join(added)}" if added else '')
                       + (f" · finished {', '.join(fin)}" if fin else ''))
    dumpj(old, PORTAL, indent=1)
    print(f'S&P paper: {now} broker | bars {len(b)} | picks {len(picks)} | legs {len(rows)} | history to {hist.index[-1].date()} | added {added} | finished {fin}')

def fail(e):
    """Keep the last good S&P card and say what failed."""
    old = loadj(PORTAL, {}); mk = old.setdefault('markets', {}); c = mk.get('US500') or {}
    c.update(base_card()); c.setdefault('entries', []); c.setdefault('state', 'waiting'); c['feed_error'] = True
    c['message'] = f"S&P paper update failed at {F.broker_to_dubai(F.broker_now()).strftime('%-I:%M %p').lower()} Dubai ({type(e).__name__}: {str(e)[:120]}) — shows the last good update; retries every minute."
    mk['US500'] = c; dumpj(old, PORTAL, indent=1)
