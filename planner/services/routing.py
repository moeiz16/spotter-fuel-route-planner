import logging
from dataclasses import dataclass

import numpy as np
import requests
from django.conf import settings
from django.core.cache import cache

from planner.exceptions import RouteNotFound, UpstreamServiceError
from planner.geo import METERS_PER_MILE, decode_polyline, path_lengths

from .http import session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Route:
    distance_miles: float
    duration_seconds: float
    path: np.ndarray  # shape (n, 2): latitude, longitude

    def sample(self, spacing_miles=1.0):
        """Points spaced evenly along the route, with the mile marker of each.

        The raw geometry is uneven: hundreds of points on a mountain pass, a
        handful on a straight interstate. Even spacing makes "nearest point on
        the route" accurate to about half the spacing wherever a station is.
        """
        legs = path_lengths(self.path)
        if not len(legs) or not legs.sum():
            return self.path[:1], np.zeros(1)

        # Scale so the last marker matches the driving distance OSRM reports.
        travelled = np.concatenate(([0.0], np.cumsum(legs)))
        travelled *= self.distance_miles / travelled[-1]

        count = max(int(self.distance_miles / spacing_miles) + 1, 2)
        markers = np.linspace(0.0, self.distance_miles, count)
        points = np.column_stack(
            (
                np.interp(markers, travelled, self.path[:, 0]),
                np.interp(markers, travelled, self.path[:, 1]),
            )
        )
        return points, markers

    def outline(self, max_points=1500):
        """The path thinned to a size that is reasonable to send to a client."""
        step = -(-len(self.path) // max_points)
        thinned = self.path[::step]
        if (len(self.path) - 1) % step:
            thinned = np.vstack((thinned, self.path[-1]))
        return thinned


def get_route(start, finish):
    """Driving route between two locations. Makes at most one OSRM request."""
    key = (
        f"route:{start.latitude:.4f},{start.longitude:.4f}"
        f":{finish.latitude:.4f},{finish.longitude:.4f}"
    )
    route = cache.get(key)
    if route is None:
        route = _fetch_route(start, finish)
        cache.set(key, route, settings.ROUTE_CACHE_TIMEOUT)
    return route


def _fetch_route(start, finish):
    # OSRM wants lon,lat. The full-resolution geometry is needed to match
    # stations against the road, and the polyline encoding keeps it compact.
    url = (
        f"{settings.OSRM_BASE_URL}/route/v1/driving/"
        f"{start.longitude},{start.latitude};{finish.longitude},{finish.latitude}"
    )
    params = {"overview": "full", "geometries": "polyline", "steps": "false"}
    try:
        response = session.get(url, params=params, timeout=settings.EXTERNAL_API_TIMEOUT)
        body = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("OSRM request failed: %s", exc)
        raise UpstreamServiceError(
            "The routing service is unavailable, try again shortly."
        ) from exc

    # OSRM reports problems in the body ("NoRoute", "InvalidQuery", ...),
    # usually alongside a 400.
    code = body.get("code")
    if code == "NoRoute":
        raise RouteNotFound("No driving route exists between these locations.")
    if code != "Ok":
        logger.warning("OSRM returned %s: %s", code, body.get("message"))
        raise UpstreamServiceError("The routing service could not process this request.")

    best = body["routes"][0]
    return Route(
        distance_miles=best["distance"] / METERS_PER_MILE,
        duration_seconds=best["duration"],
        path=np.array(decode_polyline(best["geometry"])),
    )
