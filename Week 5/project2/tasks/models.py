from django.conf import settings
from django.db import models
from django.utils import timezone

from .themes import DEFAULT_THEME_KEY

POINTS_PER_TASK = 10


class Profile(models.Model):
    """Per-user app settings that don't belong on Django's built-in User model."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    openai_api_key = models.CharField(max_length=200, blank=True, default="")
    gemini_api_key = models.CharField(max_length=200, blank=True, default="")
    AI_PROVIDER_CHOICES = [
        ("openai", "OpenAI (ChatGPT)"),
        ("gemini", "Google Gemini"),
        ("local", "Local model (no API key, no cost)"),
    ]
    ai_provider = models.CharField(
        max_length=10, choices=AI_PROVIDER_CHOICES, default="openai"
    )
    points = models.PositiveIntegerField(default=0)
    active_theme = models.CharField(max_length=30, default=DEFAULT_THEME_KEY)
    unlocked_themes = models.CharField(
        max_length=200,
        default=DEFAULT_THEME_KEY,
        help_text="Comma-separated theme keys this user has unlocked.",
    )

    def __str__(self):
        return f"{self.user.username}'s profile"

    @staticmethod
    def _mask(key):
        """Last 4 characters only -- the real key is never shown back to the user."""
        if not key:
            return ""
        if len(key) <= 4:
            return "•" * len(key)
        return f"{'•' * 8}{key[-4:]}"

    @property
    def has_openai_key(self):
        return bool(self.openai_api_key)

    @property
    def has_gemini_key(self):
        return bool(self.gemini_api_key)

    @property
    def has_api_key(self):
        """True if the *currently selected* provider is ready to use: either
        it has a per-user key, or it's the local provider, which never needs one."""
        if self.ai_provider == "gemini":
            return self.has_gemini_key
        if self.ai_provider == "local":
            return True
        return self.has_openai_key

    def masked_api_key(self):
        return self._mask(self.openai_api_key)

    def masked_gemini_api_key(self):
        return self._mask(self.gemini_api_key)

    @property
    def active_provider_api_key(self):
        """The per-user key for whichever provider is currently selected, or ''.
        The local provider never uses a key, so it always returns ''."""
        if self.ai_provider == "gemini":
            return self.gemini_api_key
        if self.ai_provider == "local":
            return ""
        return self.openai_api_key

    @property
    def unlocked_theme_keys(self):
        return {key.strip() for key in self.unlocked_themes.split(",") if key.strip()}

    def unlock_theme(self, key):
        keys = self.unlocked_theme_keys
        keys.add(key)
        self.unlocked_themes = ",".join(sorted(keys))


class Task(models.Model):
    CATEGORY_CHOICES = [
        ("work", "Work"),
        ("personal", "Personal"),
        ("shopping", "Shopping"),
        ("health", "Health"),
        ("errands", "Errands"),
        ("other", "Other"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tasks",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    complete = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, blank=True, default=""
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["complete", "-created"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Figure out which direction (if any) the complete flag just flipped,
        # by comparing against what's currently in the database -- this works
        # no matter which view changed it (toggle button, edit form, admin).
        previous_complete = None
        if self.pk is not None:
            previous_complete = (
                Task.objects.filter(pk=self.pk).values_list("complete", flat=True).first()
            )

        became_complete = bool(self.complete) and not previous_complete
        became_incomplete = bool(previous_complete) and not self.complete

        # Keep completed_at in sync with complete regardless of which view
        # changed it.
        if became_complete:
            self.completed_at = timezone.now()
        elif became_incomplete:
            self.completed_at = None

        super().save(*args, **kwargs)

        # Points mirror the checkbox exactly: completing a task pays out 10
        # points, and un-completing it takes those 10 back (never dropping a
        # user's balance below zero). Resaving a task without changing
        # complete -- e.g. editing its title -- doesn't touch points either
        # way.
        if became_complete or became_incomplete:
            profile, _ = Profile.objects.get_or_create(user=self.user)
            if became_complete:
                profile.points += POINTS_PER_TASK
            else:
                profile.points = max(profile.points - POINTS_PER_TASK, 0)
            profile.save(update_fields=["points"])

    def get_category_display_or_default(self):
        return self.get_category_display() if self.category else "Uncategorized"
