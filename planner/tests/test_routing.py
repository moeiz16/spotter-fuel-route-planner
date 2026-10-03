from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import SimpleTestCase

from planner.exceptions import RouteNotFound, UpstreamServiceError
from planner.geo import decode_polyline
from planner.services import routing
from planner.services.geocoding import Location

from .utils import encode_polyline, json_response, osrm_response

CHICAGO = Location("Chicago, IL", 41.85, -87.65)
DALLAS = Location("Dallas, TX", 32.78, -96.8)


class DecodePolylineTests(SimpleTestCase):
    def test_decodes_the_reference_example(self):
        # The worked example from Google's polyline format documentation.
        self.assertEqual(
            decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@"),
            [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)],
        )

    def test_round_trips_with_the_test_encoder(self):
        points = [(35.0, -100.0), (35.12345, -99.5), (34.9, -98.76543)]
        self.assertEqual(decode_polyline(encode_polyline(points)), points)


@mock.patch.object(routing.session, "get")
class GetRouteTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    def test_parses_distance_duration_and_path(self, get):
        get.return_value = osrm_response([(41.85, -87.65), (32.78, -96.8)], 925, duration_hours=14)

        route = routing.get_route(CHICAGO, DALLAS)

        self.assertAlmostEqual(route.distance_miles, 925)
        self.assertEqual(route.duration_seconds, 14 * 3600)
        self.assertEqual(route.path.tolist(), [[41.85, -87.65], [32.78, -96.8]])
        # OSRM takes longitude first.
        self.assertIn("/driving/-87.65,41.85;-96.8,32.78", get.call_args.args[0])

    def test_same_trip_is_only_requested_once(self, get):
        get.return_value = osrm_response([(41.85, -87.65), (32.78, -96.8)], 925)

        routing.get_route(CHICAGO, DALLAS)
        routing.get_route(CHICAGO, DALLAS)

        self.assertEqual(get.call_count, 1)

    def test_no_route(self, get):
        get.return_value = json_response({"code": "NoRoute", "message": "Impossible route"}, 400)

        with self.assertRaises(RouteNotFound):
            routing.get_route(CHICAGO, DALLAS)

    def test_network_failure(self, get):
        get.side_effect = routing.requests.ConnectionError("boom")

        with self.assertLogs("planner.services.routing", "WARNING"):
            with self.assertRaises(UpstreamServiceError):
                routing.get_route(CHICAGO, DALLAS)


class RouteSampleTests(SimpleTestCase):
    def test_points_are_evenly_spaced_even_when_the_path_is_not(self):
        # Three vertices, the middle one very close to the start.
        path = np.array([[35.0, -100.0], [35.0, -99.99], [35.0, -98.0]])
        route = routing.Route(distance_miles=120.0, duration_seconds=0, path=path)

        points, markers = route.sample(spacing_miles=1.0)

        self.assertEqual(len(points), 121)
        self.assertAlmostEqual(markers[0], 0.0)
        self.assertAlmostEqual(markers[-1], 120.0)
        steps = np.diff(points[:, 1])
        self.assertAlmostEqual(steps.min(), steps.max(), places=6)

    def test_outline_keeps_both_ends(self):
        path = np.column_stack((np.linspace(30, 40, 5001), np.linspace(-100, -90, 5001)))
        route = routing.Route(distance_miles=900.0, duration_seconds=0, path=path)

        outline = route.outline(max_points=100)

        self.assertLessEqual(len(outline), 101)
        self.assertEqual(outline[0].tolist(), path[0].tolist())
        self.assertEqual(outline[-1].tolist(), path[-1].tolist())
