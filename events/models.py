"""Database models for events and user registrations."""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Event(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    venue = models.CharField(max_length=255)
    event_date = models.DateTimeField()
    capacity = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["event_date", "title"]

    def __str__(self):
        return self.title

    def clean(self):
        super().clean()
        errors = {}
        if self.capacity is not None and self.capacity < 1:
            errors["capacity"] = "Capacity must be at least one attendee."
        if self.event_date and timezone.is_naive(self.event_date):
            errors["event_date"] = "Enter a date and time with a valid timezone."
        if self.pk and self.capacity is not None:
            existing_count = self.registrations.count()
            if self.capacity < existing_count:
                errors["capacity"] = (
                    f"Capacity cannot be lower than the {existing_count} existing registration(s)."
                )
        if errors:
            raise ValidationError(errors)

    @property
    def registration_count(self):
        """Use an annotation when a view has provided one, otherwise count rows."""
        if hasattr(self, "_registration_count"):
            return self._registration_count
        if hasattr(self, "registration_count_value"):
            return self.registration_count_value
        return self.registrations.count()

    @property
    def available_seats(self):
        return max(self.capacity - self.registration_count, 0)

    @property
    def status(self):
        if self.event_date <= timezone.now():
            return "completed"
        if self.available_seats == 0:
            return "full"
        return "upcoming"


class Registration(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="event_registrations",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "event"],
                name="unique_user_event_registration",
            )
        ]

    def __str__(self):
        return f"{self.user} — {self.event}"

    def clean(self):
        super().clean()
        if not self.user_id or not self.event_id:
            return

        errors = {}
        if self.event.event_date <= timezone.now():
            errors["event"] = "You cannot register for an event that has already started."

        duplicate = Registration.objects.filter(user_id=self.user_id, event_id=self.event_id)
        if self.pk:
            duplicate = duplicate.exclude(pk=self.pk)
        if duplicate.exists():
            errors["event"] = "You are already registered for this event."

        registrations = self.event.registrations.count()
        if not self.pk and registrations >= self.event.capacity:
            errors["event"] = "This event has reached its capacity."

        if errors:
            raise ValidationError(errors)
