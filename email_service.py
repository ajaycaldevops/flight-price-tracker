import smtplib
import logging
import traceback
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape
import os

from config import Config

logger = logging.getLogger(__name__)

_jinja_env = None

def _get_jinja_env():
    global _jinja_env
    if _jinja_env is None:
        # Use abspath so the path is correct regardless of working directory
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        logger.info(f"Email template dir: {template_dir}")
        _jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(["html"]),
        )
        _jinja_env.filters["enumerate"] = enumerate
    return _jinja_env


def send_flight_alert(pref, flights: list[dict]) -> bool:
    """
    Send top-3 flight alert email to pref.email.
    Returns True on success.
    """
    if not flights:
        logger.info(f"No flights found for {pref.email}, skipping email.")
        return False

    try:
        env = _get_jinja_env()
        template = env.get_template("email.html")
        html_body = template.render(
            pref=pref,
            flights=flights,
            sent_at=datetime.now().strftime("%B %d, %Y at %I:%M %p"),
            num_results=len(flights),
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"✈ Top {len(flights)} Flights: {pref.origin} → {pref.destination}"
            f" | Best from ${flights[0]['total_price']:.2f}"
        )
        msg["From"] = f"Flight Tracker <{Config.SMTP_EMAIL}>"
        msg["To"] = pref.email

        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            server.sendmail(Config.SMTP_EMAIL, pref.email, msg.as_string())

        logger.info(f"Email sent to {pref.email} with {len(flights)} flights.")
        return True

    except Exception as e:
        logger.error(f"Failed to send flight alert to {pref.email}: {e}\n{traceback.format_exc()}")
        return False


def send_confirmation_email(pref) -> bool:
    """Send a confirmation email when tracking starts."""
    try:
        env = _get_jinja_env()
        template = env.get_template("confirmation_email.html")
        html_body = template.render(
            pref=pref,
            expires_at=pref.expires_at.strftime("%B %d, %Y"),
        )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = (
            f"✅ Flight Tracking Started: {pref.origin} → {pref.destination}"
        )
        msg["From"] = f"Flight Tracker <{Config.SMTP_EMAIL}>"
        msg["To"] = pref.email
        msg.attach(MIMEText(html_body, "html"))

        with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
            server.sendmail(Config.SMTP_EMAIL, pref.email, msg.as_string())

        logger.info(f"Confirmation sent to {pref.email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send confirmation to {pref.email}: {e}\n{traceback.format_exc()}")
        return False
