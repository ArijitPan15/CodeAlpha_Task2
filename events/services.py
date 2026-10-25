"""Transactional business logic for event registration and cancellation."""
import time

from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import F
from django.utils import timezone

from .models import Event, Registration


class RegistrationError(Exception):
    """Base class for expected registration rule failures."""


class EventAlreadyPassed(RegistrationError):
    pass


class EventIsFull(RegistrationError):
    pass


class AlreadyRegistered(RegistrationError):
    pass


class RegistrationNotFound(RegistrationError):
    pass


class RegistrationBusy(RegistrationError):
    pass


def _lock_event_for_write(event):
    """Lock the event row while checking capacity.

    PostgreSQL and similar databases honor SELECT FOR UPDATE. SQLite ignores it,
    so a no-op UPDATE obtains SQLite's writer lock before counting registrations.
    This keeps the capacity check and insert in the same serialized transaction.
    """
    if connection.vendor == "sqlite":
        Event.objects.filter(pk=event.pk).update(capacity=F("capacity"))
        event.refresh_from_db(fields=["capacity"])


def register_user_for_event(*, user, event_id):
    """Create one registration if the event is open and has a free seat."""
    for attempt in range(4):
        try:
            return _register_once(user=user, event_id=event_id)
        except OperationalError as exc:
            # SQLite can reject a deferred transaction upgrade when two
            # requests read the same event before either obtains the writer
            # lock. Retry the full transaction so the next attempt recounts.
            is_sqlite_lock = connection.vendor == "sqlite" and "locked" in str(exc).lower()
            if not is_sqlite_lock:
                raise
            if attempt == 3:
                raise RegistrationBusy from exc
            time.sleep(0.05 * (attempt + 1))


def _register_once(*, user, event_id):
    try:
        with transaction.atomic():
            event = Event.objects.select_for_update().get(pk=event_id)
            _lock_event_for_write(event)

            if event.event_date <= timezone.now():
                raise EventAlreadyPassed
            if Registration.objects.filter(user=user, event=event).exists():
                raise AlreadyRegistered
            if event.registrations.count() >= event.capacity:
                raise EventIsFull

            try:
                return Registration.objects.create(user=user, event=event)
            except IntegrityError as exc:
                # The database unique constraint is the final guard against two
                # simultaneous requests from the same user.
                raise AlreadyRegistered from exc
    except IntegrityError as exc:
        # An IntegrityError marks its transaction as broken; translate it only
        # after atomic() has rolled back and the connection is usable again.
        if Registration.objects.filter(user=user, event_id=event_id).exists():
            raise AlreadyRegistered from exc
        raise


def cancel_user_registration(*, user, registration_id):
    """Delete a user's own registration while the event is still upcoming."""
    with transaction.atomic():
        try:
            registration = Registration.objects.select_related("event").get(
                pk=registration_id,
                user=user,
            )
        except Registration.DoesNotExist as exc:
            raise RegistrationNotFound from exc

        event = Event.objects.select_for_update().get(pk=registration.event_id)
        _lock_event_for_write(event)
        if event.event_date <= timezone.now():
            raise EventAlreadyPassed
        registration.delete()
