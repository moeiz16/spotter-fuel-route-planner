from decimal import Decimal

import numpy as np
from django.test import TestCase

from planner.services import corridor
from planner.services.routing import Route
from stations.models import FuelStation

# Due north along a meridian, where one degree of latitude is 69.1 miles.
ROUTE = Route(
    distance_miles=691.0,
    duration_seconds=0,
    path=np.column_stack((np.linspace(30.0, 40.0, 50), np.full(50, -95.0))),
)


class StationsAlongTests(TestCase):
    def setUp(self):
        corridor.clear_station_index()
        self.addCleanup(corridor.clear_station_index)

    def add_station(self, opis_id, latitude, longitude):
        FuelStation.objects.create(
            opis_id=opis_id, name="", address="", city="", state="TX", rack_id=1,
            price=Decimal("3.000"), latitude=latitude, longitude=longitude,
        )  # fmt: skip

    def test_finds_stations_near_the_route_in_travel_order(self):
        self.add_station(1, 38.0, -95.02)  # 1 mile west of the road, far end
        self.add_station(2, 31.0, -95.05)  # 3 miles west, near the start
        self.add_station(3, 35.0, -95.5)  # 28 miles west
        self.add_station(4, 45.0, -95.0)  # past the end of the route

        found = corridor.stations_along(ROUTE, radius_miles=5)

        self.assertEqual([s.opis_id for s in found], [2, 1])
        self.assertAlmostEqual(found[0].mile, 69.1, delta=1)
        self.assertAlmostEqual(found[0].off_route_miles, 3.0, delta=0.2)
        self.assertAlmostEqual(found[1].mile, 552.8, delta=1)

    def test_wider_radius_picks_up_more(self):
        self.add_station(3, 35.0, -95.5)

        self.assertEqual(corridor.stations_along(ROUTE, radius_miles=5), [])
        self.assertEqual(len(corridor.stations_along(ROUTE, radius_miles=30)), 1)

    def test_no_stations_loaded(self):
        self.assertEqual(corridor.stations_along(ROUTE, radius_miles=5), [])
