import csv
from collections import Counter, defaultdict

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from stations.models import Place, place_key

# Column positions in the GeoNames postal code dump (tab separated, no header).
PLACE_NAME, STATE, COUNTY, LATITUDE, LONGITUDE = 2, 4, 5, 9, 10


class Command(BaseCommand):
    help = "Load US towns and their coordinates from the GeoNames postal code file."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=settings.PLACES_FILE)

    def handle(self, *args, **options):
        # town -> county -> coordinates of every ZIP code in it
        towns = defaultdict(lambda: defaultdict(list))
        names = defaultdict(Counter)

        with open(options["path"], encoding="utf-8", newline="") as f:
            for row in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
                if not row[STATE] or not row[LATITUDE]:
                    continue
                town = (row[STATE], place_key(row[PLACE_NAME]))
                towns[town][row[COUNTY]].append((float(row[LATITUDE]), float(row[LONGITUDE])))
                names[town][row[PLACE_NAME]] += 1

        places = []
        for (state, key), counties in towns.items():
            # A few names repeat within a state (or spill over a county line).
            # Go with the county that holds most of the ZIP codes rather than
            # averaging points that may be far apart.
            points = max(counties.values(), key=len)
            places.append(
                Place(
                    name=names[state, key].most_common(1)[0][0],
                    state=state,
                    key=key,
                    latitude=sum(lat for lat, _ in points) / len(points),
                    longitude=sum(lon for _, lon in points) / len(points),
                )
            )

        with transaction.atomic():
            Place.objects.all().delete()
            Place.objects.bulk_create(places, batch_size=2000)

        self.stdout.write(self.style.SUCCESS(f"Loaded {len(places)} places."))
