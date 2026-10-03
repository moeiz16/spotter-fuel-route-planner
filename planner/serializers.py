from django.conf import settings
from rest_framework import serializers


class TripQuerySerializer(serializers.Serializer):
    start = serializers.CharField(max_length=200)
    finish = serializers.CharField(max_length=200)


class CoordinateField(serializers.FloatField):
    def to_representation(self, value):
        return round(float(value), 5)


class LocationSerializer(serializers.Serializer):
    name = serializers.CharField()
    latitude = CoordinateField()
    longitude = CoordinateField()


class FuelStopSerializer(serializers.Serializer):
    opis_id = serializers.IntegerField(source="station.opis_id")
    name = serializers.CharField(source="station.name")
    address = serializers.CharField(source="station.address")
    city = serializers.CharField(source="station.city")
    state = serializers.CharField(source="station.state")
    latitude = CoordinateField(source="station.latitude")
    longitude = CoordinateField(source="station.longitude")
    mile_marker = serializers.SerializerMethodField()
    miles_off_route = serializers.SerializerMethodField()
    # Amounts are Decimals rounded by the planner; they go out as plain JSON numbers.
    price_per_gallon = serializers.FloatField(source="station.price")
    gallons = serializers.FloatField()
    cost = serializers.FloatField()

    def get_mile_marker(self, stop) -> float:
        return round(stop.station.mile, 1)

    def get_miles_off_route(self, stop) -> float:
        return round(stop.station.off_route_miles, 1)


class RouteSerializer(serializers.Serializer):
    distance_miles = serializers.SerializerMethodField()
    duration_hours = serializers.SerializerMethodField()
    geometry = serializers.SerializerMethodField()

    def get_distance_miles(self, route) -> float:
        return round(route.distance_miles, 1)

    def get_duration_hours(self, route) -> float:
        return round(route.duration_seconds / 3600, 2)

    def get_geometry(self, route) -> dict:
        # GeoJSON puts longitude first.
        coordinates = [[round(lon, 5), round(lat, 5)] for lat, lon in route.outline().tolist()]
        return {"type": "LineString", "coordinates": coordinates}


class TripPlanSerializer(serializers.Serializer):
    start = LocationSerializer()
    finish = LocationSerializer()
    route = RouteSerializer()
    fuel_stops = FuelStopSerializer(many=True)
    total_gallons = serializers.FloatField()
    total_fuel_cost = serializers.FloatField()
    vehicle = serializers.SerializerMethodField()

    def get_vehicle(self, plan) -> dict:
        return {
            "range_miles": settings.VEHICLE_RANGE_MILES,
            "miles_per_gallon": settings.VEHICLE_MPG,
            "starts_with_full_tank": True,
        }
