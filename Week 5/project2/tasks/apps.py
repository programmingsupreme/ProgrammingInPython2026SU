"""App configuration for the tasks app.

Also handles an optional startup optimization: loading the local AI quick-add
model (see tasks/ai.py) is slow -- a multi-second load even from cache, or a
~2GB download the very first time -- and without this, that cost lands on
whichever user happens to submit the first local-provider quick-add after the
server starts. Instead, ready() kicks off that load in a background thread at
startup, but only when it's actually worth doing: only if some user has the
local provider selected at all, and never during management commands (tests,
migrations, etc.) that aren't really starting a server.
"""
import os
import sys
import threading
import warnings

from django.apps import AppConfig

# Management commands that load the app registry without starting a server
# -- never worth touching the database or loading a model for these.
SKIP_WARMUP_COMMANDS = {
    "test", "migrate", "makemigrations", "collectstatic", "shell",
    "shell_plus", "createsuperuser", "dbshell", "check",
}


def _is_reloader_watcher_process():
    """True only for `runserver`'s outer file-watching process. With the
    autoreloader on (the default), Django's ready() runs once in that outer
    watcher and again in the subprocess that actually serves requests (which
    has RUN_MAIN=true) -- skip the watcher so the warm-up doesn't start
    twice. Not true for --noreload (no watcher/subprocess split) or for
    production runs that don't go through `runserver` at all."""
    if "runserver" not in sys.argv:
        return False
    if "--noreload" in sys.argv:
        return False
    return os.environ.get("RUN_MAIN") != "true"


def _any_local_provider_profile_exists():
    """True if at least one user currently has the local provider selected.
    Returns False (rather than raising) if the database isn't ready to be
    queried yet -- e.g. migrations haven't been applied -- since there's
    nothing to warm up for in that case either way."""
    from .models import Profile

    try:
        # Django warns that DB access during app initialization is
        # discouraged (other apps' ready() may not have run yet). We've
        # confirmed Profile/tasks have nothing left to initialize at this
        # point, so the one-off query here is safe; just keep the console
        # quiet about it.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            return Profile.objects.filter(ai_provider="local").exists()
    except Exception:
        return False


def _maybe_warm_local_model():
    if len(sys.argv) > 1 and sys.argv[1] in SKIP_WARMUP_COMMANDS:
        return
    if _is_reloader_watcher_process():
        return
    if not _any_local_provider_profile_exists():
        return

    from . import ai

    threading.Thread(target=ai._get_local_llm, daemon=True).start()


class TasksConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tasks'

    def ready(self):
        from . import signals  # noqa: F401  (registers the user_signed_up receiver)
        _maybe_warm_local_model()
