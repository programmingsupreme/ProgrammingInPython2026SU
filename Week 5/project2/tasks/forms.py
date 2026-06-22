import calendar

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Task

# ---------------------------------------------------------------------------
# Due-date picker: plain Month / Day / Year / Hour / Minute / AM-PM <select>
# dropdowns standing in for a single datetime-local input.
# ---------------------------------------------------------------------------


def _blank(label):
    return [("", label)]


def _month_choices():
    return _blank("Month") + [(i, calendar.month_name[i]) for i in range(1, 13)]


def _day_choices():
    return _blank("Day") + [(d, d) for d in range(1, 32)]


def _year_choices():
    current_year = timezone.localtime(timezone.now()).year
    return _blank("Year") + [(y, y) for y in range(current_year - 1, current_year + 6)]


def _hour_choices():
    return _blank("Hour") + [(h, h) for h in range(1, 13)]


def _minute_choices():
    return _blank("Min") + [(m, f"{m:02d}") for m in range(60)]


def _ampm_choices():
    return _blank("--") + [("AM", "AM"), ("PM", "PM")]


class DateTimeSelectWidget(forms.MultiWidget):
    """Six <select> dropdowns -- Month, Day, Year, Hour, Minute, AM/PM."""

    def __init__(self, attrs=None):
        select_attrs = {**(attrs or {}), "class": "datetime-select"}
        widgets = [
            forms.Select(attrs=select_attrs, choices=_month_choices()),
            forms.Select(attrs=select_attrs, choices=_day_choices()),
            forms.Select(attrs=select_attrs, choices=_year_choices()),
            forms.Select(attrs=select_attrs, choices=_hour_choices()),
            forms.Select(attrs=select_attrs, choices=_minute_choices()),
            forms.Select(attrs=select_attrs, choices=_ampm_choices()),
        ]
        super().__init__(widgets, attrs)

    def decompress(self, value):
        if not value:
            return [None, None, None, None, None, None]
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        hour12 = value.hour % 12 or 12
        ampm = "AM" if value.hour < 12 else "PM"
        return [value.month, value.day, value.year, hour12, value.minute, ampm]


class DateTimeSelectField(forms.MultiValueField):
    """Combines the six dropdowns into one optional aware datetime, or None
    if every part is left blank."""

    def __init__(self, **kwargs):
        fields = (
            forms.ChoiceField(choices=_month_choices(), required=False),
            forms.ChoiceField(choices=_day_choices(), required=False),
            forms.ChoiceField(choices=_year_choices(), required=False),
            forms.ChoiceField(choices=_hour_choices(), required=False),
            forms.ChoiceField(choices=_minute_choices(), required=False),
            forms.ChoiceField(choices=_ampm_choices(), required=False),
        )
        kwargs.setdefault("widget", DateTimeSelectWidget)
        kwargs.setdefault("require_all_fields", False)
        super().__init__(fields, **kwargs)

    def compress(self, data_list):
        if not data_list:
            return None

        month, day, year, hour, minute, ampm = data_list
        date_parts = [month, day, year]
        if not any(date_parts):
            return None
        if not all(date_parts):
            raise forms.ValidationError(
                "Pick a month, day, and year, or leave the date blank."
            )

        hour = int(hour) if hour else 12
        minute = int(minute) if minute else 0
        ampm = ampm or "AM"
        if ampm == "PM" and hour != 12:
            hour += 12
        elif ampm == "AM" and hour == 12:
            hour = 0

        try:
            naive = timezone.datetime(int(year), int(month), int(day), hour, minute)
        except ValueError:
            raise forms.ValidationError("That's not a valid date.")

        return naive if timezone.is_aware(naive) else timezone.make_aware(naive)


# ---------------------------------------------------------------------------
# Task form
# ---------------------------------------------------------------------------


class TaskForm(forms.ModelForm):
    due_date = DateTimeSelectField(required=False, label="Due date")
    category = forms.ChoiceField(
        required=False,
        choices=[("", "Uncategorized")] + Task.CATEGORY_CHOICES,
        help_text="AI quick-add fills this in automatically -- set it manually here if you like.",
    )

    class Meta:
        model = Task
        fields = ["title", "description", "due_date", "category", "complete"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "What needs to be done?"}),
            "description": forms.Textarea(attrs={"rows": 3, "placeholder": "Details (optional)"}),
        }


class QuickAddForm(forms.Form):
    """A single free-text field that gets sent to the AI parser."""

    text = forms.CharField(
        max_length=500,
        widget=forms.TextInput(
            attrs={"placeholder": "Try: remind me to call mom tomorrow at 5pm"}
        ),
    )


# ---------------------------------------------------------------------------
# Account / API key forms
# ---------------------------------------------------------------------------


class RegisterForm(UserCreationForm):
    """Standard Django registration plus optional OpenAI/Gemini API keys and
    a preferred-provider choice, so a new user can have AI quick-add working
    immediately if they want."""

    ai_provider = forms.ChoiceField(
        choices=[
            ("openai", "OpenAI (ChatGPT)"),
            ("gemini", "Google Gemini"),
            ("local", "Local model (no API key, no cost)"),
        ],
        initial="openai",
        label="Preferred AI provider",
        help_text="Which AI quick-add should use -- you can change this anytime from Settings.",
    )
    openai_api_key = forms.CharField(
        required=False,
        label="OpenAI API key (optional)",
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"placeholder": "sk-... (optional)", "autocomplete": "off"},
        ),
    )
    gemini_api_key = forms.CharField(
        required=False,
        label="Gemini API key (optional)",
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"placeholder": "AIza... (optional)", "autocomplete": "off"},
        ),
        help_text=(
            "Add a key for whichever provider you picked above to use AI quick-add "
            "right away. You can add, change, or remove either key anytime later "
            "from Settings."
        ),
    )

    class Meta(UserCreationForm.Meta):
        model = User


class AIProviderForm(forms.Form):
    """Used on the account settings page to switch the preferred AI provider."""

    ai_provider = forms.ChoiceField(
        choices=[
            ("openai", "OpenAI (ChatGPT)"),
            ("gemini", "Google Gemini"),
            ("local", "Local model (no API key, no cost)"),
        ],
        label="Preferred AI provider",
    )


class OpenAIKeyForm(forms.Form):
    """Used on the account settings page to add or update the stored OpenAI key."""

    openai_api_key = forms.CharField(
        required=True,
        label="OpenAI API key",
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"placeholder": "sk-...", "autocomplete": "off"},
        ),
    )


class GeminiKeyForm(forms.Form):
    """Used on the account settings page to add or update the stored Gemini key."""

    gemini_api_key = forms.CharField(
        required=True,
        label="Gemini API key",
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"placeholder": "AIza...", "autocomplete": "off"},
        ),
    )
