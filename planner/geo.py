import numpy as np

EARTH_RADIUS_MILES = 3958.8
METERS_PER_MILE = 1609.344


def unit_vectors(lat, lon):
    """Convert degrees to points on the unit sphere, one row per coordinate.

    The dot product of two such vectors is the cosine of the angle between
    them, which turns "distance from every station to every route point"
    into a single matrix multiplication.
    """
    lat, lon = np.radians(lat), np.radians(lon)
    return np.column_stack((np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)))


def path_lengths(path):
    """Great-circle length in miles of each leg of a (lat, lon) path."""
    lat, lon = np.radians(path[:, 0]), np.radians(path[:, 1])
    dlat, dlon = np.diff(lat), np.diff(lon)
    a = np.sin(dlat / 2) ** 2 + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * np.arcsin(np.sqrt(a))


def decode_polyline(encoded, precision=5):
    """Decode a Google-encoded polyline into a list of (lat, lon) tuples."""
    factor = 10**precision
    points = []
    index = lat = lon = 0
    while index < len(encoded):
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        points.append((lat / factor, lon / factor))
    return points
