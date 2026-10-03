import hashlib
import logging
import re
from dataclasses import dataclass

import requests
from django.conf import settings
from django.core.cache import cache

from planner.exceptions import LocationNotFound, UpstreamServiceError
from stations.models import Place, place_key

from .http import session

logger = logging.getLogger(__name__)

COORDINATES = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
CITY_STATE = re.compile(
    r"^\s*([^,]+?)\s*,\s*([A-Za-z. ]+?)\s*(?:,\s*(?:USA?|United States))?\s*$", re.I
)

# Rough (south, west, north, east) boxes: lower 48, Alaska, Hawaii.
US_BOUNDS = [
    (24.4, -125.0, 49.4, -66.9),
    (51.0, -180.0, 71.5, -129.9),
    (18.8, -160.3, 22.3, -154.7),
]

STATE_CODES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA",
    "colorado": "CO", "connecticut": "CT", "delaware": "DE", "district of columbia": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY", "louisiana": "LA",
    "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT", "virginia": "VA",
    "washington": "WA", "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
}  # fmt: skip


@dataclass(frozen=True)
class Location:
    name: str
    latitude: float
    longitude: float


def resolve(query):
    """Turn user input into a Location inside the US.

    Tried in order of cost: literal "lat,lon", then "City, ST" against the
    local places table, and only then the Nominatim API for anything else
    (street addresses, landmarks, a city with no state).
    """
    return _from_coordinates(query) or _from_places(query) or _from_nominatim(query)


def _from_coordinates(query):
    match = COORDINATES.match(query)
    if not match:
        return None
    lat, lon = float(match[1]), float(match[2])
    if not any(s <= lat <= n and w <= lon <= e for s, w, n, e in US_BOUNDS):
        raise LocationNotFound(f"'{query}' is not inside the United States.")
    return Location(name=f"{lat:.5f}, {lon:.5f}", latitude=lat, longitude=lon)


def _from_places(query):
    match = CITY_STATE.match(query)
    if not match:
        return None
    city, state = match[1], match[2].replace(".", "").strip()
    state = STATE_CODES.get(state.lower(), state.upper())
    place = Place.objects.filter(state=state, key=place_key(city)).first()
    if place is None:
        return None
    return Location(name=str(place), latitude=place.latitude, longitude=place.longitude)


def _from_nominatim(query):
    key = "geocode:" + hashlib.sha1(query.strip().lower().encode()).hexdigest()
    location = cache.get(key)
    if location is None:
        location = _search_nominatim(query)
        cache.set(key, location, settings.GEOCODE_CACHE_TIMEOUT)
    return location


def _search_nominatim(query):
    params = {"q": query, "format": "jsonv2", "limit": 1, "countrycodes": "us"}
    try:
        response = session.get(
            f"{settings.NOMINATIM_BASE_URL}/search",
            params=params,
            timeout=settings.EXTERNAL_API_TIMEOUT,
        )
        response.raise_for_status()
        results = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Nominatim request failed: %s", exc)
        raise UpstreamServiceError(
            "The geocoding service is unavailable, try again shortly."
        ) from exc

    if not results:
        raise LocationNotFound(f"Could not find '{query}' in the United States.")
    top = results[0]
    return Location(
        name=top["display_name"], latitude=float(top["lat"]), longitude=float(top["lon"])
    )
