"""Tests for the main event, account and registration workflows."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.utils.timezone import localtime
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Event, Registration


class EventRegistrationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="sam", password="A-strong-test-password-984!")
        self.other_user = User.objects.create_user(
            username="lee", password="Another-strong-test-password-731!"
        )
        self.event = Event.objects.create(
            title="Django Workshop",
            description="A practical backend workshop.",
            venue="Central Library",
            event_date=timezone.now() + timedelta(days=7),
            capacity=2,
        )

    def test_signup_creates_account_and_signs_user_in(self):
        response = self.client.post(
            reverse("events:signup"),
            {
                "username": "new_attendee",
                "email": "attendee@example.com",
                "password1": "A-unique-password-for-tests-552!",
                "password2": "A-unique-password-for-tests-552!",
            },
        )
        self.assertRedirects(response, reverse("events:event_list"))
        created_user = User.objects.get(username="new_attendee")
        self.assertEqual(created_user.email, "attendee@example.com")
        self.assertIn("_auth_user_id", self.client.session)

    def test_user_can_log_in(self):
        response = self.client.post(
            reverse("login"),
            {"username": "sam", "password": "A-strong-test-password-984!"},
        )
        self.assertRedirects(response, reverse("events:event_list"))
        self.assertIn("_auth_user_id", self.client.session)

    def test_event_list_shows_upcoming_events_and_detail_loads(self):
        Event.objects.create(
            title="Earlier Meetup",
            description="Already happened.",
            venue="Town Hall",
            event_date=timezone.now() - timedelta(days=2),
            capacity=10,
        )
        response = self.client.get(reverse("events:event_list"))
        self.assertContains(response, "Django Workshop")
        self.assertNotContains(response, "Earlier Meetup")

        past_response = self.client.get(reverse("events:event_list"), {"status": "past"})
        self.assertContains(past_response, "Earlier Meetup")
        self.assertNotContains(past_response, "Django Workshop")

        detail_response = self.client.get(reverse("events:event_detail", args=[self.event.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "A practical backend workshop.")

    def test_authenticated_user_can_register_for_upcoming_event(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("events:register_event", args=[self.event.pk]))
        self.assertRedirects(response, reverse("events:event_detail", args=[self.event.pk]))
        self.assertTrue(Registration.objects.filter(user=self.user, event=self.event).exists())
        self.assertEqual(self.event.available_seats, 1)

    def test_duplicate_registration_is_prevented(self):
        self.client.force_login(self.user)
        url = reverse("events:register_event", args=[self.event.pk])
        self.client.post(url)
        self.client.post(url)
        self.assertEqual(Registration.objects.filter(user=self.user, event=self.event).count(), 1)

    def test_database_constraint_also_rejects_duplicate_registration(self):
        Registration.objects.create(user=self.user, event=self.event)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Registration.objects.create(user=self.user, event=self.event)

    def test_capacity_limit_prevents_registration(self):
        self.event.capacity = 1
        self.event.save()
        Registration.objects.create(user=self.user, event=self.event)

        self.client.force_login(self.other_user)
        self.client.post(reverse("events:register_event", args=[self.event.pk]))
        self.assertEqual(Registration.objects.filter(event=self.event).count(), 1)
        self.assertFalse(Registration.objects.filter(user=self.other_user, event=self.event).exists())

    def test_user_can_cancel_own_upcoming_registration(self):
        registration = Registration.objects.create(user=self.user, event=self.event)
        self.client.force_login(self.user)
        confirm_url = reverse("events:cancel_registration", args=[registration.pk])
        self.assertEqual(self.client.get(confirm_url).status_code, 200)
        response = self.client.post(confirm_url)
        self.assertRedirects(response, reverse("events:dashboard"))
        self.assertFalse(Registration.objects.filter(pk=registration.pk).exists())

    def test_user_cannot_cancel_another_users_registration(self):
        registration = Registration.objects.create(user=self.user, event=self.event)
        self.client.force_login(self.other_user)
        response = self.client.post(reverse("events:cancel_registration", args=[registration.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Registration.objects.filter(pk=registration.pk).exists())

    def test_past_event_registration_is_rejected(self):
        past_event = Event.objects.create(
            title="Past Event",
            description="No more registrations.",
            venue="Old Hall",
            event_date=timezone.now() - timedelta(hours=1),
            capacity=20,
        )
        self.client.force_login(self.user)
        self.client.post(reverse("events:register_event", args=[past_event.pk]))
        self.assertFalse(Registration.objects.filter(user=self.user, event=past_event).exists())

    def test_registration_dashboard_only_shows_current_users_events(self):
        Registration.objects.create(user=self.user, event=self.event)
        self.client.force_login(self.other_user)
        response = self.client.get(reverse("events:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Django Workshop")


class EventAdminPermissionTests(TestCase):
    def test_admin_requires_staff_access(self):
        url = reverse("admin:events_event_changelist")
        anonymous_response = self.client.get(url)
        self.assertEqual(anonymous_response.status_code, 302)

        attendee = User.objects.create_user(username="attendee", password="A-strong-password-123!")
        self.client.force_login(attendee)
        attendee_response = self.client.get(url)
        self.assertNotEqual(attendee_response.status_code, 200)

    def test_superuser_can_manage_events_in_admin(self):
        administrator = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="A-strong-admin-password-923!",
        )
        self.client.force_login(administrator)
        response = self.client.get(reverse("admin:events_event_add"))
        self.assertEqual(response.status_code, 200)

    def test_superuser_can_create_event_with_datetime_local_input(self):
        administrator = User.objects.create_superuser(
            username="event_admin",
            email="event_admin@example.com",
            password="A-strong-admin-password-714!",
        )
        self.client.force_login(administrator)
        event_date = localtime(timezone.now() + timedelta(days=4)).strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("admin:events_event_add"),
            {
                "title": "Admin Created Event",
                "description": "Created through the Django admin form.",
                "venue": "Test Hall",
                "event_date": event_date,
                "capacity": 25,
                "_save": "Save",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Event.objects.filter(title="Admin Created Event").exists())


class EventApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="api_user", password="A-strong-api-password-192!")
        self.other_user = User.objects.create_user(
            username="api_other", password="Another-strong-api-password-312!"
        )
        self.event = Event.objects.create(
            title="API Design Session",
            description="A session about reliable APIs.",
            venue="Community Hall",
            event_date=timezone.now() + timedelta(days=5),
            capacity=3,
        )

    def test_event_list_and_detail_return_json(self):
        list_response = self.client.get(reverse("events:api_event_list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["events"][0]["title"], "API Design Session")

        detail_response = self.client.get(reverse("events:api_event_detail", args=[self.event.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["event"]["available_seats"], 3)

    def test_api_registration_requires_authentication_and_saves_session_user(self):
        url = reverse("events:api_register_for_event", args=[self.event.pk])
        unauthenticated_response = self.client.post(url)
        self.assertEqual(unauthenticated_response.status_code, 401)

        self.client.force_login(self.user)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 201)
        registration = Registration.objects.get(event=self.event)
        self.assertEqual(registration.user, self.user)
        self.assertEqual(response.json()["registration"]["event"]["available_seats"], 2)

    def test_api_user_can_list_and_cancel_only_their_registration(self):
        own_registration = Registration.objects.create(user=self.user, event=self.event)
        other_registration = Registration.objects.create(user=self.other_user, event=self.event)
        self.client.force_login(self.user)

        response = self.client.get(reverse("events:api_my_registrations"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["upcoming"]), 1)
        self.assertEqual(response.json()["upcoming"][0]["id"], own_registration.pk)

        wrong_owner_response = self.client.delete(
            reverse("events:api_cancel_registration", args=[other_registration.pk])
        )
        self.assertEqual(wrong_owner_response.status_code, 404)
        self.assertTrue(Registration.objects.filter(pk=other_registration.pk).exists())

        cancel_response = self.client.delete(
            reverse("events:api_cancel_registration", args=[own_registration.pk])
        )
        self.assertEqual(cancel_response.status_code, 204)
        self.assertFalse(Registration.objects.filter(pk=own_registration.pk).exists())
