import random
from decimal import Decimal
from itertools import pairwise

from django.test import SimpleTestCase

from planner.exceptions import FuelPlanNotPossible
from planner.services.fuel import plan_fuel_stops

from .utils import make_station


def plan(stations, trip_miles, stop_penalty=0.0):
    return plan_fuel_stops(stations, trip_miles, range_miles=500, mpg=10, stop_penalty=stop_penalty)


def summary(stops):
    return [(stop.station.mile, stop.gallons) for stop in stops]


def cheapest_possible(stations, trip_miles, tank=500, mpg=10):
    """Lowest possible fuel bill, worked out a completely different way.

    Each mile of the trip burns fuel bought somewhere in the previous ``tank``
    miles, so the best price for that mile is the cheapest station in that
    window. The full tank at the start counts as a free station at mile zero.
    """
    total = 0.0
    for mile in range(1, trip_miles + 1):
        prices = [float(s.price) for s in stations if mile - tank <= s.mile < mile]
        if mile <= tank:
            prices.append(0.0)
        total += min(prices) / mpg
    return total


class PlanFuelStopsTests(SimpleTestCase):
    def test_trip_within_one_tank_needs_no_stop(self):
        self.assertEqual(plan([make_station(200, 3.00)], 450), [])

    def test_buys_only_what_is_needed_to_finish(self):
        stops = plan([make_station(300, 3.00)], 600)

        self.assertEqual(summary(stops), [(300, Decimal("10.00"))])
        self.assertEqual(stops[0].cost, Decimal("30.00"))

    def test_picks_the_cheaper_of_two_reachable_stations(self):
        stops = plan([make_station(300, 3.50), make_station(400, 3.00)], 700)

        self.assertEqual(summary(stops), [(400, Decimal("20.00"))])

    def test_buys_just_enough_to_reach_a_cheaper_station(self):
        # Arrives at mile 400 with 100 miles left; the cheap station is 200 away.
        stops = plan([make_station(400, 4.00), make_station(600, 3.00)], 1000)

        self.assertEqual(summary(stops), [(400, Decimal("10.00")), (600, Decimal("40.00"))])

    def test_fills_up_before_an_expensive_stretch(self):
        stops = plan([make_station(400, 3.00), make_station(700, 4.00)], 1100)

        self.assertEqual(summary(stops), [(400, Decimal("40.00")), (700, Decimal("20.00"))])

    def test_only_the_cheapest_station_in_a_town_is_used(self):
        stations = [make_station(300, 3.20, opis_id=1), make_station(300, 2.90, opis_id=2)]

        stops = plan(stations, 600)

        self.assertEqual([stop.station.opis_id for stop in stops], [2])

    def test_gap_longer_than_the_range_is_reported(self):
        with self.assertRaisesMessage(FuelPlanNotPossible, "between mile 100 and mile 700"):
            plan([make_station(100, 3.00), make_station(700, 3.00)], 900)

    def test_no_stations_on_a_long_trip(self):
        with self.assertRaises(FuelPlanNotPossible):
            plan([], 501)

    def test_stop_penalty_removes_a_stop_that_saves_pennies(self):
        # The truck reaches mile 495 almost empty. The cheapest plan buys one
        # gallon there to limp to mile 510, where fuel is a cent cheaper.
        stations = [make_station(495, 3.01), make_station(510, 3.00), make_station(900, 3.50)]

        without_penalty = plan(stations, 1050)
        with_penalty = plan(stations, 1050, stop_penalty=2.0)

        self.assertEqual(len(without_penalty), 3)
        self.assertEqual(len(with_penalty), 2)
        extra = sum(s.cost for s in with_penalty) - sum(s.cost for s in without_penalty)
        self.assertLess(extra, Decimal("2.00"))

    def test_penalty_free_plan_is_the_cheapest_possible(self):
        rng = random.Random(7)
        for _ in range(40):
            trip_miles = rng.randint(300, 2500)
            miles = sorted(rng.sample(range(1, trip_miles), rng.randint(5, 60)))
            stations = [make_station(m, round(rng.uniform(2.6, 4.4), 3)) for m in miles]

            try:
                stops = plan(stations, trip_miles)
            except FuelPlanNotPossible:
                gaps = [b - a for a, b in pairwise([0, *miles, trip_miles])]
                self.assertGreater(max(gaps), 500)
                continue

            spent = float(sum(stop.cost for stop in stops))
            expected = cheapest_possible(stations, trip_miles)
            # Each stop's cost is rounded to the cent.
            self.assertAlmostEqual(spent, expected, delta=0.01 * len(stops) + 0.01)

            # Never buys more than the tank holds, never arrives with fuel to spare.
            self.assertTrue(all(stop.gallons <= 50 for stop in stops))
            bought_miles = float(sum(stop.gallons for stop in stops)) * 10
            self.assertAlmostEqual(bought_miles, max(trip_miles - 500, 0), delta=0.5)
