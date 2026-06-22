import os
from unittest.mock import patch

from allauth.account.signals import user_signed_up
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .ai import AIParseError
from .forms import DateTimeSelectField
from .models import POINTS_PER_TASK, Profile, Task
from .themes import DEFAULT_THEME_KEY


class RegistrationAndLoginTests(TestCase):
    def test_register_creates_user_and_logs_in(self):
        resp = self.client.post(
            reverse("register"),
            {
                "username": "alice",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
                "ai_provider": "openai",
            },
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(User.objects.filter(username="alice").exists())
        self.assertTrue(resp.context["user"].is_authenticated)

    def test_register_without_api_key_creates_blank_profile(self):
        self.client.post(
            reverse("register"),
            {
                "username": "alice",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
                "ai_provider": "openai",
            },
        )
        profile = Profile.objects.get(user__username="alice")
        self.assertEqual(profile.openai_api_key, "")
        self.assertEqual(profile.gemini_api_key, "")
        self.assertFalse(profile.has_api_key)

    def test_register_with_api_key_creates_profile_with_key(self):
        self.client.post(
            reverse("register"),
            {
                "username": "alice",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
                "ai_provider": "openai",
                "openai_api_key": "sk-test-key",
            },
        )
        profile = Profile.objects.get(user__username="alice")
        self.assertEqual(profile.openai_api_key, "sk-test-key")
        self.assertTrue(profile.has_api_key)

    def test_register_with_gemini_provider_and_key_creates_profile_with_key(self):
        self.client.post(
            reverse("register"),
            {
                "username": "alice",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
                "ai_provider": "gemini",
                "gemini_api_key": "AIza-test-key",
            },
        )
        profile = Profile.objects.get(user__username="alice")
        self.assertEqual(profile.ai_provider, "gemini")
        self.assertEqual(profile.gemini_api_key, "AIza-test-key")
        self.assertTrue(profile.has_api_key)

    def test_register_with_local_provider_creates_profile_without_key(self):
        resp = self.client.post(
            reverse("register"),
            {
                "username": "alice",
                "password1": "SuperSecret123!",
                "password2": "SuperSecret123!",
                "ai_provider": "local",
            },
            follow=True,
        )
        profile = Profile.objects.get(user__username="alice")
        self.assertEqual(profile.ai_provider, "local")
        self.assertEqual(profile.openai_api_key, "")
        self.assertEqual(profile.gemini_api_key, "")
        # Local never needs a key, so it's "ready" even with both blank.
        self.assertTrue(profile.has_api_key)
        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("local model" in m.lower() for m in rendered_messages))

    def test_anonymous_user_redirected_to_login(self):
        resp = self.client.get(reverse("task-list"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("/login/"))

    def test_wrong_password_does_not_log_in(self):
        User.objects.create_user("alice", password="SuperSecret123!")
        self.client.post(reverse("login"), {"username": "alice", "password": "wrong"})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_correct_password_logs_in(self):
        User.objects.create_user("alice", password="SuperSecret123!")
        self.client.post(reverse("login"), {"username": "alice", "password": "SuperSecret123!"})
        self.assertIn("_auth_user_id", self.client.session)


class TaskOwnershipTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")
        self.bob = User.objects.create_user("bob", password="AnotherSecret456!")
        self.alice_task = Task.objects.create(user=self.alice, title="Alice task")
        self.bob_task = Task.objects.create(user=self.bob, title="Bob task")

    def test_user_only_sees_own_tasks(self):
        self.client.force_login(self.alice)
        resp = self.client.get(reverse("task-list"))
        titles = [t.title for t in resp.context["tasks"]]
        self.assertEqual(titles, ["Alice task"])

    def test_cannot_view_edit_page_for_other_users_task(self):
        self.client.force_login(self.bob)
        resp = self.client.get(reverse("task-update", args=[self.alice_task.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_cannot_delete_other_users_task(self):
        self.client.force_login(self.bob)
        resp = self.client.post(reverse("task-delete", args=[self.alice_task.pk]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Task.objects.filter(pk=self.alice_task.pk).exists())

    def test_cannot_toggle_other_users_task(self):
        self.client.force_login(self.bob)
        self.client.post(reverse("task-toggle", args=[self.alice_task.pk]))
        self.alice_task.refresh_from_db()
        self.assertFalse(self.alice_task.complete)

    def test_owner_can_toggle_edit_delete_own_task(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("task-toggle", args=[self.alice_task.pk]))
        self.alice_task.refresh_from_db()
        self.assertTrue(self.alice_task.complete)

        self.client.post(
            reverse("task-update", args=[self.alice_task.pk]),
            {"title": "Updated", "description": "", "complete": True},
        )
        self.alice_task.refresh_from_db()
        self.assertEqual(self.alice_task.title, "Updated")

        self.client.post(reverse("task-delete", args=[self.alice_task.pk]))
        self.assertFalse(Task.objects.filter(pk=self.alice_task.pk).exists())


class AccountSettingsTests(TestCase):
    """Covers the per-user OpenAI API key add/update/remove flow."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")

    def test_settings_page_requires_login(self):
        resp = self.client.get(reverse("account-settings"))
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.startswith("/login/"))

    def test_settings_page_works_even_without_an_existing_profile_row(self):
        # Simulates an account that predates the Profile model.
        self.client.force_login(self.alice)
        resp = self.client.get(reverse("account-settings"))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.alice).exists())

    def test_can_save_api_key(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("account-settings"), {"openai_api_key": "sk-abc123"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.openai_api_key, "sk-abc123")

    def test_can_update_api_key(self):
        Profile.objects.create(user=self.alice, openai_api_key="sk-old")
        self.client.force_login(self.alice)
        self.client.post(reverse("account-settings"), {"openai_api_key": "sk-new"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.openai_api_key, "sk-new")

    def test_can_remove_api_key(self):
        Profile.objects.create(user=self.alice, openai_api_key="sk-old")
        self.client.force_login(self.alice)
        self.client.post(reverse("account-openai-key-remove"))
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.openai_api_key, "")
        self.assertFalse(profile.has_api_key)

    def test_masked_api_key_never_exposes_full_value(self):
        profile = Profile.objects.create(user=self.alice, openai_api_key="sk-abcdef123456")
        masked = profile.masked_api_key()
        self.assertNotIn("abcdef123456", masked)
        self.assertTrue(masked.endswith("3456"))

    def test_can_save_gemini_key(self):
        self.client.force_login(self.alice)
        self.client.post(reverse("account-gemini-key"), {"gemini_api_key": "AIza-abc123"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.gemini_api_key, "AIza-abc123")

    def test_can_update_gemini_key(self):
        Profile.objects.create(user=self.alice, gemini_api_key="AIza-old")
        self.client.force_login(self.alice)
        self.client.post(reverse("account-gemini-key"), {"gemini_api_key": "AIza-new"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.gemini_api_key, "AIza-new")

    def test_can_remove_gemini_key(self):
        Profile.objects.create(user=self.alice, gemini_api_key="AIza-old")
        self.client.force_login(self.alice)
        self.client.post(reverse("account-gemini-key-remove"))
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.gemini_api_key, "")
        self.assertFalse(profile.has_gemini_key)

    def test_masked_gemini_api_key_never_exposes_full_value(self):
        profile = Profile.objects.create(user=self.alice, gemini_api_key="AIza-abcdef123456")
        masked = profile.masked_gemini_api_key()
        self.assertNotIn("abcdef123456", masked)
        self.assertTrue(masked.endswith("3456"))

    def test_default_provider_is_openai(self):
        profile, _ = Profile.objects.get_or_create(user=self.alice)
        self.assertEqual(profile.ai_provider, "openai")

    def test_can_switch_preferred_provider(self):
        Profile.objects.create(user=self.alice)
        self.client.force_login(self.alice)
        self.client.post(reverse("account-provider"), {"ai_provider": "gemini"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.ai_provider, "gemini")

    def test_has_api_key_reflects_whichever_provider_is_active(self):
        profile = Profile.objects.create(
            user=self.alice, ai_provider="gemini", gemini_api_key="AIza-key", openai_api_key=""
        )
        self.assertTrue(profile.has_api_key)

        profile.ai_provider = "openai"
        profile.save(update_fields=["ai_provider"])
        self.assertFalse(profile.has_api_key)

    def test_invalid_provider_choice_is_rejected(self):
        Profile.objects.create(user=self.alice, ai_provider="openai")
        self.client.force_login(self.alice)
        self.client.post(reverse("account-provider"), {"ai_provider": "not-a-real-provider"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.ai_provider, "openai")

    def test_can_switch_to_local_provider(self):
        Profile.objects.create(user=self.alice)
        self.client.force_login(self.alice)
        self.client.post(reverse("account-provider"), {"ai_provider": "local"})
        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.ai_provider, "local")

    def test_has_api_key_true_for_local_provider_with_no_keys_saved(self):
        profile = Profile.objects.create(user=self.alice, ai_provider="local")
        self.assertTrue(profile.has_api_key)

    def test_active_provider_api_key_blank_for_local_even_with_other_keys_saved(self):
        profile = Profile.objects.create(
            user=self.alice,
            ai_provider="local",
            openai_api_key="sk-leftover",
            gemini_api_key="AIza-leftover",
        )
        self.assertEqual(profile.active_provider_api_key, "")

    def test_settings_page_reports_local_model_availability(self):
        self.client.force_login(self.alice)
        with patch("tasks.views.local_runtime_available", return_value=True):
            resp = self.client.get(reverse("account-settings"))
        self.assertTrue(resp.context["local_model_available"])

        with patch("tasks.views.local_runtime_available", return_value=False):
            resp = self.client.get(reverse("account-settings"))
        self.assertFalse(resp.context["local_model_available"])


class QuickAddAITests(TestCase):
    """Tests the AI quick-add endpoint with the OpenAI call mocked out --
    no real API key or network access needed/used."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")
        self.client.force_login(self.alice)

    @patch("tasks.views.parse_task_text")
    def test_quick_add_uses_parsed_result(self, mock_parse):
        due = timezone.now() + timezone.timedelta(days=1)
        mock_parse.return_value = {
            "title": "Call mom",
            "description": None,
            "due_date": due,
            "category": "personal",
        }

        self.client.post(reverse("task-quick-add"), {"text": "remind me to call mom tomorrow"})

        task = Task.objects.get(user=self.alice)
        self.assertEqual(task.title, "Call mom")
        self.assertIsNotNone(task.due_date)
        self.assertEqual(task.category, "personal")
        mock_parse.assert_called_once_with(
            "remind me to call mom tomorrow", provider="openai", api_key=None
        )

    @patch("tasks.views.parse_task_text")
    def test_quick_add_passes_users_personal_api_key(self, mock_parse):
        Profile.objects.create(user=self.alice, openai_api_key="sk-personal")
        mock_parse.return_value = {
            "title": "Buy milk",
            "description": None,
            "due_date": None,
            "category": "shopping",
        }

        self.client.post(reverse("task-quick-add"), {"text": "buy milk"})

        mock_parse.assert_called_once_with("buy milk", provider="openai", api_key="sk-personal")

    @patch("tasks.views.parse_task_text")
    def test_quick_add_uses_gemini_when_selected(self, mock_parse):
        Profile.objects.create(
            user=self.alice, ai_provider="gemini", gemini_api_key="AIza-personal"
        )
        mock_parse.return_value = {
            "title": "Buy milk",
            "description": None,
            "due_date": None,
            "category": "shopping",
        }

        self.client.post(reverse("task-quick-add"), {"text": "buy milk"})

        mock_parse.assert_called_once_with("buy milk", provider="gemini", api_key="AIza-personal")

    @patch("tasks.views.parse_task_text")
    def test_quick_add_uses_local_model_when_selected(self, mock_parse):
        Profile.objects.create(user=self.alice, ai_provider="local")
        mock_parse.return_value = {
            "title": "Buy milk",
            "description": None,
            "due_date": None,
            "category": "shopping",
        }

        self.client.post(reverse("task-quick-add"), {"text": "buy milk"})

        # Local never has a saved key, so api_key should be None, not "".
        mock_parse.assert_called_once_with("buy milk", provider="local", api_key=None)

    @patch("tasks.views.parse_task_text")
    def test_quick_add_falls_back_to_raw_text_on_ai_error(self, mock_parse):
        mock_parse.side_effect = AIParseError("no OpenAI API key is configured")

        self.client.post(reverse("task-quick-add"), {"text": "buy milk"})

        task = Task.objects.get(user=self.alice)
        self.assertEqual(task.title, "buy milk")
        self.assertIsNone(task.due_date)
        self.assertEqual(task.category, "")

    @patch("tasks.views.parse_task_text")
    def test_quick_add_shows_friendly_message_when_no_key_anywhere(self, mock_parse):
        mock_parse.side_effect = AIParseError("no OpenAI API key is configured")

        with patch.dict("os.environ", {}, clear=True):
            resp = self.client.post(reverse("task-quick-add"), {"text": "buy milk"}, follow=True)

        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("OpenAI API key" in m for m in rendered_messages))
        self.assertTrue(any('href="/settings/"' in m for m in rendered_messages))
        # Should not leak the raw exception text in the friendly path.
        self.assertFalse(any("no OpenAI API key is configured" in m for m in rendered_messages))

    @patch("tasks.views.parse_task_text")
    def test_quick_add_shows_specific_error_when_a_key_exists_but_parsing_fails(self, mock_parse):
        Profile.objects.create(user=self.alice, openai_api_key="sk-personal")
        mock_parse.side_effect = AIParseError("network timeout")

        resp = self.client.post(reverse("task-quick-add"), {"text": "buy milk"}, follow=True)

        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("network timeout" in m for m in rendered_messages))
        self.assertFalse(any("OpenAI API key" in m for m in rendered_messages))

    @patch("tasks.views.parse_task_text")
    def test_quick_add_local_failure_shows_generic_message_not_key_prompt(self, mock_parse):
        # Local is always "configured" (no key needed), so a failure here
        # should never produce the "add an API key" nudge -- has_configured_key
        # is True regardless of what broke.
        Profile.objects.create(user=self.alice, ai_provider="local")
        mock_parse.side_effect = AIParseError(
            "the 'llama-cpp-python' package is not installed"
        )

        resp = self.client.post(reverse("task-quick-add"), {"text": "buy milk"}, follow=True)

        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("llama-cpp-python" in m for m in rendered_messages))
        self.assertFalse(any("add a" in m and "API key" in m for m in rendered_messages))

    @patch("tasks.views.parse_task_text")
    def test_quick_add_uses_an_for_openai_and_a_for_gemini(self, mock_parse):
        mock_parse.side_effect = AIParseError("no OpenAI API key is configured")
        with patch.dict("os.environ", {}, clear=True):
            resp = self.client.post(reverse("task-quick-add"), {"text": "buy milk"}, follow=True)
        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("add an OpenAI API key" in m for m in rendered_messages))
        self.assertFalse(any("add a OpenAI API key" in m for m in rendered_messages))

        Profile.objects.create(user=self.alice, ai_provider="gemini")
        mock_parse.side_effect = AIParseError("no Gemini API key is configured")
        with patch.dict("os.environ", {}, clear=True):
            resp = self.client.post(reverse("task-quick-add"), {"text": "buy milk"}, follow=True)
        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("add a Gemini API key" in m for m in rendered_messages))

    def test_quick_add_requires_non_empty_text(self):
        self.client.post(reverse("task-quick-add"), {"text": "   "})
        self.assertEqual(Task.objects.filter(user=self.alice).count(), 0)

    def test_quick_add_requires_login(self):
        self.client.logout()
        resp = self.client.post(reverse("task-quick-add"), {"text": "buy milk"})
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Task.objects.count(), 0)


class AIParsingUnitTests(TestCase):
    """Exercises tasks/ai.py directly, still without hitting the real API."""

    def test_raises_when_api_key_missing(self):
        with patch.dict("os.environ", {}, clear=True):
            from . import ai

            with self.assertRaises(AIParseError):
                ai.parse_task_text("call mom tomorrow")

    def test_empty_text_raises(self):
        from . import ai

        with self.assertRaises(AIParseError):
            ai.parse_task_text("   ")

    def test_explicit_api_key_overrides_missing_env_var(self):
        from . import ai

        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(ai.has_configured_key(api_key="sk-explicit"))
            self.assertFalse(ai.has_configured_key(api_key=None))

    @patch("tasks.ai.openai")
    def test_parses_well_formed_json_response(self, mock_openai):
        from . import ai

        mock_create = mock_openai.OpenAI.return_value.chat.completions.create
        mock_create.return_value.choices = [
            type(
                "Choice",
                (),
                {
                    "message": type(
                        "Message",
                        (),
                        {
                            "content": (
                                '{"title": "Call mom", "description": null, '
                                '"due_date": null, "category": "personal"}'
                            )
                        },
                    )()
                },
            )()
        ]
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = ai.parse_task_text("call mom")
        self.assertEqual(result["title"], "Call mom")
        self.assertIsNone(result["due_date"])
        self.assertEqual(result["category"], "personal")

    @patch("tasks.ai.openai")
    def test_parses_using_explicit_per_user_key_without_env_var(self, mock_openai):
        from . import ai

        mock_create = mock_openai.OpenAI.return_value.chat.completions.create
        mock_create.return_value.choices = [
            type(
                "Choice",
                (),
                {
                    "message": type(
                        "Message",
                        (),
                        {
                            "content": (
                                '{"title": "Call mom", "description": null, '
                                '"due_date": null, "category": "personal"}'
                            )
                        },
                    )()
                },
            )()
        ]
        with patch.dict("os.environ", {}, clear=True):
            result = ai.parse_task_text("call mom", api_key="sk-personal")
        self.assertEqual(result["title"], "Call mom")
        mock_openai.OpenAI.assert_called_once_with(api_key="sk-personal")

    @patch("tasks.ai.openai")
    def test_invalid_json_raises_ai_parse_error(self, mock_openai):
        from . import ai

        mock_create = mock_openai.OpenAI.return_value.chat.completions.create
        mock_create.return_value.choices = [
            type("Choice", (), {"message": type("Message", (), {"content": "not json"})()})()
        ]
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            with self.assertRaises(AIParseError):
                ai.parse_task_text("call mom")

    @patch("tasks.ai.openai")
    def test_unrecognized_category_falls_back_to_blank(self, mock_openai):
        from . import ai

        mock_create = mock_openai.OpenAI.return_value.chat.completions.create
        mock_create.return_value.choices = [
            type(
                "Choice",
                (),
                {
                    "message": type(
                        "Message",
                        (),
                        {
                            "content": (
                                '{"title": "Do a thing", "description": null, '
                                '"due_date": null, "category": "not-a-real-category"}'
                            )
                        },
                    )()
                },
            )()
        ]
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = ai.parse_task_text("do a thing")
        self.assertEqual(result["category"], "")

    def test_unknown_provider_raises_ai_parse_error(self):
        from . import ai

        with self.assertRaises(AIParseError):
            ai.parse_task_text("call mom", provider="not-a-real-provider")

    @patch("tasks.ai.genai_types")
    @patch("tasks.ai.genai")
    def test_parses_well_formed_json_response_via_gemini(self, mock_genai, mock_genai_types):
        from . import ai

        mock_response = type(
            "Response",
            (),
            {
                "text": (
                    '{"title": "Call mom", "description": null, '
                    '"due_date": null, "category": "personal"}'
                )
            },
        )()
        mock_genai.Client.return_value.models.generate_content.return_value = mock_response

        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            result = ai.parse_task_text("call mom", provider="gemini")
        self.assertEqual(result["title"], "Call mom")
        self.assertIsNone(result["due_date"])
        self.assertEqual(result["category"], "personal")

    @patch("tasks.ai.genai_types")
    @patch("tasks.ai.genai")
    def test_gemini_uses_explicit_per_user_key_without_env_var(self, mock_genai, mock_genai_types):
        from . import ai

        mock_response = type(
            "Response",
            (),
            {
                "text": (
                    '{"title": "Call mom", "description": null, '
                    '"due_date": null, "category": "personal"}'
                )
            },
        )()
        mock_genai.Client.return_value.models.generate_content.return_value = mock_response

        with patch.dict("os.environ", {}, clear=True):
            result = ai.parse_task_text("call mom", provider="gemini", api_key="AIza-personal")
        self.assertEqual(result["title"], "Call mom")
        mock_genai.Client.assert_called_once_with(api_key="AIza-personal")

    def test_gemini_raises_when_no_key_configured(self):
        from . import ai

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIParseError):
                ai.parse_task_text("call mom", provider="gemini")

    def test_clean_exception_message_extracts_nested_api_error(self):
        from . import ai

        exc = Exception(
            "503 UNAVAILABLE. {'error': {'code': 503, 'message': "
            "'The model is currently overloaded. Please try again later.', "
            "'status': 'UNAVAILABLE'}}"
        )
        self.assertEqual(
            ai._clean_exception_message(exc),
            "503: The model is currently overloaded. Please try again later.",
        )

    def test_clean_exception_message_passes_through_plain_text(self):
        from . import ai

        self.assertEqual(ai._clean_exception_message(Exception("network timeout")), "network timeout")

    def test_clean_exception_message_passes_through_unparseable_braces(self):
        from . import ai

        # Looks like it has a dict in it, but isn't valid Python -- should
        # fall back to the original string rather than raising.
        self.assertEqual(
            ai._clean_exception_message(Exception("weird {not a dict") ),
            "weird {not a dict",
        )

    @patch("tasks.ai.genai_types")
    @patch("tasks.ai.genai")
    def test_parse_task_text_cleans_up_raw_api_error_payload(self, mock_genai, mock_genai_types):
        from . import ai

        mock_genai.Client.return_value.models.generate_content.side_effect = Exception(
            "503 UNAVAILABLE. {'error': {'code': 503, 'message': "
            "'The model is currently overloaded. Please try again later.', "
            "'status': 'UNAVAILABLE'}}"
        )
        with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
            with self.assertRaises(AIParseError) as ctx:
                ai.parse_task_text("call mom", provider="gemini")
        self.assertEqual(
            str(ctx.exception),
            "503: The model is currently overloaded. Please try again later.",
        )


class LocalProviderTests(TestCase):
    """Exercises the local (llama-cpp-python) provider in tasks/ai.py, fully
    mocked out -- no real model download or inference happens in tests."""

    def setUp(self):
        from . import ai

        # _get_local_llm() caches the loaded model at module scope so a real
        # run only downloads/loads once. Reset that cache around each test so
        # tests don't leak a mocked instance into one another.
        self._ai = ai
        self._original_local_llm = ai._local_llm
        ai._local_llm = None

    def tearDown(self):
        self._ai._local_llm = self._original_local_llm

    def test_local_provider_never_requires_a_key(self):
        from . import ai

        with patch.dict("os.environ", {}, clear=True):
            self.assertTrue(ai.has_configured_key(provider="local"))
            self.assertTrue(ai.has_configured_key(provider="local", api_key="anything"))

    def test_missing_package_raises_ai_parse_error_mentioning_it(self):
        from . import ai

        with patch("tasks.ai.Llama", None):
            with self.assertRaises(AIParseError) as ctx:
                ai.parse_task_text("call mom", provider="local")
        self.assertIn("llama-cpp-python", str(ctx.exception))

    def test_local_runtime_available_reflects_whether_llama_cpp_is_importable(self):
        from . import ai

        with patch("tasks.ai.Llama", object()):
            self.assertTrue(ai.local_runtime_available())
        with patch("tasks.ai.Llama", None):
            self.assertFalse(ai.local_runtime_available())

    @patch("tasks.ai.Llama")
    def test_loads_default_model_via_from_pretrained_and_parses_response(self, mock_llama_cls):
        from . import ai

        mock_llm = mock_llama_cls.from_pretrained.return_value
        mock_llm.create_chat_completion.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"title": "Call mom", "description": null, '
                            '"due_date": null, "category": "personal"}'
                        )
                    }
                }
            ]
        }

        with patch.dict("os.environ", {}, clear=True):
            result = ai.parse_task_text("call mom", provider="local")

        self.assertEqual(result["title"], "Call mom")
        self.assertIsNone(result["due_date"])
        self.assertEqual(result["category"], "personal")
        mock_llama_cls.from_pretrained.assert_called_once_with(
            repo_id=ai.DEFAULT_LOCAL_MODEL_REPO,
            filename=ai.DEFAULT_LOCAL_MODEL_FILE,
            n_ctx=2048,
            verbose=False,
        )

    @patch("tasks.ai.Llama")
    def test_local_model_is_loaded_only_once_across_repeated_calls(self, mock_llama_cls):
        from . import ai

        mock_llm = mock_llama_cls.from_pretrained.return_value
        mock_llm.create_chat_completion.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"title": "x", "description": null, '
                            '"due_date": null, "category": "other"}'
                        )
                    }
                }
            ]
        }

        with patch.dict("os.environ", {}, clear=True):
            ai.parse_task_text("first note", provider="local")
            ai.parse_task_text("second note", provider="local")

        mock_llama_cls.from_pretrained.assert_called_once()

    @patch("tasks.ai.Llama")
    def test_local_model_path_env_var_skips_huggingface_download(self, mock_llama_cls):
        from . import ai

        mock_llm = mock_llama_cls.return_value
        mock_llm.create_chat_completion.return_value = {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"title": "x", "description": null, '
                            '"due_date": null, "category": "other"}'
                        )
                    }
                }
            ]
        }

        with patch.dict("os.environ", {"LOCAL_MODEL_PATH": "/tmp/my-model.gguf"}, clear=True):
            ai.parse_task_text("call mom", provider="local")

        mock_llama_cls.assert_called_once_with(
            model_path="/tmp/my-model.gguf", n_ctx=2048, verbose=False
        )
        mock_llama_cls.from_pretrained.assert_not_called()

    @patch("tasks.ai.Llama")
    def test_local_model_load_failure_raises_ai_parse_error(self, mock_llama_cls):
        from . import ai

        mock_llama_cls.from_pretrained.side_effect = RuntimeError("disk full")

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIParseError):
                ai.parse_task_text("call mom", provider="local")

    @patch("tasks.ai.Llama")
    def test_local_invalid_json_raises_ai_parse_error(self, mock_llama_cls):
        from . import ai

        mock_llm = mock_llama_cls.from_pretrained.return_value
        mock_llm.create_chat_completion.return_value = {
            "choices": [{"message": {"content": "not json"}}]
        }

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AIParseError):
                ai.parse_task_text("call mom", provider="local")


class StartupWarmupTests(TestCase):
    """Covers the optional local-model warm-up in tasks/apps.py. It should
    only start a background load when a real server process is starting (not
    a management command), only once even under the dev autoreloader's
    watcher/subprocess split, and only when some user actually has the local
    provider selected -- never unconditionally on every boot."""

    def _make_local_user(self, username="lucy"):
        user = User.objects.create_user(username, password="SuperSecret123!")
        Profile.objects.create(user=user, ai_provider="local")
        return user

    def test_any_local_provider_profile_exists_false_with_no_users(self):
        from . import apps

        self.assertFalse(apps._any_local_provider_profile_exists())

    def test_any_local_provider_profile_exists_false_for_openai_only_users(self):
        from . import apps

        user = User.objects.create_user("oscar", password="SuperSecret123!")
        Profile.objects.create(user=user, ai_provider="openai")
        self.assertFalse(apps._any_local_provider_profile_exists())

    def test_any_local_provider_profile_exists_true_once_someone_picks_local(self):
        from . import apps

        self._make_local_user()
        self.assertTrue(apps._any_local_provider_profile_exists())

    def test_reloader_watcher_only_true_for_runserver_with_active_reloader_unstarted(self):
        from . import apps

        with patch("tasks.apps.sys.argv", ["manage.py", "shell"]):
            self.assertFalse(apps._is_reloader_watcher_process())

        with patch("tasks.apps.sys.argv", ["manage.py", "runserver", "--noreload"]):
            self.assertFalse(apps._is_reloader_watcher_process())

        with patch("tasks.apps.sys.argv", ["manage.py", "runserver"]):
            with patch.dict("os.environ", {}, clear=True):
                self.assertTrue(apps._is_reloader_watcher_process())
            with patch.dict("os.environ", {"RUN_MAIN": "true"}):
                self.assertFalse(apps._is_reloader_watcher_process())

    def test_warmup_skipped_for_management_commands_like_test_and_migrate(self):
        from . import apps

        self._make_local_user()
        for command in ("test", "migrate", "makemigrations"):
            with patch("tasks.apps.sys.argv", ["manage.py", command]):
                with patch("tasks.apps.threading.Thread") as mock_thread:
                    apps._maybe_warm_local_model()
            mock_thread.assert_not_called()

    def test_warmup_skipped_in_reloader_watcher_process(self):
        from . import apps

        self._make_local_user()
        with patch("tasks.apps.sys.argv", ["manage.py", "runserver"]):
            with patch.dict("os.environ", {}, clear=True):
                with patch("tasks.apps.threading.Thread") as mock_thread:
                    apps._maybe_warm_local_model()
        mock_thread.assert_not_called()

    def test_warmup_skipped_when_no_one_has_local_provider_selected(self):
        from . import apps

        User.objects.create_user("oscar", password="SuperSecret123!")
        with patch("tasks.apps.sys.argv", ["manage.py", "runserver", "--noreload"]):
            with patch("tasks.apps.threading.Thread") as mock_thread:
                apps._maybe_warm_local_model()
        mock_thread.assert_not_called()

    def test_warmup_starts_background_thread_once_a_user_has_local_selected(self):
        from . import ai, apps

        self._make_local_user()
        with patch("tasks.apps.sys.argv", ["manage.py", "runserver", "--noreload"]):
            with patch("tasks.apps.threading.Thread") as mock_thread:
                apps._maybe_warm_local_model()

        mock_thread.assert_called_once_with(target=ai._get_local_llm, daemon=True)
        mock_thread.return_value.start.assert_called_once()

    def test_warmup_runs_in_the_runserver_subprocess_when_reloader_is_active(self):
        from . import ai, apps

        self._make_local_user()
        with patch("tasks.apps.sys.argv", ["manage.py", "runserver"]):
            with patch.dict("os.environ", {"RUN_MAIN": "true"}):
                with patch("tasks.apps.threading.Thread") as mock_thread:
                    apps._maybe_warm_local_model()

        mock_thread.assert_called_once_with(target=ai._get_local_llm, daemon=True)


class CompletedAtTests(TestCase):
    """Covers automatic completed_at management on Task.save()."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")

    def test_completing_a_task_sets_completed_at(self):
        task = Task.objects.create(user=self.alice, title="Wash car")
        self.assertIsNone(task.completed_at)

        task.complete = True
        task.save()
        task.refresh_from_db()
        self.assertIsNotNone(task.completed_at)

    def test_uncompleting_a_task_clears_completed_at(self):
        task = Task.objects.create(user=self.alice, title="Wash car", complete=True)
        self.assertIsNotNone(task.completed_at)

        task.complete = False
        task.save()
        task.refresh_from_db()
        self.assertIsNone(task.completed_at)

    def test_toggle_view_sets_completed_at(self):
        self.client.force_login(self.alice)
        task = Task.objects.create(user=self.alice, title="Wash car")

        self.client.post(reverse("task-toggle", args=[task.pk]))
        task.refresh_from_db()
        self.assertTrue(task.complete)
        self.assertIsNotNone(task.completed_at)

        self.client.post(reverse("task-toggle", args=[task.pk]))
        task.refresh_from_db()
        self.assertFalse(task.complete)
        self.assertIsNone(task.completed_at)

    def test_resaving_an_already_complete_task_does_not_change_completed_at(self):
        task = Task.objects.create(user=self.alice, title="Wash car", complete=True)
        first_completed_at = task.completed_at

        task.title = "Wash the car"
        task.save()
        task.refresh_from_db()
        self.assertEqual(task.completed_at, first_completed_at)


class CalendarViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")
        self.client.force_login(self.alice)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("task-calendar"))
        self.assertEqual(resp.status_code, 302)

    def test_only_shows_completed_tasks(self):
        Task.objects.create(user=self.alice, title="Done", complete=True)
        Task.objects.create(user=self.alice, title="Not done", complete=False)

        resp = self.client.get(reverse("task-calendar"))
        all_tasks = [t for day in resp.context["days"] for t in day["tasks"]]
        titles = [t.title for t in all_tasks]
        self.assertIn("Done", titles)
        self.assertNotIn("Not done", titles)

    def test_groups_completed_tasks_by_day(self):
        today = Task.objects.create(user=self.alice, title="Today task", complete=True)
        yesterday = Task.objects.create(user=self.alice, title="Yesterday task", complete=True)
        yesterday.completed_at = timezone.now() - timezone.timedelta(days=1)
        yesterday.save()

        resp = self.client.get(reverse("task-calendar"))
        self.assertEqual(len(resp.context["days"]), 2)

    def test_only_shows_own_completed_tasks(self):
        bob = User.objects.create_user("bob", password="AnotherSecret456!")
        Task.objects.create(user=bob, title="Bob's done task", complete=True)

        resp = self.client.get(reverse("task-calendar"))
        all_tasks = [t for day in resp.context["days"] for t in day["tasks"]]
        self.assertEqual(all_tasks, [])


class ListsViewTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")
        self.client.force_login(self.alice)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("task-lists"))
        self.assertEqual(resp.status_code, 302)

    def test_groups_tasks_by_category(self):
        Task.objects.create(user=self.alice, title="Finish report", category="work")
        Task.objects.create(user=self.alice, title="Buy milk", category="shopping")
        Task.objects.create(user=self.alice, title="No category")

        resp = self.client.get(reverse("task-lists"))
        labels = [g["label"] for g in resp.context["lists"]]
        self.assertIn("Work", labels)
        self.assertIn("Shopping", labels)
        self.assertIn("Uncategorized", labels)

    def test_only_shows_own_tasks(self):
        bob = User.objects.create_user("bob", password="AnotherSecret456!")
        Task.objects.create(user=bob, title="Bob's task", category="work")

        resp = self.client.get(reverse("task-lists"))
        all_tasks = [t for g in resp.context["lists"] for t in g["tasks"]]
        self.assertEqual(all_tasks, [])

    def test_manual_category_can_be_set_via_task_form(self):
        self.client.post(
            reverse("task-create"),
            {"title": "Plan trip", "description": "", "category": "personal"},
        )
        task = Task.objects.get(title="Plan trip")
        self.assertEqual(task.category, "personal")


class PointsTests(TestCase):
    """Covers awarding/deducting points as a task's complete flag flips (Task.save())."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")

    def test_completing_a_task_awards_points(self):
        task = Task.objects.create(user=self.alice, title="Wash car")
        task.complete = True
        task.save()

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, POINTS_PER_TASK)

    def test_creating_an_already_complete_task_awards_points(self):
        Task.objects.create(user=self.alice, title="Wash car", complete=True)

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, POINTS_PER_TASK)

    def test_uncompleting_a_task_deducts_points(self):
        task = Task.objects.create(user=self.alice, title="Wash car", complete=True)
        self.assertEqual(Profile.objects.get(user=self.alice).points, POINTS_PER_TASK)

        task.complete = False
        task.save()

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, 0)

    def test_uncompleting_never_drops_points_below_zero(self):
        task = Task.objects.create(user=self.alice, title="Wash car", complete=True)
        profile = Profile.objects.get(user=self.alice)
        profile.points = 3  # simulate having already spent points in the Shop
        profile.save(update_fields=["points"])

        task.complete = False
        task.save()

        profile.refresh_from_db()
        self.assertEqual(profile.points, 0)

    def test_toggling_off_and_on_mirrors_points_each_time(self):
        task = Task.objects.create(user=self.alice, title="Wash car")

        task.complete = True
        task.save()
        self.assertEqual(Profile.objects.get(user=self.alice).points, POINTS_PER_TASK)

        task.complete = False
        task.save()
        self.assertEqual(Profile.objects.get(user=self.alice).points, 0)

        task.complete = True
        task.save()
        self.assertEqual(Profile.objects.get(user=self.alice).points, POINTS_PER_TASK)

    def test_resaving_a_complete_task_without_changing_complete_does_not_change_points(self):
        task = Task.objects.create(user=self.alice, title="Wash car", complete=True)

        task.title = "Wash the car"
        task.save()

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, POINTS_PER_TASK)

    def test_uncompleted_task_awards_no_points(self):
        Task.objects.create(user=self.alice, title="Wash car")

        profile, _ = Profile.objects.get_or_create(user=self.alice)
        self.assertEqual(profile.points, 0)

    def test_toggle_view_awards_points(self):
        self.client.force_login(self.alice)
        task = Task.objects.create(user=self.alice, title="Wash car")

        self.client.post(reverse("task-toggle", args=[task.pk]))

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, POINTS_PER_TASK)

    def test_toggle_view_deducts_points_on_second_toggle(self):
        self.client.force_login(self.alice)
        task = Task.objects.create(user=self.alice, title="Wash car")

        self.client.post(reverse("task-toggle", args=[task.pk]))  # complete -> +10
        self.client.post(reverse("task-toggle", args=[task.pk]))  # incomplete -> -10

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, 0)

    def test_completing_multiple_tasks_accumulates_points(self):
        for title in ("Task A", "Task B", "Task C"):
            Task.objects.create(user=self.alice, title=title, complete=True)

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, POINTS_PER_TASK * 3)

    def test_uncompleting_one_of_several_only_deducts_for_that_task(self):
        tasks = [
            Task.objects.create(user=self.alice, title=title, complete=True)
            for title in ("Task A", "Task B", "Task C")
        ]
        tasks[0].complete = False
        tasks[0].save()

        profile = Profile.objects.get(user=self.alice)
        self.assertEqual(profile.points, POINTS_PER_TASK * 2)


class ThemeShopTests(TestCase):
    """Covers the points-gated theme shop, sourced from the Bootswatch CDN."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")
        self.client.force_login(self.alice)

    def test_requires_login(self):
        self.client.logout()
        resp = self.client.get(reverse("theme-shop"))
        self.assertEqual(resp.status_code, 302)

    def test_default_theme_is_unlocked_and_active_for_new_user(self):
        resp = self.client.get(reverse("theme-shop"))
        default_item = next(
            item for item in resp.context["shop_items"] if item["key"] == DEFAULT_THEME_KEY
        )
        self.assertTrue(default_item["unlocked"])
        self.assertTrue(default_item["active"])
        self.assertEqual(default_item["cost"], 0)

    def test_other_themes_start_locked(self):
        resp = self.client.get(reverse("theme-shop"))
        non_default = [
            item for item in resp.context["shop_items"] if item["key"] != DEFAULT_THEME_KEY
        ]
        self.assertTrue(non_default)
        for item in non_default:
            self.assertFalse(item["unlocked"])
            self.assertIsNotNone(item["css_url"])

    def test_purchasing_a_theme_with_enough_points_unlocks_and_activates_it(self):
        profile = Profile.objects.create(user=self.alice, points=100)
        self.client.post(reverse("theme-select", args=["cyborg"]))

        profile.refresh_from_db()
        self.assertIn("cyborg", profile.unlocked_theme_keys)
        self.assertEqual(profile.active_theme, "cyborg")
        self.assertEqual(profile.points, 100 - 30)

    def test_purchasing_a_theme_without_enough_points_is_blocked(self):
        profile = Profile.objects.create(user=self.alice, points=5)
        self.client.post(reverse("theme-select", args=["cyborg"]))

        profile.refresh_from_db()
        self.assertNotIn("cyborg", profile.unlocked_theme_keys)
        self.assertEqual(profile.active_theme, DEFAULT_THEME_KEY)
        self.assertEqual(profile.points, 5)

    def test_switching_to_an_already_unlocked_theme_is_free(self):
        profile = Profile.objects.create(
            user=self.alice, points=100, unlocked_themes="retrowave,cyborg"
        )
        self.client.post(reverse("theme-select", args=["cyborg"]))

        profile.refresh_from_db()
        self.assertEqual(profile.active_theme, "cyborg")
        self.assertEqual(profile.points, 100)

    def test_unknown_theme_key_is_rejected(self):
        Profile.objects.create(user=self.alice, points=1000)
        resp = self.client.post(reverse("theme-select", args=["not-a-real-theme"]), follow=True)

        rendered_messages = [str(m) for m in resp.context["messages"]]
        self.assertTrue(any("Unknown theme" in m for m in rendered_messages))

    def test_active_theme_css_is_exposed_to_templates(self):
        Profile.objects.create(
            user=self.alice, points=100, active_theme="cyborg", unlocked_themes="retrowave,cyborg"
        )
        resp = self.client.get(reverse("task-list"))
        self.assertIn("bootswatch", resp.context["active_theme"]["css_url"])
        self.assertContains(resp, "bootswatch")

    def test_default_theme_has_no_external_css_link(self):
        Profile.objects.create(user=self.alice)
        resp = self.client.get(reverse("task-list"))
        self.assertIsNone(resp.context["active_theme"]["css_url"])
        self.assertNotContains(resp, "bootswatch")

    def test_no_profile_yet_does_not_break_the_page(self):
        # Mirrors the pre-existing "account predates Profile model" case --
        # the context processor should no-op, not 500.
        resp = self.client.get(reverse("task-list"))
        self.assertEqual(resp.status_code, 200)


class PasswordResetTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create_user(
            "alice", email="alice@example.com", password="OldPassword123!"
        )

    def test_request_form_renders(self):
        resp = self.client.get(reverse("password_reset"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Forgot Your Password?")

    def test_known_email_sends_one_console_email_with_a_working_link(self):
        resp = self.client.post(
            reverse("password_reset"), {"email": "alice@example.com"}, follow=True
        )
        self.assertRedirects(resp, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("alice@example.com", mail.outbox[0].to)
        self.assertIn("/reset/", mail.outbox[0].body)

    def test_unknown_email_does_not_error_or_send_mail(self):
        # Same response either way so the page can't be used to probe which
        # emails have accounts.
        resp = self.client.post(
            reverse("password_reset"), {"email": "nobody@example.com"}, follow=True
        )
        self.assertRedirects(resp, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    def test_full_reset_flow_changes_the_password(self):
        self.client.post(reverse("password_reset"), {"email": "alice@example.com"})
        reset_url = self._extract_reset_url(mail.outbox[0].body)

        # Following the emailed link logs the token and swaps in a one-time
        # "set-password" link, mirroring what a real browser does.
        resp = self.client.get(reset_url, follow=True)
        confirm_url = resp.redirect_chain[-1][0]

        resp = self.client.post(
            confirm_url,
            {"new_password1": "BrandNewPassword456!", "new_password2": "BrandNewPassword456!"},
            follow=True,
        )
        self.assertRedirects(resp, reverse("password_reset_complete"))

        self.client.logout()
        login_ok = self.client.login(username="alice", password="BrandNewPassword456!")
        self.assertTrue(login_ok)

    def test_mismatched_new_passwords_are_rejected(self):
        self.client.post(reverse("password_reset"), {"email": "alice@example.com"})
        reset_url = self._extract_reset_url(mail.outbox[0].body)
        resp = self.client.get(reset_url, follow=True)
        confirm_url = resp.redirect_chain[-1][0]

        self.client.post(
            confirm_url,
            {"new_password1": "BrandNewPassword456!", "new_password2": "SomethingElse789!"},
            follow=True,
        )

        self.client.logout()
        login_ok = self.client.login(username="alice", password="BrandNewPassword456!")
        self.assertFalse(login_ok)

    @staticmethod
    def _extract_reset_url(email_body):
        for line in email_body.splitlines():
            line = line.strip()
            if line.startswith("http://") or line.startswith("https://"):
                return line[line.index("/reset/"):]
        raise AssertionError(f"No reset link found in email body:\n{email_body}")


class DateTimeSelectFieldUnitTests(TestCase):
    """Exercises the Month/Day/Year/Hour/Minute/AM-PM compress() logic directly."""

    def test_all_blank_compresses_to_none(self):
        field = DateTimeSelectField()
        self.assertIsNone(field.compress([]))
        self.assertIsNone(field.compress(["", "", "", "", "", ""]))

    def test_full_value_compresses_to_aware_datetime(self):
        field = DateTimeSelectField()
        result = field.compress(["6", "20", "2026", "5", "30", "PM"])
        expected = timezone.make_aware(timezone.datetime(2026, 6, 20, 17, 30))
        self.assertEqual(result, expected)

    def test_midnight_12am_compresses_to_hour_zero(self):
        field = DateTimeSelectField()
        result = field.compress(["1", "1", "2027", "12", "0", "AM"])
        expected = timezone.make_aware(timezone.datetime(2027, 1, 1, 0, 0))
        self.assertEqual(result, expected)

    def test_noon_12pm_compresses_to_hour_twelve(self):
        field = DateTimeSelectField()
        result = field.compress(["1", "1", "2027", "12", "0", "PM"])
        expected = timezone.make_aware(timezone.datetime(2027, 1, 1, 12, 0))
        self.assertEqual(result, expected)

    def test_partial_date_raises_validation_error(self):
        from django import forms as django_forms

        field = DateTimeSelectField()
        with self.assertRaises(django_forms.ValidationError):
            field.compress(["6", "", "2026", "", "", ""])


class TaskFormDueDateDropdownTests(TestCase):
    """Covers the due-date dropdowns end-to-end through the task create/edit views."""

    def setUp(self):
        self.alice = User.objects.create_user("alice", password="SuperSecret123!")
        self.client.force_login(self.alice)

    def test_leaving_due_date_blank_creates_task_without_one(self):
        self.client.post(
            reverse("task-create"),
            {
                "title": "No due date",
                "description": "",
                "due_date_0": "",
                "due_date_1": "",
                "due_date_2": "",
                "due_date_3": "",
                "due_date_4": "",
                "due_date_5": "",
                "category": "",
            },
        )
        task = Task.objects.get(title="No due date")
        self.assertIsNone(task.due_date)

    def test_filling_in_all_six_dropdowns_sets_the_due_date(self):
        self.client.post(
            reverse("task-create"),
            {
                "title": "Has due date",
                "description": "",
                "due_date_0": "6",
                "due_date_1": "20",
                "due_date_2": "2026",
                "due_date_3": "5",
                "due_date_4": "30",
                "due_date_5": "PM",
                "category": "",
            },
        )
        task = Task.objects.get(title="Has due date")
        expected = timezone.make_aware(timezone.datetime(2026, 6, 20, 17, 30))
        self.assertEqual(task.due_date, expected)

    def test_partially_filled_due_date_is_rejected_with_no_task_created(self):
        resp = self.client.post(
            reverse("task-create"),
            {
                "title": "Bad due date",
                "description": "",
                "due_date_0": "6",
                "due_date_1": "",
                "due_date_2": "",
                "due_date_3": "",
                "due_date_4": "",
                "due_date_5": "",
                "category": "",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Task.objects.filter(title="Bad due date").exists())
        self.assertTrue(resp.context["form"].errors)

    def test_edit_page_for_a_task_with_a_due_date_renders_successfully(self):
        due = timezone.make_aware(timezone.datetime(2026, 12, 25, 9, 15))
        task = Task.objects.create(user=self.alice, title="Christmas", due_date=due)

        resp = self.client.get(reverse("task-update", args=[task.pk]))
        self.assertEqual(resp.status_code, 200)


class DateTimeSelectWidgetUnitTests(TestCase):
    """Covers decompose() -- turning a stored datetime back into the six
    dropdown values used to prefill the edit form."""

    def test_no_value_decompresses_to_all_none(self):
        from .forms import DateTimeSelectWidget

        widget = DateTimeSelectWidget()
        self.assertEqual(widget.decompress(None), [None, None, None, None, None, None])

    def test_aware_datetime_decompresses_to_matching_dropdown_values(self):
        from .forms import DateTimeSelectWidget

        widget = DateTimeSelectWidget()
        due = timezone.make_aware(timezone.datetime(2026, 12, 25, 9, 15))
        self.assertEqual(widget.decompress(due), [12, 25, 2026, 9, 15, "AM"])

    def test_pm_hour_decompresses_with_12_hour_clock_and_pm_marker(self):
        from .forms import DateTimeSelectWidget

        widget = DateTimeSelectWidget()
        due = timezone.make_aware(timezone.datetime(2026, 12, 25, 17, 30))
        self.assertEqual(widget.decompress(due), [12, 25, 2026, 5, 30, "PM"])


class GoogleSignInTests(TestCase):
    """Covers the "Sign in with Google" (django-allauth) integration: the
    button should only appear once GOOGLE_OAUTH_CLIENT_ID/SECRET are set in
    the environment, and a brand-new social signup should get a Profile the
    same way our own register() view creates one."""

    def test_google_button_hidden_when_not_configured(self):
        resp = self.client.get(reverse("login"))
        self.assertNotContains(resp, "Sign in with Google")

        resp = self.client.get(reverse("register"))
        self.assertNotContains(resp, "Sign up with Google")

    @patch.dict(
        os.environ,
        {"GOOGLE_OAUTH_CLIENT_ID": "test-id", "GOOGLE_OAUTH_CLIENT_SECRET": "test-secret"},
    )
    def test_google_button_shown_when_configured(self):
        resp = self.client.get(reverse("login"))
        self.assertContains(resp, "Sign in with Google")

        resp = self.client.get(reverse("register"))
        self.assertContains(resp, "Sign up with Google")

    def test_user_signed_up_signal_creates_profile(self):
        """Simulates what allauth fires right after a brand-new Google
        sign-in, without needing real Google credentials."""
        user = User.objects.create_user(username="googleuser")
        self.assertFalse(Profile.objects.filter(user=user).exists())

        user_signed_up.send(sender=user.__class__, request=None, user=user)

        self.assertTrue(Profile.objects.filter(user=user).exists())

    def test_signal_is_harmless_if_profile_already_exists(self):
        user = User.objects.create_user(username="googleuser2")
        Profile.objects.create(user=user, ai_provider="openai")

        user_signed_up.send(sender=user.__class__, request=None, user=user)

        self.assertEqual(Profile.objects.filter(user=user).count(), 1)
