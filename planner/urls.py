from django.urls import path

from . import views

app_name = "planner"

urlpatterns = [
    path("route/", views.RouteView.as_view(), name="route"),
    path("route/map/", views.route_map, name="route-map"),
]
