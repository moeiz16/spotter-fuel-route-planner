import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from stations.models import FuelStation, Place

# country, zip, place, state name, state, county, county code, -, -, lat, lon, accuracy
PLACES = """\
US\t74332\tBig Cabin\tOklahoma\tOK\tCraig\t035\t\t\t36.5340\t-95.2246\t4
US\t53532\tDeforest\tWisconsin\tWI\tDane\t025\t\t\t43.2478\t-89.3437\t4
US\t64101\tKansas City\tMissouri\tMO\tJackson\t095\t\t\t39.10\t-94.60\t4
US\t64102\tKansas City\tMissouri\tMO\tJackson\t095\t\t\t39.08\t-94.58\t4
US\t64150\tKansas City\tMissouri\tMO\tPlatte\t165\t\t\t39.30\t-94.70\t4
"""

PRICES = """\
OPIS Truckstop ID,Truckstop Name,Address,City,State,Rack ID,Retail Price
7,WOODSHED OF BIG CABIN,"I-44, EXIT 283 & US-69",Big Cabin,OK,307,3.00733333
9,TRUCK STOP ,"I-90, EXIT 126",De Forest                  ,WI,420,3.299
9,TRUCK STOP,"I-90, EXIT 126",De Forest,WI,420,3.399
9,TRUCK STOP,"I-90, EXIT 126",De Forest,WI,420,3.349
15,FLYING J,"Hwy 1",Calgary,AB,900,4.10
22,LOST STATION,"Nowhere Rd",Atlantis,OK,307,3.10
"""


class ImportTests(TestCase):
    def setUp(self):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.places_file = folder / "places.txt"
        self.places_file.write_text(PLACES)
        self.prices_file = folder / "prices.csv"
        self.prices_file.write_text(PRICES)

    def run_command(self, name, path):
        out = StringIO()
        call_command(name, str(path), stdout=out)
        return out.getvalue()

    def test_places_are_one_per_town(self):
        self.run_command("import_places", self.places_file)

        self.assertEqual(Place.objects.count(), 3)
        # Platte County is ignored: most of the city's ZIP codes are in Jackson.
        kansas_city = Place.objects.get(state="MO")
        self.assertAlmostEqual(kansas_city.latitude, 39.09)
        self.assertAlmostEqual(kansas_city.longitude, -94.59)

    def test_stations_are_located_and_deduplicated(self):
        self.run_command("import_places", self.places_file)
        output = self.run_command("import_fuel_prices", self.prices_file)

        self.assertEqual(sorted(FuelStation.objects.values_list("opis_id", flat=True)), [7, 9])

        woodshed = FuelStation.objects.get(opis_id=7)
        self.assertEqual(woodshed.price, Decimal("3.007"))
        self.assertEqual((woodshed.latitude, woodshed.longitude), (36.534, -95.2246))

        # Three price rows averaged; "De Forest" matched to "Deforest".
        truck_stop = FuelStation.objects.get(opis_id=9)
        self.assertEqual(truck_stop.name, "TRUCK STOP")
        self.assertEqual(truck_stop.city, "De Forest")
        self.assertEqual(truck_stop.price, Decimal("3.349"))
        self.assertEqual(truck_stop.latitude, 43.2478)

        self.assertIn("Skipped 1 rows outside the US", output)
        self.assertIn("Atlantis, OK", output)

    def test_running_again_replaces_the_price_list(self):
        self.run_command("import_places", self.places_file)
        self.run_command("import_fuel_prices", self.prices_file)
        self.run_command("import_fuel_prices", self.prices_file)

        self.assertEqual(FuelStation.objects.count(), 2)

    def test_prices_need_places_first(self):
        with self.assertRaises(CommandError):
            self.run_command("import_fuel_prices", self.prices_file)
