class PlannerError(Exception):
    """Base class for anything that stops a trip from being planned.

    ``status_code`` is the HTTP status the API should answer with.
    """

    status_code = 400


class LocationNotFound(PlannerError):
    pass


class RouteNotFound(PlannerError):
    status_code = 422


class FuelPlanNotPossible(PlannerError):
    status_code = 422


class UpstreamServiceError(PlannerError):
    status_code = 502
