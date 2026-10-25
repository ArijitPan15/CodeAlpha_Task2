"""Django admin configuration for events and registrations."""
from django.contrib import admin
from django.db.models import Count

from .forms import EventAdminForm
from .models import Event, Registration


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    form = EventAdminForm
    list_display = ("title", "venue", "event_date", "capacity", "registered_count", "available_count")
    list_filter = ("event_date", "created_at")
    search_fields = ("title", "description", "venue")
    date_hierarchy = "event_date"
    ordering = ("event_date",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_admin_registration_count=Count("registrations"))

    @admin.display(description="Registered", ordering="_admin_registration_count")
    def registered_count(self, obj):
        return obj._admin_registration_count

    @admin.display(description="Seats remaining")
    def available_count(self, obj):
        return max(obj.capacity - obj._admin_registration_count, 0)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("user", "event", "registered_at")
    list_filter = ("registered_at", "event__event_date")
    search_fields = ("user__username", "user__email", "event__title")
    date_hierarchy = "registered_at"
    readonly_fields = ("registered_at",)
    autocomplete_fields = ("user", "event")
