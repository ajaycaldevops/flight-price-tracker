Check if the Amadeus flight API is reachable, measure response time, and flag if it is slow or down.

Run the health check script:

```!
python .claude/skills/api-health-check/health_check.py
```

After the output above, summarize the result clearly:

- **UP**: State the response time and that the API is healthy.
- **SLOW**: State the response time, flag it as WARNING (1.5–3s) or CRITICAL (>3s), and suggest checking https://developers.amadeus.com for outages.
- **DOWN**: State the error and the suggested cause from the script output.

## Thresholds

| Response time | Status |
|---|---|
| < 1.5s | OK |
| 1.5s – 3.0s | WARNING — slightly slow |
| > 3.0s | CRITICAL — likely degraded |
| Exception | DOWN |

## Common failure causes

- **401 / auth error** — wrong `AMADEUS_CLIENT_ID` or `AMADEUS_CLIENT_SECRET` in `.env`
- **403 forbidden** — credentials scoped to `test` but `AMADEUS_HOSTNAME=production` (or vice versa)
- **429 rate limited** — sandbox quota hit; wait ~1 minute
- **Network / timeout** — no internet or Amadeus is down
- **No error but empty results** — API is healthy; `AMADEUS_HOSTNAME=test` (sandbox) has limited routes
