---
name: api-health-check
description: Check if the Amadeus flight API is reachable, measure response time, and flag if it is slow or down. Run this before debugging empty search results or when the scheduler silently produces no alerts.
disable-model-invocation: true
allowed-tools: Bash(python *)
---

## Amadeus API Health Check

Running health check — this may take a few seconds while the OAuth token is exchanged...

```!
python .claude/skills/api-health-check/health_check.py
```

---

## What to report

After the script output above, summarize the result in one of these forms:

**Healthy:**
> Amadeus API is UP. Response time: Xs (OK). Environment: test/production.

**Slow:**
> Amadeus API is SLOW. Response time: Xs (WARNING/CRITICAL). Consider retrying or checking https://developers.amadeus.com for outage notices.

**Down:**
> Amadeus API is DOWN. Error: <error message>. Suggested fix: <cause line from script output>.

## Thresholds

| Response time | Status |
|---|---|
| < 1.5s | OK |
| 1.5s – 3.0s | WARNING — slightly slow |
| > 3.0s | CRITICAL — likely degraded |
| Exception | DOWN |

## Common causes of failure

- **401 / auth error** — wrong `AMADEUS_CLIENT_ID` or `AMADEUS_CLIENT_SECRET` in `.env`
- **403 forbidden** — credentials created for `test` but `AMADEUS_HOSTNAME=production` (or vice versa)
- **429 rate limited** — too many calls; sandbox quota is low, wait ~1 minute
- **Network error / timeout** — no internet, or Amadeus itself is down; check https://developers.amadeus.com
- **Empty results (but no error)** — API is healthy but `AMADEUS_HOSTNAME=test` (sandbox) has limited routes; switch to `production` for real data
