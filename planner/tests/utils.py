from decimal import Decimal
from unittest import mock

from planner.services.corridor import RouteStation


def make_station(mile, price, opis_id=None, **extra):
    """A RouteStation with only the fields a test cares about filled in."""
    fields = {
        "opis_id": opis_id if opis_id is not None else int(mile),
        "name": f"Station at mile {mile}",
        "address": "",
        "city": "",
        "state": "",
        "price": Decimal(str(price)),
        "latitude": 0.0,
        "longitude": 0.0,
        "mile": mile,
        "off_route_miles": 0.0,
    }
    fields.update(extra)
    return RouteStation(**fields)


def encode_polyline(points):
    """Inverse of planner.geo.decode_polyline, to build fake OSRM responses."""
    encoded = []
    previous = (0, 0)
    for point in points:
        current = (round(point[0] * 1e5), round(point[1] * 1e5))
        for value in (current[0] - previous[0], current[1] - previous[1]):
            value = ~(value << 1) if value < 0 else value << 1
            while value >= 0x20:
                encoded.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            encoded.append(chr(value + 63))
        previous = current
    return "".join(encoded)


def json_response(body, status=200):
    response = mock.Mock(status_code=status)
    response.json.return_value = body
    return response


def osrm_response(points, distance_miles, duration_hours=1.0):
    return json_response(
        {
            "code": "Ok",
            "routes": [
                {
                    "distance": distance_miles * 1609.344,
                    "duration": duration_hours * 3600,
                    "geometry": encode_polyline(points),
                }
            ],
        }
    )
