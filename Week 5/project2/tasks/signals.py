"""Signal receivers for the tasks app.

Mirrors what the password-based register() view does explicitly: make sure
every new user ends up with a Profile right away, including users who sign
up via "Sign in with Google" (allauth) rather than our own register form.
"""
from allauth.account.signals import user_signed_up
from django.dispatch import receiver

from .models import Profile


@receiver(user_signed_up)
def create_profile_for_new_signup(request, user, **kwargs):
    """Fires for every new signup allauth handles (e.g. a first-time Google
    sign-in). Our own register() view already creates a Profile directly, so
    this is mainly a safety net for the social-login path -- get_or_create
    keeps it harmless if a Profile somehow already exists."""
    Profile.objects.get_or_create(user=user)
