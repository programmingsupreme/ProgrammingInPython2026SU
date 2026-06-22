import os

from .models import Profile
from .themes import get_theme


def google_oauth(request):
    """Expose whether Google sign-in is configured, so login/register
    templates can show or hide the "Sign in with Google" button without
    erroring out when GOOGLE_OAUTH_CLIENT_ID/SECRET aren't set in .env."""
    return {
        "google_oauth_enabled": bool(os.environ.get("GOOGLE_OAUTH_CLIENT_ID"))
        and bool(os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET"))
    }


def active_theme(request):
    """Expose the logged-in user's active theme info + points balance to every
    template, so base.html can link the right (fetched, not hardcoded) theme
    stylesheet and show the points badge without every view passing it along."""
    if not request.user.is_authenticated:
        return {}

    profile = Profile.objects.filter(user=request.user).first()
    if profile is None:
        return {}

    return {
        "active_theme": get_theme(profile.active_theme),
        "user_points": profile.points,
    }
