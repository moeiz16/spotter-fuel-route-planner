from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache

import numpy as np

from planner.geo import EARTH_RADIUS_MILES, unit_vectors
from stations.models import FuelStation

# Stations compared against the route per matrix multiplication. Keeps the
# intermediate array to a few MB even on coast-to-coast routes.
BLOCK_SIZE = 512


@dataclass(frozen=True)
class RouteStation:
    """A fuel station placed along a route."""

    opis_id: int
    name: str
    address: str
    city: str
    state: str
    price: Decimal
    latitude: float
    longitude: float
    mile: float  # distance from the start to where the route passes the station
    off_route_miles: float


@lru_cache(maxsize=1)
def _station_index():
    """Every station, loaded once per process and kept as numpy arrays."""
    stations = list(
        FuelStation.objects.values(
            "opis_id", "name", "address", "city", "state", "price", "latitude", "longitude"
        )
    )
    lat = np.array([s["latitude"] for s in stations], dtype=float)
    lon = np.array([s["longitude"] for s in stations], dtype=float)
    return stations, lat, lon, unit_vectors(lat, lon)


def clear_station_index():
    _station_index.cache_clear()


def stations_along(route, radius_miles):
    """Stations within ``radius_miles`` of the route, ordered by mile marker."""
    stations, lat, lon, vectors = _station_index()
    if not stations:
        return []

    points, markers = route.sample()

    # Cheap first cut: ignore everything outside the route's bounding box.
    pad = radius_miles / 40  # degrees; a degree of longitude is 45+ miles in the lower 48
    (south, west), (north, east) = points.min(axis=0), points.max(axis=0)
    candidates = np.flatnonzero(
        (lat >= south - pad) & (lat <= north + pad) & (lon >= west - pad) & (lon <= east + pad)
    )

    route_vectors = unit_vectors(points[:, 0], points[:, 1]).T
    found = []
    for start in range(0, len(candidates), BLOCK_SIZE):
        block = candidates[start : start + BLOCK_SIZE]
        cosines = vectors[block] @ route_vectors
        nearest = cosines.argmax(axis=1)
        closest = np.clip(cosines[np.arange(len(block)), nearest], -1.0, 1.0)
        distances = EARTH_RADIUS_MILES * np.arccos(closest)

        for i in np.flatnonzero(distances <= radius_miles):
            found.append(
                RouteStation(
                    **stations[block[i]],
                    mile=float(markers[nearest[i]]),
                    off_route_miles=float(distances[i]),
                )
            )

    found.sort(key=lambda s: s.mile)
    return found
