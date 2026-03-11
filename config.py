import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = "sqlite:///flight_tracker.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    AMADEUS_CLIENT_ID = os.getenv("AMADEUS_CLIENT_ID")
    AMADEUS_CLIENT_SECRET = os.getenv("AMADEUS_CLIENT_SECRET")
    AMADEUS_HOSTNAME = os.getenv("AMADEUS_HOSTNAME", "test")  # "test" or "production"

    SMTP_EMAIL = os.getenv("SMTP_EMAIL")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    SMTP_HOST = "smtp.gmail.com"
    SMTP_PORT = 587
