import math
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

import numpy as np

from planner.exceptions import FuelPlanNotPossible

from .corridor import RouteStation

CENTS = Decimal("0.01")


@dataclass(frozen=True)
class FuelStop:
    station: RouteStation
    gallons: Decimal
    cost: Decimal


def plan_fuel_stops(stations, trip_miles, *, range_miles, mpg, stop_penalty=0.0):
    """Choose where to buy fuel, and how much, to finish the trip cheaply.

    The truck leaves with a full tank and may arrive empty. This is a dynamic
    programme over (station, fuel in the tank): ``cost[f]`` is the least money
    that can have been spent to be at the current point of the route with
    ``f`` miles of fuel left. Fuel is counted in whole miles, so purchases come
    out in tenths of a gallon at 10 mpg.

    ``stop_penalty`` is a dollar amount charged per stop while optimising (it
    is not part of the returned costs). With a penalty of zero the result is
    the true minimum fuel spend, but that plan is full of stops nobody would
    make, like pulling in for half a gallon because this town is a cent
    cheaper than the next. A few dollars per stop removes those and barely
    moves the total.
    """
    tank = int(range_miles)
    finish = math.ceil(trip_miles)

    # Stations in the same town share a mile marker; only the cheapest matters.
    cheapest = {}
    for station in stations:
        mile = round(station.mile)
        if mile not in cheapest or station.price < cheapest[mile].price:
            cheapest[mile] = station
    stations = sorted(cheapest.items())

    levels = np.arange(tank + 1)
    cost = np.full(tank + 1, np.inf)
    cost[tank] = 0.0

    position = 0
    arrived_with = []  # per station: the level we pulled in with, for each level we left with
    for mile, station in stations:
        cost = _drive(cost, position, mile)
        position = mile

        # Leaving with g after arriving with f <= g costs cost[f] + (g - f) * per_mile.
        # Taking the running minimum of cost[f] - f * per_mile gives the best f
        # for every g in one pass.
        per_mile = float(station.price) / mpg
        base = cost - levels * per_mile
        best = np.minimum.accumulate(base)
        best_from = np.maximum.accumulate(np.where(base <= best, levels, 0))

        buying = best + levels * per_mile + stop_penalty
        buy = buying < cost
        cost = np.where(buy, buying, cost)
        arrived_with.append(np.where(buy, best_from, levels))

    cost = _drive(cost, position, finish)
    position = finish

    # Walk back from the cheapest way of arriving to recover the purchases.
    stops = []
    level = int(cost.argmin())
    for (mile, station), came_in_with in zip(stations[::-1], arrived_with[::-1], strict=True):
        level += position - mile
        position = mile
        before = int(came_in_with[level])
        if before < level:
            stops.append(_stop(station, (level - before) / mpg))
        level = before

    stops.reverse()
    return stops


def _drive(cost, from_mile, to_mile):
    """Shift every fuel level down by the distance driven."""
    gap = to_mile - from_mile
    moved = np.full_like(cost, np.inf)
    if gap < len(cost):
        moved[: len(cost) - gap] = cost[gap:]
    if not np.isfinite(moved).any():
        raise FuelPlanNotPossible(
            f"The fuel price list has no station within range between mile {from_mile} "
            f"and mile {to_mile} of this route."
        )
    return moved


def _stop(station, gallons):
    gallons = Decimal(gallons).quantize(CENTS, ROUND_HALF_UP)
    cost = (gallons * station.price).quantize(CENTS, ROUND_HALF_UP)
    return FuelStop(station=station, gallons=gallons, cost=cost)
