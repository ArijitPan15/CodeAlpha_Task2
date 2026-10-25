"""JSON API endpoints for event discovery and attendee registrations."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Event, Registration
from .services import (
    AlreadyRegistered,
    EventAlreadyPassed,
    EventIsFull,
    RegistrationBusy,
    RegistrationNotFound,
    cancel_user_registration,
    register_user_for_event,
)


def api_login_required(view_func):
    """Return a JSON 401 response instead of redirecting API clients to HTML."""

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication is required.", "code": "authentication_required"},
                status=401,
            )
        return view_func(request, *args, **kwargs)

    return wrapped


def _event_data(event, registration_count=None):
    count = event.registration_count if registration_count is None else registration_count
    seats_left = max(event.capacity - count, 0)
    if event.event_date <= timezone.now():
        status = "completed"
    elif seats_left == 0:
        status = "full"
    else:
        status = "upcoming"

    return {
        "id": event.pk,
        "title": event.title,
        "description": event.description,
        "venue": event.venue,
        "event_date": event.event_date.isoformat(),
        "capacity": event.capacity,
        "registered_count": count,
        "available_seats": seats_left,
        "status": status,
    }


def _registration_data(registration, registration_count=None):
    return {
        "id": registration.pk,
        "registered_at": registration.registered_at.isoformat(),
        "status": "completed" if registration.event.event_date <= timezone.now() else "registered",
        "event": _event_data(registration.event, registration_count),
    }


def _api_error(message, code, status):
    return JsonResponse({"error": message, "code": code}, status=status)


@require_GET
def event_list(request):
    """GET /api/events/ — return searchable events as JSON."""
    now = timezone.now()
    status_filter = request.GET.get("status", "upcoming")
    if status_filter not in {"upcoming", "past", "all"}:
        return _api_error("Use upcoming, past, or all for status.", "invalid_status", 400)

    events = Event.objects.annotate(_registration_count=Count("registrations"))
    if status_filter == "upcoming":
        events = events.filter(event_date__gt=now)
    elif status_filter == "past":
        events = events.filter(event_date__lte=now)

    query = request.GET.get("q", "").strip()
    if query:
        events = events.filter(Q(title__icontains=query) | Q(description__icontains=query))

    return JsonResponse(
        {"events": [_event_data(event, event._registration_count) for event in events]},
    )


@require_GET
def event_detail(request, pk):
    """GET /api/events/<id>/ — return one event or a JSON 404."""
    try:
        event = Event.objects.annotate(_registration_count=Count("registrations")).get(pk=pk)
    except Event.DoesNotExist:
        return _api_error("That event could not be found.", "event_not_found", 404)
    return JsonResponse({"event": _event_data(event, event._registration_count)})


@require_POST
@api_login_required
def register_for_event(request, pk):
    """POST /api/events/<id>/registrations/ — register the session user."""
    try:
        registration = register_user_for_event(user=request.user, event_id=pk)
    except Event.DoesNotExist:
        return _api_error("That event could not be found.", "event_not_found", 404)
    except AlreadyRegistered:
        return _api_error("You are already registered for this event.", "already_registered", 409)
    except EventIsFull:
        return _api_error("This event has reached capacity.", "event_full", 409)
    except EventAlreadyPassed:
        return _api_error("Registration is closed because this event has passed.", "event_passed", 409)
    except RegistrationBusy:
        return _api_error("Registration is busy. Please retry shortly.", "registration_busy", 503)

    event = Event.objects.annotate(_registration_count=Count("registrations")).get(pk=pk)
    return JsonResponse(
        {"registration": _registration_data(registration, event._registration_count)},
        status=201,
    )


@require_GET
@api_login_required
def my_registrations(request):
    """GET /api/registrations/ — return only the signed-in user's registrations."""
    registrations = list(
        Registration.objects.filter(user=request.user)
        .select_related("event")
        .annotate(_event_registration_count=Count("event__registrations"))
        .order_by("event__event_date")
    )
    now = timezone.now()
    upcoming = [r for r in registrations if r.event.event_date > now]
    past = [r for r in registrations if r.event.event_date <= now]

    return JsonResponse(
        {
            "upcoming": [
                _registration_data(r, r._event_registration_count) for r in upcoming
            ],
            "past": [_registration_data(r, r._event_registration_count) for r in past],
        }
    )


@require_http_methods(["DELETE"])
@api_login_required
def cancel_registration(request, pk):
    """DELETE /api/registrations/<id>/ — cancel only the caller's registration."""
    try:
        cancel_user_registration(user=request.user, registration_id=pk)
    except RegistrationNotFound:
        return _api_error("That registration could not be found.", "registration_not_found", 404)
    except EventAlreadyPassed:
        return _api_error("A past event registration cannot be cancelled.", "event_passed", 409)

    return HttpResponse(status=204)
