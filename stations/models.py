import re

from django.db import models


def place_key(name):
    """Collapse a town name to a lookup key: 'De Forest' and 'DeForest' both -> 'deforest'."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


class Place(models.Model):
    """A US town or city with a representative coordinate.

    Used to put fuel stations on the map (the price list has no coordinates)
    and to resolve "City, ST" inputs without calling a geocoding API.
    """

    name = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    key = models.CharField(max_length=100, editable=False)
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["state", "key"], name="unique_place_per_state"),
        ]

    def __str__(self):
        return f"{self.name}, {self.state}"

    def save(self, *args, **kwargs):
        self.key = place_key(self.name)
        super().save(*args, **kwargs)


class FuelStation(models.Model):
    opis_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=150)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=2)
    rack_id = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=6, decimal_places=3, help_text="USD per gallon")
    latitude = models.FloatField()
    longitude = models.FloatField()

    class Meta:
        ordering = ["opis_id"]

    def __str__(self):
        return f"{self.name} ({self.city}, {self.state})"
