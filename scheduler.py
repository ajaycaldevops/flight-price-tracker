import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler = None


def run_price_checks(app):
    """Called by the scheduler at 7am and 8pm. Checks all active searches."""
    from models import SearchPreference, db
    from flight_search import search_flights
    from email_service import send_flight_alert

    with app.app_context():
        now = datetime.utcnow()
        active_searches = SearchPreference.query.filter(
            SearchPreference.is_active == True,
            SearchPreference.expires_at >= now,
        ).all()

        logger.info(f"[{now}] Running price checks for {len(active_searches)} active searches.")

        for pref in active_searches:
            try:
                flights = search_flights(pref)
                if flights:
                    send_flight_alert(pref, flights)
                else:
                    logger.info(f"No flights found for search #{pref.id}")
            except Exception as e:
                logger.error(f"Error processing search #{pref.id}: {e}")

        # Deactivate expired searches
        expired = SearchPreference.query.filter(
            SearchPreference.is_active == True,
            SearchPreference.expires_at < now,
        ).all()
        for pref in expired:
            pref.is_active = False
            logger.info(f"Deactivated expired search #{pref.id} for {pref.email}")
        if expired:
            db.session.commit()


def start_scheduler(app):
    global _scheduler
    if _scheduler and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="America/Los_Angeles")

    # 7:00 AM Eastern
    _scheduler.add_job(
        func=run_price_checks,
        trigger=CronTrigger(hour=7, minute=0),
        args=[app],
        id="morning_check",
        replace_existing=True,
        name="Morning flight price check (7am ET)",
    )

    # 8:00 PM Eastern
    _scheduler.add_job(
        func=run_price_checks,
        trigger=CronTrigger(hour=20, minute=0),
        args=[app],
        id="evening_check",
        replace_existing=True,
        name="Evening flight price check (8pm ET)",
    )

    _scheduler.start()
    logger.info("Scheduler started: checks at 7:00 AM and 8:00 PM (Pacific).")


def stop_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("Scheduler stopped.")
