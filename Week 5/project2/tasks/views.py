from itertools import groupby

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.html import format_html
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from .ai import AIParseError, has_configured_key, local_runtime_available, parse_task_text
from .forms import (
    AIProviderForm,
    GeminiKeyForm,
    OpenAIKeyForm,
    RegisterForm,
    TaskForm,
)
from .models import Profile, Task
from .themes import THEMES, get_theme, is_valid_theme_key


class OwnedQuerysetMixin(LoginRequiredMixin):
    """Restrict any ListView/UpdateView/DeleteView to the logged-in user's own tasks."""

    def get_queryset(self):
        return super().get_queryset().filter(user=self.request.user)


class TaskListView(OwnedQuerysetMixin, ListView):
    model = Task
    template_name = "tasks/task_list.html"
    context_object_name = "tasks"


class TaskCreateView(LoginRequiredMixin, CreateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("task-list")

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)


class TaskUpdateView(OwnedQuerysetMixin, UpdateView):
    model = Task
    form_class = TaskForm
    template_name = "tasks/task_form.html"
    success_url = reverse_lazy("task-list")


class TaskDeleteView(OwnedQuerysetMixin, DeleteView):
    model = Task
    template_name = "tasks/task_confirm_delete.html"
    success_url = reverse_lazy("task-list")


@login_required
def toggle_complete(request, pk):
    """Flip a task's complete flag. Looking it up scoped to request.user prevents
    a user from toggling someone else's task by guessing the URL."""
    task = get_object_or_404(Task, pk=pk, user=request.user)
    task.complete = not task.complete
    task.save()
    return redirect("task-list")


@login_required
@require_POST
def quick_add_task(request):
    """Create a task from a single free-text note using whichever AI provider
    (OpenAI or Gemini) the user has selected.

    If AI parsing isn't available (no key, network issue, bad response) we
    don't lose the user's input -- we just save it verbatim as the title.
    """
    text = request.POST.get("text", "").strip()
    if not text:
        messages.error(request, "Type something before adding a task.")
        return redirect("task-list")

    profile = Profile.objects.filter(user=request.user).first()
    provider = profile.ai_provider if profile else "openai"
    api_key = profile.active_provider_api_key if profile else ""

    try:
        parsed = parse_task_text(text, provider=provider, api_key=api_key or None)
        Task.objects.create(
            user=request.user,
            title=parsed["title"],
            description=parsed["description"],
            due_date=parsed["due_date"],
            category=parsed.get("category", ""),
        )
        messages.success(request, "Task added.")
    except AIParseError as exc:
        Task.objects.create(user=request.user, title=text[:200])
        if not has_configured_key(provider, api_key):
            provider_label = "Gemini" if provider == "gemini" else "OpenAI"
            article = "an" if provider_label[:1] in "AEIOU" else "a"
            messages.warning(
                request,
                format_html(
                    "Saved as plain text — "
                    '<a href="{}">add {} {} API key</a> to use the AI quick-add feature.',
                    reverse("account-settings"),
                    article,
                    provider_label,
                ),
            )
        else:
            messages.warning(request, f"Saved as plain text — AI parsing failed ({exc}).")

    return redirect("task-list")


@login_required
def task_calendar(request):
    """Show all completed tasks grouped by the day they were completed,
    each with the time of completion."""
    completed_tasks = (
        Task.objects.filter(user=request.user, complete=True, completed_at__isnull=False)
        .order_by("-completed_at")
    )

    days = [
        {"date": day, "tasks": list(tasks)}
        for day, tasks in groupby(
            completed_tasks, key=lambda t: t.completed_at.astimezone().date()
        )
    ]

    return render(request, "tasks/calendar.html", {"days": days})


@login_required
def task_lists(request):
    """Show tasks grouped by their AI-assigned (or manually set) category."""
    user_tasks = Task.objects.filter(user=request.user)

    category_labels = dict(Task.CATEGORY_CHOICES)
    groups = {key: [] for key, _ in Task.CATEGORY_CHOICES}
    groups[""] = []

    for task in user_tasks:
        groups.setdefault(task.category, []).append(task)

    ordered_keys = [key for key, _ in Task.CATEGORY_CHOICES] + [""]
    lists = [
        {
            "key": key,
            "label": category_labels.get(key, "Uncategorized"),
            "tasks": groups[key],
        }
        for key in ordered_keys
        if groups[key]
    ]

    return render(request, "tasks/lists.html", {"lists": lists})


def register(request):
    if request.user.is_authenticated:
        return redirect("task-list")

    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            openai_key = form.cleaned_data.get("openai_api_key", "").strip()
            gemini_key = form.cleaned_data.get("gemini_api_key", "").strip()
            provider = form.cleaned_data.get("ai_provider", "openai")
            Profile.objects.create(
                user=user,
                openai_api_key=openai_key,
                gemini_api_key=gemini_key,
                ai_provider=provider,
            )
            # Now that allauth's social backend is also configured (for
            # "Sign in with Google"), Django has multiple auth backends and
            # needs to be told which one authenticated this user -- this was
            # plain password auth, so that's ModelBackend.
            login(request, user, backend="django.contrib.auth.backends.ModelBackend")
            if provider == "local":
                messages.success(
                    request,
                    "Account created. AI quick-add will use a local model — no API key "
                    "needed, though the first request may take a bit longer while it "
                    "downloads.",
                )
            else:
                active_key = gemini_key if provider == "gemini" else openai_key
                if active_key:
                    messages.success(
                        request,
                        "Account created. Your API key is saved — AI quick-add is ready to go.",
                    )
                else:
                    messages.success(
                        request,
                        "Account created. Add an API key anytime from Settings to use AI quick-add.",
                    )
            return redirect("task-list")
    else:
        form = RegisterForm()
    return render(request, "registration/register.html", {"form": form})


@login_required
def account_settings(request):
    """Let a logged-in user manage their preferred AI provider and the
    OpenAI/Gemini API keys that back it."""
    profile, _ = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = OpenAIKeyForm(request.POST)
        if form.is_valid():
            profile.openai_api_key = form.cleaned_data["openai_api_key"].strip()
            profile.save(update_fields=["openai_api_key"])
            messages.success(request, "OpenAI API key saved.")
            return redirect("account-settings")
    else:
        form = OpenAIKeyForm()

    return render(
        request,
        "account/settings.html",
        {
            "form": form,
            "gemini_form": GeminiKeyForm(),
            "provider_form": AIProviderForm(initial={"ai_provider": profile.ai_provider}),
            "profile": profile,
            "local_model_available": local_runtime_available(),
        },
    )


@login_required
@require_POST
def save_gemini_key(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = GeminiKeyForm(request.POST)
    if form.is_valid():
        profile.gemini_api_key = form.cleaned_data["gemini_api_key"].strip()
        profile.save(update_fields=["gemini_api_key"])
        messages.success(request, "Gemini API key saved.")
    else:
        messages.error(request, "Please enter a Gemini API key.")
    return redirect("account-settings")


@login_required
@require_POST
def set_ai_provider(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    form = AIProviderForm(request.POST)
    if form.is_valid():
        profile.ai_provider = form.cleaned_data["ai_provider"]
        profile.save(update_fields=["ai_provider"])
        messages.success(
            request, f"Now using {profile.get_ai_provider_display()} for AI quick-add."
        )
    else:
        messages.error(request, "Unknown AI provider.")
    return redirect("account-settings")


@login_required
@require_POST
def remove_openai_key(request):
    Profile.objects.filter(user=request.user).update(openai_api_key="")
    messages.success(request, "OpenAI API key removed.")
    return redirect("account-settings")


@login_required
@require_POST
def remove_gemini_key(request):
    Profile.objects.filter(user=request.user).update(gemini_api_key="")
    messages.success(request, "Gemini API key removed.")
    return redirect("account-settings")


@login_required
def theme_shop(request):
    """List every theme, each one's cost, and whether the user has it unlocked.

    Theme stylesheets themselves aren't authored here -- each paid option's
    actual look comes from a real, hosted Bootswatch CSS file (see
    tasks/themes.py); this view just tracks points and unlock state.
    """
    profile, _ = Profile.objects.get_or_create(user=request.user)
    unlocked = profile.unlocked_theme_keys

    shop_items = [
        {
            **theme,
            "unlocked": theme["key"] in unlocked,
            "active": theme["key"] == profile.active_theme,
            "affordable": profile.points >= theme["cost"],
        }
        for theme in THEMES
    ]

    return render(
        request,
        "tasks/shop.html",
        {"shop_items": shop_items, "profile": profile},
    )


@login_required
@require_POST
def select_theme(request, theme_key):
    """Switch to an already-unlocked theme for free, or buy a locked one with
    points if the user can afford it."""
    if not is_valid_theme_key(theme_key):
        messages.error(request, "Unknown theme.")
        return redirect("theme-shop")

    profile, _ = Profile.objects.get_or_create(user=request.user)
    theme = get_theme(theme_key)

    if theme_key in profile.unlocked_theme_keys:
        profile.active_theme = theme_key
        profile.save(update_fields=["active_theme"])
        messages.success(request, f"{theme['name']} is now active.")
    elif profile.points >= theme["cost"]:
        profile.points -= theme["cost"]
        profile.unlock_theme(theme_key)
        profile.active_theme = theme_key
        profile.save(update_fields=["points", "unlocked_themes", "active_theme"])
        messages.success(request, f"Unlocked {theme['name']} for {theme['cost']} points!")
    else:
        messages.error(
            request,
            f"Not enough points for {theme['name']} — need {theme['cost']}, you have {profile.points}.",
        )

    return redirect("theme-shop")
