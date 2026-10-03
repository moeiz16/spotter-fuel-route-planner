from unittest import mock

from django.core.cache import cache
from django.test import TestCase

from planner.exceptions import LocationNotFound, UpstreamServiceError
from planner.services import geocoding
from stations.models import Place

from .utils import json_response


@mock.patch.object(geocoding.session, "get")
class ResolveTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Place.objects.create(name="Saint Louis", state="MO", latitude=38.63, longitude=-90.24)

    def setUp(self):
        cache.clear()

    def test_coordinates_are_used_as_given(self, get):
        location = geocoding.resolve(" 41.8781, -87.6298 ")

        self.assertEqual((location.latitude, location.longitude), (41.8781, -87.6298))
        get.assert_not_called()

    def test_coordinates_outside_the_us_are_rejected(self, get):
        with self.assertRaises(LocationNotFound):
            geocoding.resolve("51.5074,-0.1278")

    def test_city_and_state_come_from_the_places_table(self, get):
        for query in ("Saint Louis, MO", "saint louis,mo", "Saint Louis, Missouri, USA"):
            with self.subTest(query=query):
                location = geocoding.resolve(query)
                self.assertEqual(location.name, "Saint Louis, MO")
                self.assertEqual((location.latitude, location.longitude), (38.63, -90.24))
        get.assert_not_called()

    def test_anything_else_goes_to_nominatim_once(self, get):
        get.return_value = json_response(
            [{"display_name": "Willis Tower, Chicago", "lat": "41.8789", "lon": "-87.6359"}]
        )

        first = geocoding.resolve("Willis Tower")
        second = geocoding.resolve("willis tower")

        self.assertEqual(first, geocoding.Location("Willis Tower, Chicago", 41.8789, -87.6359))
        self.assertEqual(second, first)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["countrycodes"], "us")

    def test_unknown_place(self, get):
        get.return_value = json_response([])

        with self.assertRaises(LocationNotFound):
            geocoding.resolve("Nowhereville, ZZ")

    def test_geocoder_down(self, get):
        get.side_effect = geocoding.requests.Timeout()

        with self.assertLogs("planner.services.geocoding", "WARNING"):
            with self.assertRaises(UpstreamServiceError):
                geocoding.resolve("Willis Tower")
