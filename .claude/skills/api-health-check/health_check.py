import sys
import time
import os
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

client_id = os.getenv("AMADEUS_CLIENT_ID")
client_secret = os.getenv("AMADEUS_CLIENT_SECRET")
hostname = os.getenv("AMADEUS_HOSTNAME", "test")
env_label = "sandbox" if hostname == "test" else "production"

print(f"Environment : {hostname} ({env_label})")

if not client_id or not client_secret:
    print("Credentials : MISSING — set AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET in .env")
    print("Status      : DOWN")
    sys.exit(1)

print(f"Credentials : set")

SLOW_WARN = 1.5   # seconds
SLOW_CRIT = 3.0   # seconds

try:
    from amadeus import Client, ResponseError

    t0 = time.perf_counter()
    amadeus = Client(
        client_id=client_id,
        client_secret=client_secret,
        hostname=hostname,
        log_level="silent",
    )
    # Lightweight call: airport lookup forces OAuth token exchange + one API round-trip
    response = amadeus.reference_data.locations.get(keyword="JFK", subType="AIRPORT")
    elapsed = time.perf_counter() - t0

    result_count = len(response.data)

    if elapsed < SLOW_WARN:
        status, flag = "UP", "OK"
    elif elapsed < SLOW_CRIT:
        status, flag = "SLOW", "WARNING"
    else:
        status, flag = "SLOW", "CRITICAL — response time exceeds 3s"

    print(f"Response    : {elapsed:.2f}s  [{flag}]")
    print(f"API results : {result_count} location(s) returned for 'JFK'")
    print(f"Status      : {status}")

    if elapsed >= SLOW_CRIT:
        print("\n! API is responding but very slowly — check https://developers.amadeus.com for outage notices.")
    elif elapsed >= SLOW_WARN:
        print("\n~ API is slightly slow. Monitor for degradation.")
    else:
        print("\nAmadeus API is healthy.")

except Exception as e:
    elapsed = time.perf_counter() - t0 if "t0" in dir() else None
    err = str(e)
    print(f"Response    : {f'{elapsed:.2f}s' if elapsed else 'n/a'}")
    print(f"Error       : {err}")

    if "401" in err or "Unauthorized" in err:
        cause = "Authentication failed — verify AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET"
    elif "429" in err:
        cause = "Rate limited — too many requests, wait before retrying"
    elif "403" in err:
        cause = "Forbidden — credentials may not have access to this environment"
    else:
        cause = "Cannot reach Amadeus API — check network or https://developers.amadeus.com"

    print(f"Cause       : {cause}")
    print(f"Status      : DOWN")
    sys.exit(1)
