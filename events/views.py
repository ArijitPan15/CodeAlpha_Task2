"""Request handlers for event browsing, accounts and registrations."""
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from .forms import SignupForm
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


def event_list(request):
    now = timezone.now()
    status_filter = request.GET.get("status", "upcoming")
    if status_filter not in {"upcoming", "past", "all"}:
        status_filter = "upcoming"

    events = Event.objects.annotate(_registration_count=Count("registrations"))
    if status_filter == "upcoming":
        events = events.filter(event_date__gt=now)
    elif status_filter == "past":
        events = events.filter(event_date__lte=now)

    query = request.GET.get("q", "").strip()
    if query:
        events = events.filter(Q(title__icontains=query) | Q(description__icontains=query))

    return render(
        request,
        "events/event_list.html",
        {"events": events, "query": query, "status_filter": status_filter},
    )


def event_detail(request, pk):
    event = get_object_or_404(
        Event.objects.annotate(_registration_count=Count("registrations")),
        pk=pk,
    )
    registration = None
    if request.user.is_authenticated:
        registration = Registration.objects.filter(user=request.user, event=event).first()
    return render(
        request,
        "events/event_detail.html",
        {"event": event, "registration": registration},
    )


@login_required
@require_POST
def register_event(request, pk):
    try:
        registration = register_user_for_event(user=request.user, event_id=pk)
    except Event.DoesNotExist:
        messages.error(request, "That event could not be found.")
        return redirect("events:event_list")
    except AlreadyRegistered:
        messages.warning(request, "You are already registered for this event.")
    except EventIsFull:
        messages.error(request, "This event is full, so registration is closed.")
    except EventAlreadyPassed:
        messages.error(request, "Registration is closed because this event has passed.")
    except RegistrationBusy:
        messages.warning(request, "Registrations are busy right now. Please try again in a moment.")
    else:
        messages.success(request, f"You are registered for {registration.event.title}.")
    return redirect("events:event_detail", pk=pk)


@login_required
def dashboard(request):
    registrations = list(
        Registration.objects.filter(user=request.user)
        .select_related("event")
        .order_by("event__event_date")
    )
    now = timezone.now()
    upcoming_registrations = [r for r in registrations if r.event.event_date > now]
    past_registrations = [r for r in registrations if r.event.event_date <= now]
    return render(
        request,
        "events/dashboard.html",
        {
            "upcoming_registrations": upcoming_registrations,
            "past_registrations": past_registrations,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def cancel_registration(request, pk):
    # Scoping the lookup by user prevents another attendee's registration from
    # being displayed or changed by guessing its numeric URL.
    registration = get_object_or_404(
        Registration.objects.select_related("event"),
        pk=pk,
        user=request.user,
    )
    if request.method == "POST":
        try:
            cancel_user_registration(user=request.user, registration_id=pk)
        except RegistrationNotFound:
            messages.error(request, "That registration could not be found.")
        except EventAlreadyPassed:
            messages.error(request, "A registration cannot be cancelled after the event has passed.")
        else:
            messages.success(request, f"Your registration for {registration.event.title} was cancelled.")
        return redirect("events:dashboard")

    return render(
        request,
        "events/cancel_registration.html",
        {"registration": registration, "now": timezone.now()},
    )


def signup(request):
    if request.user.is_authenticated:
        return redirect("events:event_list")
    form = SignupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        auth_login(request, user)
        messages.success(request, "Your account is ready. You are now signed in.")
        return redirect("events:event_list")
    return render(request, "registration/signup.html", {"form": form})
