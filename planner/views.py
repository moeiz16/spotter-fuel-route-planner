from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import PlannerError
from .serializers import TripPlanSerializer, TripQuerySerializer
from .services.trips import plan_trip


class RouteView(APIView):
    """GET /api/v1/route/?start=...&finish=...

    Returns the driving route, where to stop for fuel and what it will cost.
    """

    @extend_schema(
        summary="Plan a route with fuel stops",
        parameters=[TripQuerySerializer],
        responses={
            200: TripPlanSerializer,
            400: OpenApiResponse(
                description="Missing parameter, or location not found or outside the US"
            ),
            422: OpenApiResponse(
                description="No route, or no fuel station within range on part of it"
            ),
            502: OpenApiResponse(description="Routing or geocoding service unavailable"),
        },
        examples=[
            OpenApiExample(
                "City names",
                value={"start": "Chicago, IL", "finish": "Miami, FL"},
                request_only=True,
            ),
        ],
    )
    def get(self, request):
        query = TripQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)

        try:
            plan = plan_trip(**query.validated_data)
        except PlannerError as exc:
            return Response({"detail": str(exc)}, status=exc.status_code)

        data = TripPlanSerializer(plan).data
        map_path = reverse("planner:route-map") + "?" + urlencode(query.validated_data)
        data["map_url"] = request.build_absolute_uri(map_path)
        return Response(data)


def route_map(request):
    """The same plan drawn on a map. With no parameters it just shows the form."""
    context = {"start": request.GET.get("start", ""), "finish": request.GET.get("finish", "")}
    if not request.GET:
        return render(request, "planner/map.html", context)

    query = TripQuerySerializer(data=request.GET)
    if not query.is_valid():
        context["error"] = "Enter both a start and a finish location."
        return render(request, "planner/map.html", context, status=400)

    try:
        plan = plan_trip(**query.validated_data)
    except PlannerError as exc:
        context["error"] = str(exc)
        return render(request, "planner/map.html", context, status=exc.status_code)

    context["plan"] = TripPlanSerializer(plan).data
    return render(request, "planner/map.html", context)
