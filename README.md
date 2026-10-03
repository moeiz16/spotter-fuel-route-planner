# Fuel route planner

A Django API that takes a start and a finish location in the USA and returns the
driving route, the cheapest places to stop for fuel along it, and the total fuel
cost.

- Django 6.1, Django REST Framework, Python 3.13
- One call to a free routing API ([OSRM](https://project-osrm.org/)) per new trip, none for a repeated one
- Responds in about 20 ms once a route is cached; a new route takes as long as OSRM does (usually around a second)

## Running it

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python manage.py migrate
python manage.py import_places         # US towns and their coordinates
python manage.py import_fuel_prices    # the supplied price list

python manage.py runserver
```

No API keys are needed. Then open
<http://127.0.0.1:8000/api/v1/route/map/?start=Chicago,+IL&finish=Miami,+FL>
or import `docs/postman_collection.json` into Postman.

Interactive API docs (Scalar): <http://127.0.0.1:8000/api/docs/>

Tests: `python manage.py test`

## API

### `GET /api/v1/route/?start=<location>&finish=<location>`

A location can be any of:

| Form | Example | External calls |
| --- | --- | --- |
| City and state | `Chicago, IL` or `Chicago, Illinois` | none |
| Coordinates | `41.8781,-87.6298` | none |
| Anything else | `1600 Pennsylvania Ave NW, Washington DC` | one Nominatim lookup, cached |

Response (geometry and stops shortened):

```json
{
  "start": {"name": "Chicago, IL", "latitude": 41.85421, "longitude": -87.67605},
  "finish": {"name": "Miami, FL", "latitude": 25.7687, "longitude": -80.25724},
  "route": {
    "distance_miles": 1348.0,
    "duration_hours": 25.41,
    "geometry": {"type": "LineString", "coordinates": [[-87.6759, 41.85422], "..."]}
  },
  "fuel_stops": [
    {
      "opis_id": 70437,
      "name": "Thorntons #155",
      "address": "SR-1020 N, & SR1065 E",
      "city": "Louisville",
      "state": "KY",
      "latitude": 38.20845,
      "longitude": -85.69631,
      "mile_marker": 299.0,
      "miles_off_route": 2.2,
      "price_per_gallon": 2.906,
      "gallons": 7.5,
      "cost": 21.8
    }
  ],
  "total_gallons": 84.9,
  "total_fuel_cost": 242.45,
  "vehicle": {"range_miles": 500, "miles_per_gallon": 10, "starts_with_full_tank": true},
  "map_url": "http://127.0.0.1:8000/api/v1/route/map/?start=Chicago%2C+IL&finish=Miami%2C+FL"
}
```

`route.geometry` is GeoJSON, so it can be dropped straight onto any map
library. `map_url` is the same plan already drawn.

| Status | When |
| --- | --- |
| 400 | A parameter is missing, or a location can't be found or is outside the US |
| 422 | No driving route exists, or the price list has no station within range on part of the route |
| 502 | The routing or geocoding service is down |

### `GET /api/v1/route/map/?start=<location>&finish=<location>`

An HTML page (Leaflet + OpenStreetMap tiles) showing the route, the numbered
fuel stops and the totals. Without parameters it shows an empty form.

## How it works

1. **Resolve the two locations.** Coordinates are used as given. `City, ST` is
   looked up in a local table of US towns. Only free-form text goes to
   Nominatim.
2. **Fetch the route** from OSRM: one request, full geometry. The result is
   cached by coordinate pair.
3. **Find the stations on the way.** The route is resampled to a point every
   mile, and every station's distance to every point is computed with one numpy
   matrix product. Stations within 5 miles are kept, each tagged with the mile
   marker where the route passes it.
4. **Choose the stops** with a dynamic programme over (station, fuel left in
   the tank) that minimises total spend.

Steps 3 and 4 together take around 15 ms on a coast-to-coast route. Everything
else is the OSRM round trip.

## Decisions and assumptions

**Station locations.** The price list has no coordinates, and addresses like
`I-44, EXIT 283 & US-69` don't geocode reliably. Geocoding 6,600 addresses
through a free API would also take hours. So each station is placed at the
centre of its town, using the GeoNames postal code file (all 6,626 US stations
matched). That is accurate to a few miles, which is enough for deciding
where to stop on a 500 mile tank, and it is why the search corridor is 5 miles
wide rather than tighter.

**Duplicate prices.** About 600 truck stops appear more than once with different
prices and no date. There is no way to know which is current, so they are
averaged into one station.

**Canadian rows** (620 of them) are skipped since trips are within the USA.

**Starting fuel.** The truck leaves with a full tank and may arrive empty.
`total_fuel_cost` is what gets spent at the pump during the trip, so a trip
under 500 miles costs nothing and has no stops.

**"Optimal".** The cheapest possible plan buys each gallon at the lowest price
available within the previous 500 miles. Taken literally that produces things
like a 0.2 gallon stop to save one cent. So the optimiser charges itself a
small amount per stop (`FUEL_STOP_PENALTY`, $2 by default). On New York to Los
Angeles that takes the plan from 14 stops to 7 and adds $3.25 to a $703.55 fuel
bill. Set it to 0 for the strict minimum. The penalty is never included in the
reported cost.

**Caching.** Routes are cached, not finished plans, so a price update takes
effect without clearing anything. The default cache is in-process memory; with
several workers it should be Redis.

**One routing call.** OSRM's public server needs no key and returns the whole
geometry in one response. `OSRM_BASE_URL` can point at a self-hosted instance.

## Limitations

- The supplied list has only 16 stations in California, so routes that run the
  length of the west coast (Seattle to Los Angeles, for example) have a gap of
  more than 500 miles and return a 422 that says where the gap is.
- The detour from the route to a station is not added to the mileage.
- The plan lets the tank run to empty. A real dispatcher would want a reserve.
- Coordinates are checked against bounding boxes for the lower 48, Alaska and
  Hawaii, which is approximate near the borders.
- Stations are loaded into memory once per process, so the server needs a
  restart after `import_fuel_prices`.

## Settings

All optional, read from the environment.

| Variable | Default | |
| --- | --- | --- |
| `FUEL_STOP_PENALTY` | `2` | Dollars a stop must save to be worth making |
| `STATION_SEARCH_RADIUS_MILES` | `5` | How far from the route a station can be |
| `OSRM_BASE_URL` | `https://router.project-osrm.org` | |
| `NOMINATIM_BASE_URL` | `https://nominatim.openstreetmap.org` | |
| `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_ALLOWED_HOSTS` | development values | |

The range (500 miles) and consumption (10 mpg) are in `config/settings.py`.

## Layout

```
config/                  project settings and URLs
stations/                FuelStation and Place models, the two import commands
planner/
  services/geocoding.py  location text -> coordinates
  services/routing.py    OSRM client and the Route object
  services/corridor.py   stations near a route
  services/fuel.py       the fuel stop optimiser
  services/trips.py      ties the four together
  views.py, serializers.py, templates/
data/                    the price list and the GeoNames file
docs/                    Postman collection
```

## Credits

Routing by [OSRM](https://project-osrm.org/), geocoding by
[Nominatim](https://nominatim.org/), map data © OpenStreetMap contributors,
town coordinates from [GeoNames](https://www.geonames.org/) (CC BY 4.0).
