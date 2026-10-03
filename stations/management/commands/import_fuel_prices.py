import csv
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from stations.models import FuelStation, Place, place_key

THREE_PLACES = Decimal("0.001")


class Command(BaseCommand):
    help = "Load the fuel price list, placing each station at its town's coordinates."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=settings.FUEL_PRICES_CSV)

    def handle(self, *args, **options):
        places = {
            (state, key): (lat, lon)
            for state, key, lat, lon in Place.objects.values_list(
                "state", "key", "latitude", "longitude"
            )
        }
        if not places:
            raise CommandError("No places loaded yet. Run `manage.py import_places` first.")
        us_states = {state for state, _ in places}

        # The list repeats some truck stops with different prices and no date,
        # so there is no way to tell which one is current.
        rows_by_station = defaultdict(list)
        outside_us = 0
        with open(options["path"], encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                if row["State"].strip() not in us_states:
                    outside_us += 1
                    continue
                rows_by_station[int(row["OPIS Truckstop ID"])].append(row)

        stations = []
        unmatched = set()
        for opis_id, rows in rows_by_station.items():
            first = rows[0]
            city, state = first["City"].strip(), first["State"].strip()
            coords = places.get((state, place_key(city)))
            if coords is None:
                unmatched.add(f"{city}, {state}")
                continue

            prices = [Decimal(row["Retail Price"]) for row in rows]
            average = (sum(prices) / len(prices)).quantize(THREE_PLACES, ROUND_HALF_UP)
            stations.append(
                FuelStation(
                    opis_id=opis_id,
                    name=first["Truckstop Name"].strip(),
                    address=first["Address"].strip(),
                    city=city,
                    state=state,
                    rack_id=int(first["Rack ID"]),
                    price=average,
                    latitude=coords[0],
                    longitude=coords[1],
                )
            )

        with transaction.atomic():
            FuelStation.objects.all().delete()
            FuelStation.objects.bulk_create(stations, batch_size=1000)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(stations)} fuel stations."))
        if outside_us:
            self.stdout.write(f"Skipped {outside_us} rows outside the US.")
        if unmatched:
            self.stdout.write(
                self.style.WARNING(
                    f"Could not locate {len(unmatched)} towns: {', '.join(sorted(unmatched))}"
                )
            )
