import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

from config import Config
from models import db, SearchPreference
from flight_search import search_airport
from email_service import send_confirmation_email
from scheduler import start_scheduler, run_price_checks

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Jinja2 filter so email template can use {{ flights | enumerate(1) }}
    app.jinja_env.filters["enumerate"] = enumerate

    # Start background scheduler (7am & 8pm price checks)
    start_scheduler(app)

    # ── Routes ─────────────────────────────────────────────────────────────

    @app.route("/", methods=["GET", "POST"])
    def index():
        if request.method == "POST":
            errors = []

            origin = request.form.get("origin", "").strip().upper()
            destination = request.form.get("destination", "").strip().upper()
            departure_date_from = request.form.get("departure_date_from", "").strip()
            departure_date_to = request.form.get("departure_date_to", "").strip()
            departure_time_from = request.form.get("departure_time_from", "").strip() or None
            departure_time_to = request.form.get("departure_time_to", "").strip() or None
            return_date_from = request.form.get("return_date_from", "").strip() or None
            return_date_to = request.form.get("return_date_to", "").strip() or None
            max_stops_raw = request.form.get("max_stops", "").strip()
            email = request.form.get("email", "").strip()
            tracking_days = request.form.get("tracking_days", "7").strip()

            try:
                num_passengers = int(request.form.get("num_passengers", 1))
            except ValueError:
                num_passengers = 1

            try:
                checked_bags = int(request.form.get("checked_bags_per_passenger", 0))
            except ValueError:
                checked_bags = 0

            try:
                tracking_days = int(tracking_days)
            except ValueError:
                tracking_days = 7

            max_stops = int(max_stops_raw) if max_stops_raw != "" else None

            # Latest dates default to earliest if left blank
            if not departure_date_to:
                departure_date_to = departure_date_from
            if return_date_from and not return_date_to:
                return_date_to = return_date_from

            # Basic validation
            if not origin or len(origin) != 3:
                errors.append("Origin must be a 3-letter IATA airport code (e.g. JFK).")
            if not destination or len(destination) != 3:
                errors.append("Destination must be a 3-letter IATA airport code (e.g. LAX).")
            if origin == destination:
                errors.append("Origin and destination cannot be the same.")
            if not departure_date_from:
                errors.append("Please provide an earliest departure date.")
            if not email or "@" not in email:
                errors.append("Please provide a valid email address.")
            if tracking_days < 1 or tracking_days > 90:
                errors.append("Tracking days must be between 1 and 90.")
            if num_passengers < 1 or num_passengers > 9:
                errors.append("Number of passengers must be between 1 and 9.")
            if checked_bags < 0 or checked_bags > 5:
                errors.append("Checked bags per passenger must be between 0 and 5.")

            # Date validation
            try:
                d_from = datetime.strptime(departure_date_from, "%Y-%m-%d").date()
                d_to = datetime.strptime(departure_date_to, "%Y-%m-%d").date()
                if d_from > d_to:
                    errors.append("Latest departure date must be on or after earliest departure date.")
                if d_from < datetime.utcnow().date():
                    errors.append("Departure date cannot be in the past.")
            except ValueError:
                errors.append("Invalid departure date format.")

            if return_date_from:
                try:
                    r_from = datetime.strptime(return_date_from, "%Y-%m-%d").date()
                    r_to = datetime.strptime(return_date_to, "%Y-%m-%d").date()
                    if r_from > r_to:
                        errors.append("Latest return date must be on or after earliest return date.")
                    d_from_date = datetime.strptime(departure_date_from, "%Y-%m-%d").date()
                    if r_from <= d_from_date:
                        errors.append("Return date must be after the departure date.")
                except ValueError:
                    errors.append("Invalid return date format.")

            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template("index.html", form=request.form)

            expires_at = datetime.utcnow() + timedelta(days=tracking_days)

            pref = SearchPreference(
                origin=origin,
                destination=destination,
                departure_date_from=departure_date_from,
                departure_date_to=departure_date_to,
                departure_time_from=departure_time_from,
                departure_time_to=departure_time_to,
                return_date_from=return_date_from,
                return_date_to=return_date_to,
                num_passengers=num_passengers,
                checked_bags_per_passenger=checked_bags,
                max_stops=max_stops,
                email=email,
                tracking_days=tracking_days,
                expires_at=expires_at,
            )
            db.session.add(pref)
            db.session.commit()

            # Send confirmation email
            email_ok = send_confirmation_email(pref)

            # Run an immediate check so user sees results right away
            try:
                run_price_checks(app)
            except Exception as e:
                logger.error(f"Immediate check failed: {e}")

            return redirect(url_for("success", search_id=pref.id, email_sent=int(email_ok)))

        return render_template("index.html", form={})

    @app.route("/success/<int:search_id>")
    def success(search_id):
        pref = SearchPreference.query.get_or_404(search_id)
        email_sent = request.args.get("email_sent", "1") == "1"
        return render_template("success.html", pref=pref, email_sent=email_sent)

    @app.route("/searches")
    def searches():
        """Admin view of all tracked searches."""
        all_searches = SearchPreference.query.order_by(
            SearchPreference.created_at.desc()
        ).all()
        return render_template("searches.html", searches=all_searches)

    @app.route("/cancel/<int:search_id>", methods=["POST"])
    def cancel(search_id):
        pref = SearchPreference.query.get_or_404(search_id)
        pref.is_active = False
        db.session.commit()
        flash(f"Tracking cancelled for {pref.origin} → {pref.destination}.", "info")
        return redirect(url_for("searches"))

    @app.route("/api/airport-search")
    def airport_search():
        """AJAX endpoint for airport autocomplete."""
        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify([])
        results = search_airport(q)
        return jsonify(results)

    @app.route("/run-now", methods=["POST"])
    def run_now():
        """Manually trigger a price check (for testing)."""
        run_price_checks(app)
        flash("Price check triggered! Check your email shortly.", "success")
        return redirect(url_for("searches"))

    @app.route("/test-email")
    def test_email():
        """Send a plain test email and show the exact result in the browser."""
        import smtplib
        from config import Config
        to_addr = request.args.get("to", Config.SMTP_EMAIL)
        lines = []
        lines.append(f"SMTP_HOST:  {Config.SMTP_HOST}")
        lines.append(f"SMTP_PORT:  {Config.SMTP_PORT}")
        lines.append(f"SMTP_EMAIL: {Config.SMTP_EMAIL}")
        lines.append(f"PASSWORD:   {'(set, length=' + str(len(Config.SMTP_PASSWORD or '')) + ')' if Config.SMTP_PASSWORD else '(NOT SET)'}")
        lines.append(f"Sending to: {to_addr}")
        lines.append("")
        try:
            with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT, timeout=10) as server:
                lines.append("✓ Connected to SMTP server")
                server.ehlo()
                lines.append("✓ EHLO ok")
                server.starttls()
                lines.append("✓ STARTTLS ok")
                server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
                lines.append("✓ Login ok")
                server.sendmail(
                    Config.SMTP_EMAIL, to_addr,
                    f"Subject: Flight Tracker Test\r\nFrom: {Config.SMTP_EMAIL}\r\nTo: {to_addr}\r\n\r\nThis is a test email from your Flight Price Tracker app."
                )
                lines.append(f"✓ Email sent successfully to {to_addr}!")
        except Exception as e:
            lines.append(f"✗ ERROR: {type(e).__name__}: {e}")
        return "<pre style='font-family:monospace;font-size:14px;padding:2rem;'>" + "\n".join(lines) + "</pre>"

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(debug=False, port=5000)
