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
    Search all departure date (× return date for round trips) combinations and
    return the top 3 cheapest flights within the optional departure time window.
    Capped at 20 API calls to stay within Amadeus rate limits.
    """
    amadeus = get_amadeus_client()

    dep_from = datetime.strptime(pref.departure_date_from, "%Y-%m-%d").date()
    dep_to = datetime.strptime(pref.departure_date_to, "%Y-%m-%d").date()

    is_roundtrip = bool(pref.return_date_from and pref.return_date_to)

    # Build list of (dep_date, ret_date | None) pairs to query
    dep_dates = [dep_from + timedelta(days=i) for i in range((dep_to - dep_from).days + 1)]

    if is_roundtrip:
        ret_from = datetime.strptime(pref.return_date_from, "%Y-%m-%d").date()
        ret_to = datetime.strptime(pref.return_date_to, "%Y-%m-%d").date()
        ret_dates = [ret_from + timedelta(days=i) for i in range((ret_to - ret_from).days + 1)]
        pairs = [(d, r) for d in dep_dates for r in ret_dates if r > d]
    else:
        pairs = [(d, None) for d in dep_dates]

    # Cap at 20 calls, sampling evenly if needed
    if len(pairs) > 20:
        step = len(pairs) // 20
        pairs = pairs[::step][:20]

    all_offers = []
    for dep_date, ret_date in pairs:
        params = dict(
            originLocationCode=pref.origin.upper(),
            destinationLocationCode=pref.destination.upper(),
            departureDate=dep_date.strftime("%Y-%m-%d"),
            adults=pref.num_passengers,
            max=20,
            currencyCode="USD",
        )
        if ret_date:
            params["returnDate"] = ret_date.strftime("%Y-%m-%d")
        try:
            response = amadeus.shopping.flight_offers_search.get(**params)
            all_offers.extend(response.data or [])
        except ResponseError as e:
            logger.warning(f"No results for {dep_date}/{ret_date}: {e}")

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

    # Apply max stops filter
    if pref.max_stops is not None:
        flights = [
            f for f in flights
            if _max_stops_for_flight(f) <= pref.max_stops
        ]

    # Sort by total price, return top 3
    flights.sort(key=lambda x: x["total_price"])
    return flights[:3]


def _max_stops_for_flight(flight: dict) -> int:
    """Return the highest stop count across all legs of a flight."""
    out_stops = int(flight["stops"].split()[0]) if flight["stops"] != "Nonstop" else 0
    if flight.get("return"):
        ret_stops = int(flight["return"]["stops"].split()[0]) if flight["return"]["stops"] != "Nonstop" else 0
        return max(out_stops, ret_stops)
    return out_stops


def _parse_offer(offer: dict, pref) -> dict | None:
    itineraries = offer["itineraries"]

    # Outbound leg
    out = itineraries[0]
    out_segs = out["segments"]
    out_dep_dt = datetime.fromisoformat(out_segs[0]["departure"]["at"])
    out_arr_dt = datetime.fromisoformat(out_segs[-1]["arrival"]["at"])
    out_stops = len(out_segs) - 1
    out_flights = " → ".join(f"{s['carrierCode']}{s['number']}" for s in out_segs)

    # Return leg (round trip only)
    ret_info = None
    if len(itineraries) > 1:
        ret = itineraries[1]
        ret_segs = ret["segments"]
        ret_dep_dt = datetime.fromisoformat(ret_segs[0]["departure"]["at"])
        ret_arr_dt = datetime.fromisoformat(ret_segs[-1]["arrival"]["at"])
        ret_stops = len(ret_segs) - 1
        ret_flights = " → ".join(f"{s['carrierCode']}{s['number']}" for s in ret_segs)
        ret_info = {
            "departure": ret_dep_dt.strftime("%a %b %d, %Y at %I:%M %p"),
            "arrival": ret_arr_dt.strftime("%a %b %d, %Y at %I:%M %p"),
            "duration": _format_duration(ret["duration"]),
            "stops": "Nonstop" if ret_stops == 0 else f"{ret_stops} stop{'s' if ret_stops > 1 else ''}",
            "flight_numbers": ret_flights,
            "departure_datetime": ret_dep_dt,
        }

    carrier_code = offer.get("validatingAirlineCodes", [out_segs[0]["carrierCode"]])[0]
    airline_name = AIRLINE_NAMES.get(carrier_code, carrier_code)

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
    dep_date_str = out_dep_dt.strftime("%Y-%m-%d")
    pax = pref.num_passengers
    is_roundtrip = ret_info is not None
    if is_roundtrip:
        ret_date_str = ret_info["departure_datetime"].strftime("%Y-%m-%d")
        kayak_url = (
            f"https://www.kayak.com/flights/{pref.origin}-{pref.destination}"
            f"/{dep_date_str}/{ret_date_str}/{pax}adults"
        )
        google_flights_url = (
            f"https://www.google.com/flights?hl=en#flt="
            f"{pref.origin}.{pref.destination}.{dep_date_str}"
            f"*{pref.destination}.{pref.origin}.{ret_date_str}"
            f";c:{currency};e:1;sd:1;t:f"
        )
    else:
        kayak_url = (
            f"https://www.kayak.com/flights/{pref.origin}-{pref.destination}"
            f"/{dep_date_str}/{pax}adults"
        )
        google_flights_url = (
            f"https://www.google.com/flights?hl=en#flt="
            f"{pref.origin}.{pref.destination}.{dep_date_str}"
            f";c:{currency};e:1;sd:1;t:f"
        )

    return {
        "airline": airline_name,
        "carrier_code": carrier_code,
        "flight_numbers": out_flights,
        "departure": out_dep_dt.strftime("%a %b %d, %Y at %I:%M %p"),
        "arrival": out_arr_dt.strftime("%a %b %d, %Y at %I:%M %p"),
        "duration": _format_duration(out["duration"]),
        "stops": "Nonstop" if out_stops == 0 else f"{out_stops} stop{'s' if out_stops > 1 else ''}",
        "return": ret_info,
        "is_roundtrip": is_roundtrip,
        "total_price": total_price,
        "price_per_person": price_per_person,
        "currency": currency,
        "bags_included": bags_included,
        "carry_on_included": True,
        "kayak_url": kayak_url,
        "google_flights_url": google_flights_url,
        "airline_website": _get_airline_website(carrier_code),
        "departure_datetime": out_dep_dt,
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
