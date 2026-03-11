from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class SearchPreference(db.Model):
    __tablename__ = "search_preferences"

    id = db.Column(db.Integer, primary_key=True)

    # Route
    origin = db.Column(db.String(3), nullable=False)       # IATA code e.g. JFK
    destination = db.Column(db.String(3), nullable=False)  # IATA code e.g. LAX

    # Travel dates
    departure_date_from = db.Column(db.String(10), nullable=False)  # YYYY-MM-DD
    departure_date_to = db.Column(db.String(10), nullable=False)    # YYYY-MM-DD
    return_date_from = db.Column(db.String(10), nullable=True)      # YYYY-MM-DD (round trip)
    return_date_to = db.Column(db.String(10), nullable=True)        # YYYY-MM-DD (round trip)

    # Departure time window (24h format, e.g. "06:00")
    departure_time_from = db.Column(db.String(5), nullable=True)
    departure_time_to = db.Column(db.String(5), nullable=True)

    # Passengers, bags & stops
    num_passengers = db.Column(db.Integer, default=1)
    checked_bags_per_passenger = db.Column(db.Integer, default=0)
    max_stops = db.Column(db.Integer, nullable=True)  # None = any number of stops

    # Notification settings
    email = db.Column(db.String(255), nullable=False)
    tracking_days = db.Column(db.Integer, nullable=False)

    # Lifecycle
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    def __repr__(self):
        return f"<Search {self.origin}->{self.destination} for {self.email}>"
