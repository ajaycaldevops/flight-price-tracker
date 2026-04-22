# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```powershell
cd flight_tracker
python -m pip install -r requirements.txt
python run.py
# App runs at http://localhost:5000
```

`run.py` is the entry point — it calls `create_app()` and starts Flask on `0.0.0.0:5000`. Running `app.py` directly also works but skips the startup banner. Always use `python -m pip` — bare `pip` is not recognized on this machine.

**After any schema change:** stop the app, delete `instance/flight_tracker.db`, restart. Flask-SQLAlchemy's `create_all()` only creates missing tables — it never alters existing ones.

To manually trigger a price check, visit `/searches` → "Run Price Check Now".
To diagnose SMTP issues, visit `/test-email` (sends a plain-text email and prints each step). Pass `?to=someone@example.com` to send to a different address than `SMTP_EMAIL`.

## Environment

All secrets live in `.env` (never commit). Required keys:
- `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` — from developers.amadeus.com
- `AMADEUS_HOSTNAME` — `test` for sandbox, `production` for live data
- `SMTP_EMAIL` / `SMTP_PASSWORD` — Gmail address + 16-char App Password (not the account password)

## Architecture

Flask web app + APScheduler background scheduler. All business logic runs inside a Flask app context.

**Form submission flow:**
`app.py` validates → saves `SearchPreference` to SQLite → `send_confirmation_email` → `run_price_checks(app)` (no `force` arg, but `last_best_price` is `None` on a brand-new record so `first_run=True` and the alert always sends) → redirect to `/success`

**Scheduled flow (7:00 AM & 8:00 PM PT daily):**
`scheduler.py` (APScheduler, `America/Los_Angeles`) → `run_price_checks(app, force=False)` → for each active non-expired `SearchPreference`: `search_flights(pref)` → compare best price against `last_best_price` → `send_flight_alert` only if price dropped (or first run). Same run deactivates expired searches.

**Gotcha — timezone label mismatch in `scheduler.py`:** The `BackgroundScheduler` timezone is `America/Los_Angeles` (PT), which is correct. The job name strings inside `start_scheduler` incorrectly say "ET" — ignore them. The schedule fires at 7:00 AM and 8:00 PM Pacific.

**Key constraints:**
- `scheduler.py` imports `models`, `flight_search`, and `email_service` lazily inside `run_price_checks` to avoid circular imports at module load time.
- `enumerate` is registered as a Jinja2 filter in **two** places: `create_app()` for Flask's env (used by web templates) and `_get_jinja_env()` in `email_service.py` for its standalone env (used by email templates). Both are required — missing either causes `TemplateAssertionError: No filter named 'enumerate'`.
- `AMADEUS_HOSTNAME=test` (sandbox) returns limited routes/dates. Many searches return empty results in sandbox — switch to `production` for real data.

**Flight search (`flight_search.py`):**
- Builds all `(departure_date, return_date)` pairs from the date ranges; capped at 20 API calls total (sampled evenly if exceeded).
- `departure_date_to` and `return_date_to` are optional in the form — `app.py` defaults them to the `_from` value before saving, so `search_flights` always receives a valid range.
- Each Amadeus call uses `returnDate` param for round trips; response has `itineraries[0]` (outbound) and `itineraries[1]` (return).
- Post-fetch filters applied in order: departure time window (falls back to unfiltered if nothing matches), then `max_stops` (checked per leg via `_max_stops_for_flight`).
- Returns top 3 sorted by `grandTotal` price. Booking links: Kayak deep link (includes return date for round trips), Google Flights, and `_get_airline_website` lookup.
- Airport autocomplete is served by the `/api/airport-search?q=<query>` endpoint (AJAX, wired to the origin/destination inputs on the form). Backed by `search_airport()` in `flight_search.py`.

**`SearchPreference` model fields of note:**
- `departure_date_to`, `return_date_from/to`, `departure_time_from/to` — all nullable; absence means single-date or one-way or any-time search.
- `num_passengers` — Integer (1–9); `checked_bags_per_passenger` — Integer (0–5). Both are passed to the Amadeus API and affect results.
- `max_stops` — nullable Integer; `None` = no stops filter, `0` = nonstop only.
- `expires_at` — set to `created_at + tracking_days`; scheduler deactivates rows where `expires_at < now`.
- `last_best_price` — nullable Float; `None` = never alerted yet (first run always sends). Scheduler only emails on subsequent runs if the new best price is lower.

**Price-drop alert logic (`scheduler.py`):**
- `run_price_checks(app, force=False)` — scheduled runs use `force=False` (price-drop only); the `/run-now` manual trigger passes `force=True` to always send regardless of price history.
- After sending an alert, `last_best_price` is updated and committed so the next scheduled run has a baseline to compare against.

**Flight offer deduplication (`flight_search.py`):**
- After all Amadeus API calls, offers are deduplicated by Amadeus offer `id` before parsing. Prevents the same offer appearing multiple times in top-3 when it shows up across multiple date-pair queries.

**Email templates** (`email.html`, `confirmation_email.html`) are rendered by a standalone Jinja2 `Environment` in `email_service.py` (not Flask's env). Template dir resolved with `os.path.abspath(__file__)` to avoid working-directory issues. Sent via Gmail SMTP port 587 with STARTTLS.
