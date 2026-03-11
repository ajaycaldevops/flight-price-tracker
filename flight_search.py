import logging
from datetime import datetime, timedelta
from amadeus import Client, ResponseError
from config import Config

logger = logging.getLogger(__name__)

# Airline IATA code -> name map (common carriers)
AIRLINE_NAMES = {
    "AA": "American Airlines", "UA": "United Airlines", "DL": "Delta Air Lines",
    "WN": "Southwest Airlines", "B6": "JetBlue", "AS": "Alaska Airlines",
    "F9": "Frontier Airlines", "NK": "Spirit Airlines", "G4": "Allegiant Air",
    "SY": "Sun Country Airlines", "HA": "Hawaiian Airlines",
    "BA": "British Airways", "LH": "Lufthansa", "AF": "Air France",
    "KL": "KLM", "EK": "Emirates", "QR": "Qatar Airways", "EY": "Etihad",
    "SQ": "Singapore Airlines", "CX": "Cathay Pacific", "JL": "Japan Airlines",
    "NH": "ANA", "TK": "Turkish Airlines", "IB": "Iberia",
    "AC": "Air Canada", "QF": "Qantas", "LA": "LATAM Airlines",
    "AM": "Aeromexico", "CM": "Copa Airlines", "AV": "Avianca",
    "VY": "Vueling", "FR": "Ryanair", "U2": "easyJet", "W6": "Wizz Air",
    "SK": "SAS", "AY": "Finnair", "LX": "Swiss", "OS": "Austrian Airlines",
}

def get_amadeus_client():
    return Client(
        client_id=Config.AMADEUS_CLIENT_ID,
        client_secret=Config.AMADEUS_CLIENT_SECRET,
        hostname=Config.AMADEUS_HOSTNAME,
        log_level="silent",
    )


def search_airport(keyword: str) -> list[dict]:
    """Search airports/cities by keyword. Returns list of {iata, name, city}."""
    try:
        amadeus = get_amadeus_client()
        response = amadeus.reference_data.locations.get(
            keyword=keyword,
            subType="AIRPORT,CITY",
        )
        results = []
        for loc in response.data[:8]:
            results.append({
                "iata": loc["iataCode"],
                "name": loc["name"],
                "city": loc.get("address", {}).get("cityName", ""),
                "country": loc.get("address", {}).get("countryName", ""),
                "label": f"{loc['iataCode']} – {loc['name']}, {loc.get('address', {}).get('cityName', '')}",
            })
        return results
    except ResponseError as e:
        logger.error(f"Airport search error: {e}")
        return []


def search_flights(pref) -> list[dict]:
    """
    Search all departure dates in the range and return top 3 cheapest flights
    that fall within the optional departure time window.
    Returns list of flight dicts ready for email rendering.
    """
    amadeus = get_amadeus_client()

    date_from = datetime.strptime(pref.departure_date_from, "%Y-%m-%d").date()
    date_to = datetime.strptime(pref.departure_date_to, "%Y-%m-%d").date()

    all_offers = []
    current = date_from
    while current <= date_to:
        try:
            response = amadeus.shopping.flight_offers_search.get(
                originLocationCode=pref.origin.upper(),
                destinationLocationCode=pref.destination.upper(),
                departureDate=current.strftime("%Y-%m-%d"),
                adults=pref.num_passengers,
                max=20,
                currencyCode="USD",
            )
            all_offers.extend(response.data or [])
        except ResponseError as e:
            logger.warning(f"No results for {current}: {e}")
        current += timedelta(days=1)

    if not all_offers:
        return []

    flights = []
    for offer in all_offers:
        try:
            flight = _parse_offer(offer, pref)
            if flight:
                flights.append(flight)
        except Exception as e:
            logger.warning(f"Failed to parse offer: {e}")

    # Apply departure time filter
    if pref.departure_time_from and pref.departure_time_to:
        flights = _filter_by_time(flights, pref.departure_time_from, pref.departure_time_to)

    # Sort by total price, return top 3
    flights.sort(key=lambda x: x["total_price"])
    return flights[:3]


def _parse_offer(offer: dict, pref) -> dict | None:
    itinerary = offer["itineraries"][0]
    segments = itinerary["segments"]
    first_seg = segments[0]
    last_seg = segments[-1]

    departure_dt = datetime.fromisoformat(first_seg["departure"]["at"])
    arrival_dt = datetime.fromisoformat(last_seg["arrival"]["at"])
    num_stops = len(segments) - 1

    carrier_code = offer.get("validatingAirlineCodes", [first_seg["carrierCode"]])[0]
    airline_name = AIRLINE_NAMES.get(carrier_code, carrier_code)
    flight_numbers = " → ".join(
        f"{s['carrierCode']}{s['number']}" for s in segments
    )

    price_info = offer["price"]
    total_price = float(price_info["grandTotal"])
    currency = price_info["currency"]
    price_per_person = round(total_price / pref.num_passengers, 2)

    # Bag info from traveler pricing (first traveler)
    bags_included = 0
    try:
        tp = offer["travelerPricings"][0]
        for fi in tp.get("fareDetailsBySegment", []):
            ai = fi.get("includedCheckedBags", {})
            bags_included = max(bags_included, ai.get("quantity", 0))
    except Exception:
        pass

    # Build booking links
    dep_date_str = departure_dt.strftime("%Y-%m-%d")
    pax = pref.num_passengers
    kayak_url = (
        f"https://www.kayak.com/flights/{pref.origin}-{pref.destination}"
        f"/{dep_date_str}/{pax}adults"
    )
    google_flights_url = (
        f"https://www.google.com/flights?hl=en#flt="
        f"{pref.origin}.{pref.destination}.{dep_date_str}"
        f";c:{currency};e:1;sd:1;t:f"
    )
    airline_website = _get_airline_website(carrier_code)

    return {
        "airline": airline_name,
        "carrier_code": carrier_code,
        "flight_numbers": flight_numbers,
        "departure": departure_dt.strftime("%a %b %d, %Y at %I:%M %p"),
        "arrival": arrival_dt.strftime("%a %b %d, %Y at %I:%M %p"),
        "duration": _format_duration(itinerary["duration"]),
        "stops": "Nonstop" if num_stops == 0 else f"{num_stops} stop{'s' if num_stops > 1 else ''}",
        "total_price": total_price,
        "price_per_person": price_per_person,
        "currency": currency,
        "bags_included": bags_included,
        "carry_on_included": True,  # assumed per spec
        "kayak_url": kayak_url,
        "google_flights_url": google_flights_url,
        "airline_website": airline_website,
        "departure_datetime": departure_dt,
    }


def _filter_by_time(flights: list[dict], time_from: str, time_to: str) -> list[dict]:
    try:
        t_from = datetime.strptime(time_from, "%H:%M").time()
        t_to = datetime.strptime(time_to, "%H:%M").time()
    except ValueError:
        return flights

    filtered = [
        f for f in flights
        if t_from <= f["departure_datetime"].time() <= t_to
    ]
    # Fall back to all flights if time filter removes everything
    return filtered if filtered else flights


def _format_duration(iso_duration: str) -> str:
    """Convert PT2H35M -> 2h 35m"""
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?", iso_duration)
    if not match:
        return iso_duration
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    parts = []
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    return " ".join(parts) or "0m"


def _get_airline_website(carrier_code: str) -> str:
    websites = {
        "AA": "https://www.aa.com", "UA": "https://www.united.com",
        "DL": "https://www.delta.com", "WN": "https://www.southwest.com",
        "B6": "https://www.jetblue.com", "AS": "https://www.alaskaair.com",
        "F9": "https://www.flyfrontier.com", "NK": "https://www.spirit.com",
        "G4": "https://www.allegiantair.com", "HA": "https://www.hawaiianairlines.com",
        "BA": "https://www.britishairways.com", "LH": "https://www.lufthansa.com",
        "AF": "https://www.airfrance.com", "KL": "https://www.klm.com",
        "EK": "https://www.emirates.com", "QR": "https://www.qatarairways.com",
        "EY": "https://www.etihad.com", "SQ": "https://www.singaporeair.com",
        "CX": "https://www.cathaypacific.com", "JL": "https://www.jal.com",
        "NH": "https://www.ana.co.jp/en/us/", "TK": "https://www.turkishairlines.com",
        "IB": "https://www.iberia.com", "AC": "https://www.aircanada.com",
        "QF": "https://www.qantas.com", "VY": "https://www.vueling.com",
        "FR": "https://www.ryanair.com", "U2": "https://www.easyjet.com",
        "W6": "https://wizzair.com", "SK": "https://www.flysas.com",
        "AY": "https://www.finnair.com", "LX": "https://www.swiss.com",
    }
    return websites.get(carrier_code, f"https://www.google.com/flights")
