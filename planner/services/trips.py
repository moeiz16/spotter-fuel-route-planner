from dataclasses import dataclass

from django.conf import settings

from . import corridor, fuel, geocoding, routing


@dataclass(frozen=True)
class TripPlan:
    start: geocoding.Location
    finish: geocoding.Location
    route: routing.Route
    fuel_stops: list

    @property
    def total_fuel_cost(self):
        return sum(stop.cost for stop in self.fuel_stops)

    @property
    def total_gallons(self):
        return sum(stop.gallons for stop in self.fuel_stops)


def plan_trip(start, finish):
    """Route between two places plus the cheapest set of fuel stops along it."""
    start = geocoding.resolve(start)
    finish = geocoding.resolve(finish)
    route = routing.get_route(start, finish)

    stations = corridor.stations_along(route, settings.STATION_SEARCH_RADIUS_MILES)
    stops = fuel.plan_fuel_stops(
        stations,
        route.distance_miles,
        range_miles=settings.VEHICLE_RANGE_MILES,
        mpg=settings.VEHICLE_MPG,
        stop_penalty=settings.FUEL_STOP_PENALTY,
    )
    return TripPlan(start=start, finish=finish, route=route, fuel_stops=stops)
