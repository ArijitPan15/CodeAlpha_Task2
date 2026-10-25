from django.urls import path

from . import api, views


app_name = "events"

urlpatterns = [
    path("api/events/", api.event_list, name="api_event_list"),
    path("api/events/<int:pk>/", api.event_detail, name="api_event_detail"),
    path("api/events/<int:pk>/registrations/", api.register_for_event, name="api_register_for_event"),
    path("api/registrations/", api.my_registrations, name="api_my_registrations"),
    path("api/registrations/<int:pk>/", api.cancel_registration, name="api_cancel_registration"),
    path("", views.event_list, name="event_list"),
    path("events/<int:pk>/", views.event_detail, name="event_detail"),
    path("events/<int:pk>/register/", views.register_event, name="register_event"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("registrations/<int:pk>/cancel/", views.cancel_registration, name="cancel_registration"),
    path("accounts/signup/", views.signup, name="signup"),
]
