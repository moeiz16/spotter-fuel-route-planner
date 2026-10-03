from decimal import Decimal
from unittest import mock

import numpy as np
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from planner.services import corridor, http
from stations.models import FuelStation, Place

from .utils import json_response, osrm_response

# A made-up road running due east along the 35th parallel. One degree of
# longitude there is about 56.6 miles, so the whole thing is roughly 680 miles.
ROAD = [(35.0, float(lon)) for lon in np.linspace(-100.0, -88.0, 25)]
ROAD_MILES = 680


def add_station(opis_id, longitude, price, latitude=35.0):
    return FuelStation.objects.create(
        opis_id=opis_id,
        name=f"Station {opis_id}",
        address="I-40",
        city="Somewhere",
        state="OK",
        rack_id=1,
        price=Decimal(price),
        latitude=latitude,
        longitude=longitude,
    )


@mock.patch.object(http.session, "get")
class RouteApiTests(TestCase):
    url = reverse("planner:route")

    @classmethod
    def setUpTestData(cls):
        Place.objects.create(name="Westville", state="OK", latitude=35.0, longitude=-100.0)
        Place.objects.create(name="Eastville", state="TN", latitude=35.0, longitude=-88.0)
        add_station(1, -96.0, "3.500")  # about mile 227
        add_station(2, -94.0, "3.100")  # about mile 340
        add_station(3, -93.0, "3.900")  # about mile 397
        add_station(4, -94.0, "2.500", latitude=35.5)  # cheap, but 35 miles off the road

    def setUp(self):
        cache.clear()
        corridor.clear_station_index()
        self.addCleanup(corridor.clear_station_index)

    def get_plan(self, **params):
        params = {"start": "Westville, OK", "finish": "Eastville, TN", **params}
        return self.client.get(self.url, params)

    def test_plans_a_trip_with_a_single_routing_call(self, get):
        get.return_value = osrm_response(ROAD, ROAD_MILES, duration_hours=10)

        response = self.get_plan()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(get.call_count, 1)
        body = response.json()
        self.assertEqual(body["start"]["name"], "Westville, OK")
        self.assertEqual(body["route"]["distance_miles"], 680.0)
        self.assertEqual(body["route"]["duration_hours"], 10.0)
        self.assertEqual(body["route"]["geometry"]["type"], "LineString")
        self.assertEqual(body["route"]["geometry"]["coordinates"][0], [-100.0, 35.0])

        # 180 miles short of the destination on one tank; the cheapest station
        # that is actually on the road covers it.
        self.assertEqual([stop["opis_id"] for stop in body["fuel_stops"]], [2])
        stop = body["fuel_stops"][0]
        self.assertEqual(stop["gallons"], 18.0)
        self.assertEqual(stop["cost"], 55.8)
        self.assertEqual(body["total_fuel_cost"], 55.8)
        self.assertIn("/api/v1/route/map/?start=Westville", body["map_url"])

    def test_repeat_request_makes_no_external_call(self, get):
        get.return_value = osrm_response(ROAD, ROAD_MILES)

        self.get_plan()
        self.get_plan()

        self.assertEqual(get.call_count, 1)

    def test_both_locations_are_required(self, get):
        response = self.client.get(self.url, {"start": "Westville, OK"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("finish", response.json())
        get.assert_not_called()

    def test_location_outside_the_us(self, get):
        response = self.get_plan(finish="48.8566,2.3522")

        self.assertEqual(response.status_code, 400)
        self.assertIn("not inside the United States", response.json()["detail"])

    def test_no_route(self, get):
        get.return_value = json_response({"code": "NoRoute"}, 400)

        self.assertEqual(self.get_plan().status_code, 422)

    def test_no_station_within_range(self, get):
        FuelStation.objects.all().delete()
        get.return_value = osrm_response(ROAD, ROAD_MILES)

        response = self.get_plan()

        self.assertEqual(response.status_code, 422)
        self.assertIn("no station within range", response.json()["detail"])

    def test_routing_service_down(self, get):
        get.side_effect = http.requests.ConnectionError()

        with self.assertLogs("planner.services.routing", "WARNING"):
            response = self.get_plan()

        self.assertEqual(response.status_code, 502)

    def test_map_page_shows_the_plan(self, get):
        get.return_value = osrm_response(ROAD, ROAD_MILES)

        response = self.client.get(
            reverse("planner:route-map"), {"start": "Westville, OK", "finish": "Eastville, TN"}
        )

        self.assertContains(response, "Station 2")
        self.assertContains(response, "$55.80")
        self.assertContains(response, 'id="plan-data"')

    def test_map_page_without_parameters_is_just_the_form(self, get):
        response = self.client.get(reverse("planner:route-map"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="plan-data"')
