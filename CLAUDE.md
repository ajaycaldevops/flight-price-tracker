# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the App

```powershell
cd flight_tracker
python -m pip install -r requirements.txt
python run.py
# App runs at http://localhost:5000
```

`pip` alone is not recognized on this machine — always use `python -m pip`.

To manually trigger a price check without waiting for the schedule, visit `/searches` and click **"Run Price Check Now"**.

## Environment

All secrets live in `.env` (never commit this). Copy `.env.example` to create one. Required keys:
- `AMADEUS_CLIENT_ID` / `AMADEUS_CLIENT_SECRET` — from developers.amadeus.com
- `AMADEUS_HOSTNAME` — `test` for sandbox, `production` for live data
- `SMTP_EMAIL` / `SMTP_PASSWORD` — Gmail address + 16-char App Password (not the account password)

## Architecture

The app is a Flask web app with a background scheduler. All modules import from each other within a Flask app context.

**Request flow (form submission):**
1. `app.py` validates form → saves `SearchPreference` to SQLite → calls `send_confirmation_email` → calls `run_price_checks` immediately for instant results → redirects to `/success`

**Scheduled flow (7am & 8pm PT daily):**
1. `scheduler.py` (`APScheduler` with `America/Los_Angeles` timezone) calls `run_price_checks(app)`
2. `run_price_checks` queries all active, non-expired `SearchPreference` rows
3. For each: calls `flight_search.search_flights(pref)` → calls `email_service.send_flight_alert(pref, flights)`
4. Also deactivates expired searches in the same run

**Key design constraints:**
- `scheduler.py` imports `models`, `flight_search`, and `email_service` lazily (inside `run_price_checks`) to avoid circular imports at module load time
- The `enumerate` built-in is registered as a Jinja2 filter in `create_app()` so `email.html` can use `{% for rank, f in flights | enumerate(1) %}`
- `AMADEUS_HOSTNAME=test` (sandbox) has limited route/date coverage — flights may return empty for many routes. Switch to `production` after Amadeus approval for real data.

**Flight search logic (`flight_search.py`):**
- Iterates every date in `departure_date_from`..`departure_date_to`, querying Amadeus separately per date (API doesn't support date ranges natively)
- After collecting all offers, optionally filters by `departure_time_from`/`departure_time_to`; if filtering removes all results, falls back to unfiltered
- Returns top 3 by `grandTotal` price
- Booking links are constructed as Kayak deep links, Google Flights links, and direct airline website URLs (see `_get_airline_website`)

**Database:** SQLite at `instance/flight_tracker.db` (auto-created by Flask-SQLAlchemy). Single table: `search_preferences`. No migrations setup — schema changes require dropping and recreating the DB.

**Email templates** (`templates/email.html`, `templates/confirmation_email.html`) are rendered via Jinja2 in `email_service.py` using a standalone `Environment` (not the Flask one), then sent via Gmail SMTP with `starttls`.
