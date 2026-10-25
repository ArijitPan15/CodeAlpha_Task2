"""Forms and shared Bootstrap styling for the event application."""
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import Event


class BootstrapFormMixin:
    """Apply consistent Bootstrap classes to all rendered form controls."""

    def apply_bootstrap_classes(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                css_class = "form-check-input"
            elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css_class = "form-select"
            else:
                css_class = "form-control"
            current = widget.attrs.get("class", "")
            widget.attrs["class"] = f"{current} {css_class}".strip()


class SignupForm(BootstrapFormMixin, UserCreationForm):
    email = forms.EmailField(required=False, help_text="Optional; used for account contact details.")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()
        self.fields["username"].help_text = "Choose a username for your account."


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={"autofocus": True, "autocomplete": "username"})
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()


class EventAdminForm(BootstrapFormMixin, forms.ModelForm):
    event_date = forms.DateTimeField(
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"],
        widget=forms.DateTimeInput(
            format="%Y-%m-%dT%H:%M",
            attrs={"type": "datetime-local"},
        ),
    )

    class Meta:
        model = Event
        fields = ["title", "description", "venue", "event_date", "capacity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apply_bootstrap_classes()

    def clean_capacity(self):
        capacity = self.cleaned_data["capacity"]
        if capacity < 1:
            raise forms.ValidationError("Capacity must be at least one attendee.")
        if self.instance.pk:
            registration_count = self.instance.registrations.count()
            if capacity < registration_count:
                raise forms.ValidationError(
                    f"Capacity cannot be lower than the {registration_count} existing registration(s)."
                )
        return capacity
