# Full-Stack To-Do List Web Application

A Django web app where each user registers an account, logs in, and manages their own private to-do list (create, view, complete, edit, delete tasks). Built per `proposal.pdf`.

## Project layout

```
todo_project/      # Django project settings/urls
tasks/              # The to-do list app (models, views, forms, templates)
templates/          # Shared templates: base.html, login/register/password reset
static/tasks/css/   # Stylesheet
manage.py
requirements.txt
```

## Data model

- `User` — Django's built-in auth user (username, email, hashed password).
- `Task` — `user` (FK to User), `title`, `description` (optional), `due_date` (optional — picked via Month/Day/Year/Hour/Minute/AM-PM dropdowns rather than a raw date/time input), `complete` (bool), `completed_at` (auto-managed timestamp, set/cleared whenever `complete` flips), `category` (optional, one of work/personal/shopping/health/errands/other — auto-assigned by AI quick-add or set manually), `created` (auto timestamp). See `todo_db_uml.png` for the original diagram (`due_date`, `completed_at`, and `category` were added later).
- `Profile` — `user` (one-to-one with User), `openai_api_key` (optional, per-user), `gemini_api_key` (optional, per-user), `ai_provider` (which AI powers this user's quick-add — `"openai"`, `"gemini"`, or `"local"`, default `"openai"`), `points` (int, earned by completing tasks), `active_theme` / `unlocked_themes` (which Theme Shop look is currently selected, and which ones this user has bought). Added later so each user can supply their own key(s) for AI quick-add instead of relying on a single shared key, choose which provider to use (including a local, key-free model), and so the points/theme system has somewhere to live.

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Create the database tables
python manage.py migrate

# 4. (Optional) create an admin account
python manage.py createsuperuser

# 5. Run the development server
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` — you'll be redirected to log in. Use **Register** to create an account, then start adding tasks.

## Features

- Register / log in / log out (Django's built-in auth system + a custom register view), plus an optional **"Sign in with Google"** button (via [django-allauth](https://docs.allauth.org)) that lets you register/log in with a Google account instead of a password. See "Google sign-in setup" below — without it configured, the button just doesn't appear and password auth works exactly as before.
- **Forgot your password?** (`/password-reset/`): enter your account email and get a one-time reset link. In dev, no real email account is needed — the email prints to the terminal running `manage.py runserver` (Django's console email backend). See "Password reset emails" below for how to send real ones instead.
- Create, list, edit, and delete tasks. The due date field is a set of Month/Day/Year/Hour/Minute/AM-PM dropdowns rather than a single date/time input — leave all six blank for no due date, or fill in all six; a partially-filled date is rejected with a validation error.
- One-click toggle to mark a task complete/incomplete.
- **AI quick-add**: type a plain-English note (e.g. "remind me to call mom tomorrow at 5pm") and your preferred AI provider — ChatGPT via the OpenAI API, Google Gemini, or a model that runs locally on your own machine via [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — parses it into a title, optional description, optional due date, and a category. A small "i" icon next to the **Add with AI** button explains this on hover. See setup below — without an API key (and without choosing the local provider) it still works, it just saves your note as-is.
- **Calendar page** (`/calendar/`): every completed task, grouped by the day it was completed and showing the time it was checked off.
- **Lists page** (`/lists/`): your tasks grouped by category (Work, Personal, Shopping, Health, Errands, Other, or Uncategorized) — categories are assigned automatically by AI quick-add, or can be set by hand from a task's Edit page.
- **Per-user API keys + provider choice**: each user can add, change, or remove their own OpenAI key and/or Gemini key independently from the **Settings** page (linked in the navbar) — optionally during registration, or anytime after — and pick which provider is active for their quick-add requests via a "Preferred AI provider" selector, including a third **Local model** option that needs no key at all. Both cloud keys are kept even when only one is active, so switching providers later doesn't require re-entering a key. Neither key is ever displayed back in full, only masked (e.g. `••••••••3456`).
- **Points + Theme Shop** (`/shop/`): completing a task earns 10 points (shown in the navbar, e.g. "★ 30 pts"); un-completing it takes those 10 back (your balance never drops below 0), so points always mirror which tasks are currently checked off rather than accumulating permanently. Points can be spent in the Shop to unlock additional site-wide looks. The default Retrowave look is hand-built (`static/tasks/css/style.css`) and always free; every other theme (Cyborg, Vapor, Darkly, Solar, Superhero, Lux) is a real, free stylesheet fetched live from [Bootswatch](https://bootswatch.com) over its jsDelivr CDN — nothing about a purchased theme's colors or fonts is hardcoded in this app, it's just a `<link>` tag pointed at `tasks/themes.py`'s registry of CDN URLs. Switching to a theme you've already unlocked is free. Because the app's own CSS happens to reuse plain Bootstrap-style class names (`.btn`, `.btn-primary`, `.container`, `.navbar`, etc.), loading a Bootswatch stylesheet visibly recolors the navbar, buttons, page background, links, and headings sitewide — task cards and lists keep their retrowave panel styling either way.
- Each user only ever sees and can act on their own tasks — every query is filtered by `request.user`, and direct URL access to another user's task returns 404.
- Admin site (`/admin/`) for inspecting all users/tasks (superuser only). The admin list for profiles shows only whether a key is set, never the key itself.

## AI quick-add setup

The quick-add box calls the OpenAI API, the Google Gemini API, or a model running locally on your own machine (in `tasks/ai.py`) to turn your note into a structured task, depending on which provider is selected in **Settings** → "Preferred AI provider" (OpenAI by default). For OpenAI/Gemini, there are two ways to provide a key, and either is enough on its own:

**Option A — per-user key (recommended):** Register an account and paste your key into the optional OpenAI/Gemini field on the registration form, or add/update/remove either key later from **Settings** (top nav once logged in) — you can hold both keys at once and switch providers freely. Get an OpenAI key at [platform.openai.com](https://platform.openai.com/api-keys) (API keys), or a Gemini key at [aistudio.google.com](https://aistudio.google.com/apikey) (API keys). Each user's key is stored in the database and used only for that user's quick-add requests; a per-user key always takes priority over the matching shared key below.

**Option B — shared/global key (`.env`):** Useful for local dev so the feature works for every account without each one adding a key.

1. Copy `.env.example` to `.env` in the project root and paste in the key for whichever provider(s) you want to enable:
   ```
   OPENAI_API_KEY=sk-...
   GEMINI_API_KEY=AIza-...
   ```
   `.env` is gitignored — never commit a real key.
2. Restart `manage.py runserver` so it picks up the new environment variable(s).

**Option C — local model (no key, no cost, no account):** Pick **Local model** as your preferred provider (at registration or later from Settings) and quick-add parsing runs entirely on your own machine via [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — listed in `requirements.txt`, so `pip install -r requirements.txt` already pulls it in. There's nothing else to configure:

- The first quick-add request after picking Local model downloads a small (~2GB) instruct model from Hugging Face (`lmstudio-community/Qwen2.5-3B-Instruct-GGUF` by default) and caches it under `~/.cache/huggingface`; every request after that (and every other user on a shared deployment) reuses the cached copy, so the download only happens once.
- To use a different model, set `LOCAL_MODEL_REPO` / `LOCAL_MODEL_FILE` in `.env` to any other GGUF repo/file on Hugging Face, or set `LOCAL_MODEL_PATH` to a `.gguf` file you already have on disk to skip the download entirely. See `.env.example` for all three.
- `pip install llama-cpp-python` ships prebuilt wheels for most common platforms; on a platform without one, pip falls back to compiling from source, which needs a C/C++ compiler installed (e.g. `build-essential` on Debian/Ubuntu, Xcode Command Line Tools on macOS).
- Local inference runs on CPU by default and has no per-call cost or external network dependency once the model is cached, but it's noticeably slower than the cloud providers (especially on a laptop with no GPU) and needs a few GB of free RAM while a request is in flight.
- The app automatically pre-loads the local model in the background as soon as the server starts, but only if at least one account already has Local model selected — so it doesn't slow down or use RAM on a server where nobody uses it. This shifts the one-time load/download wait to server startup instead of someone's first quick-add after a restart; switching to Local model for the first time still loads the model on that first request, same as before. It can't speed up the per-request inference time itself (see the previous bullet).

**Cost:** each cloud quick-add call is one short request — to `gpt-4o-mini` for OpenAI (configurable via `OPENAI_MODEL` in `.env`), or `gemini-3.5-flash` for Gemini (configurable via `GEMINI_MODEL`) — both providers' cheapest/fastest general-purpose models, a few hundred tokens and fractions of a cent per call. Check current pricing at [openai.com/api/pricing](https://openai.com/api/pricing/) or [ai.google.dev/pricing](https://ai.google.dev/pricing) before heavy use. The local provider has no per-call cost at all (just the one-time download and the compute/RAM on your own machine).

**No key configured for the active provider (and not using Local model)?** The feature degrades gracefully: quick-add still creates a task using your note as the title, with a banner that links straight to the Settings page to add a key for whichever provider is selected (the correct article — "add an OpenAI API key" vs. "add a Gemini API key" — is used automatically).

**A key is configured but the call still fails** (network blip, rate limit, the provider's API itself returning an error)? The same graceful fallback applies, and the warning banner shows a short, cleaned-up reason rather than the raw error payload some SDKs return — e.g. a Gemini "503 model overloaded" response shows as `503: The model is currently overloaded...` instead of the full nested JSON error body.

## Password reset emails

By default the app uses Django's console email backend: a "forgot password" email is printed to the terminal running `manage.py runserver` instead of being delivered anywhere, so the whole flow works out of the box with no email account or extra setup. Just copy the reset link from the console output into your browser.

To send real emails instead (e.g. once deployed), add SMTP settings to `.env` — no code changes needed. Using Gmail:

1. Turn on 2-Step Verification on the Gmail account you want to send from, if it isn't already: [myaccount.google.com/signinoptions/two-step-verification](https://myaccount.google.com/signinoptions/two-step-verification). An App Password can't be created without this.
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), sign in again if prompted, type a name like "Django todo app," and click **Create**. Google shows a 16-character password (4 groups of 4) — copy it now, it's only shown once.
3. Open `.env` in the project root (copy from `.env.example` first if you haven't already) and add:
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_HOST_USER=you@gmail.com
   EMAIL_HOST_PASSWORD=your-16-char-app-password
   DEFAULT_FROM_EMAIL=you@gmail.com
   ```
   Use the 16-character App Password from step 2 for `EMAIL_HOST_PASSWORD`, not your normal Gmail login password — Google rejects SMTP logins with the real password once 2-Step Verification is on. `.env` is gitignored, so this never gets committed.
4. Restart `manage.py runserver` so it picks up the new settings, then verify delivery without going through the full password-reset flow:
   ```bash
   python manage.py sendtestemail your-address@example.com
   ```
   If that email arrives, real "forgot password" emails will too. If it doesn't, double check steps 1–3 (the most common issue is pasting the App Password with spaces still in it, or using the account password instead).

See `.env.example` for the same SMTP block, commented out, ready to fill in.

## Google sign-in setup

The "Sign in with Google" button on the login/register pages is powered by [django-allauth](https://docs.allauth.org) and needs a Google OAuth Client ID/Secret to work. Without them set, the button is simply hidden and password auth is unaffected.

1. Go to the [Google Cloud Console credentials page](https://console.cloud.google.com/apis/credentials) and create a project if you don't already have one (top-left project dropdown → **New Project**).
2. Configure the consent screen first (Google requires this before it'll let you create credentials): in the left sidebar go to **APIs & Services → OAuth consent screen**. Choose **External** (unless you have a Google Workspace org and want Internal), fill in an app name and your support email, and save through the remaining steps — for local dev/testing you don't need to submit for verification.
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
4. For **Application type**, choose **Web application**. Give it any name (e.g. "Todo app local dev").
5. Under **Authorized JavaScript origins**, add: `http://127.0.0.1:8000`
6. Under **Authorized redirect URIs**, add: `http://127.0.0.1:8000/accounts/google/login/callback/`
   (If you deploy this app later, add a second origin/redirect pair for your real domain — `https://yourdomain.com` and `https://yourdomain.com/accounts/google/login/callback/`.)
7. Click **Create**. Google shows a **Client ID** (ends in `.apps.googleusercontent.com`) and **Client Secret** — copy both.
8. Open `.env` in the project root (copy from `.env.example` first if you haven't already) and add:
   ```
   GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
   ```
   `.env` is gitignored, so these never get committed.
9. Restart `manage.py runserver`. The "Sign in with Google" / "Sign up with Google" button now appears on the login and register pages. The first time a given Google account signs in, it creates a new local account automatically (no separate "pick a username" step) and a `Profile` for it, exactly like registering with a password — you can add API keys, switch AI provider, etc. from Settings afterward either way.

If the consent screen is still in "Testing" mode (rather than "In production"), only Google accounts you've explicitly added as test users (OAuth consent screen → Test users) will be able to sign in — add your own Google account there while testing locally.

## Automated tests

```bash
python manage.py test
```

Covers registration/login, per-user task isolation (404 on cross-user access), per-user API key management for both OpenAI and Gemini (add/update/remove via Settings, optional keys at registration, switching the preferred provider, masked-key display), the local model provider (always reports as "configured" with no key, loads/caches the model exactly once across repeated calls, falls back cleanly with `AIParseError` if `llama-cpp-python` is missing or the model fails to load, and `LOCAL_MODEL_PATH` correctly skips the Hugging Face download), the background warm-up that pre-loads the local model at server startup (only kicks off a background thread when some account actually has Local model selected, never during `test`/`migrate`/other management commands, and only once even under the dev autoreloader's watcher/subprocess split), automatic `completed_at` tracking, the Calendar and Lists views, the AI quick-add view for all three providers (including category auto-assignment), the due-date dropdowns (blank submission, fully-filled submission with 12-hour AM/PM conversion, partial submission rejected), points tracking (completing a task awards points, un-completing it deducts them back down to a floor of 0), the Theme Shop (locked/unlocked state, purchase success/failure, free re-activation of an already-owned theme), the password reset flow (request email, unknown email is handled the same way so it can't be used to probe which addresses have accounts, full reset-and-login round trip, mismatched new passwords rejected), and Google sign-in (the button only renders when `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` are set, and a simulated social signup gets a `Profile` the same way password registration does) — all three providers' calls are mocked in tests (no real download, network call, or inference happens), password reset emails are captured in Django's test outbox rather than actually sent, and the Google sign-in tests never contact Google, so running the suite never costs money, sends real email, downloads a model, or needs real credentials.

## Manual test checklist

- [ ] Register two different accounts in two browser sessions (or use incognito).
- [ ] Add tasks under each account; confirm each only sees their own.
- [ ] Try visiting `/task/<id>/edit/` for a task that belongs to the other user — should 404.
- [ ] Mark a task complete, confirm it visually updates and re-sorts, and shows up on the Calendar page under today's date with the correct time.
- [ ] Un-complete a task, confirm it disappears from the Calendar page.
- [ ] Delete a task, confirm the confirmation page and removal.
- [ ] Log out, confirm task pages redirect to login.
- [ ] Register a new account with an OpenAI API key filled in; confirm Settings shows it as saved (masked).
- [ ] Register a new account with `ai_provider` set to Gemini and a Gemini key filled in; confirm Settings shows Gemini as the active provider and the Gemini key as saved (masked).
- [ ] Register a new account leaving both API keys blank; confirm quick-add falls back to plain text with a friendly message linking to Settings.
- [ ] From Settings, add an OpenAI key, then update it, then remove it; confirm each action updates the status badge. Repeat for the Gemini key.
- [ ] From Settings, switch "Preferred AI provider" from OpenAI to Gemini and back; confirm the displayed active provider updates and the previously-saved key for each provider is unaffected by the switch.
- [ ] With a key set for the active provider (per-user or shared `.env` var), try quick-add with a note that includes a relative date/time; confirm the due date is parsed correctly and the task lands under the right category on the Lists page. Try this once with OpenAI active and once with Gemini active.
- [ ] Without any key configured for the active provider, try quick-add; confirm it still creates a task (using the raw text, uncategorized) and shows the friendly "add an API key" message instead of erroring.
- [ ] From Settings, switch "Preferred AI provider" to **Local model** and confirm the card above the selector shows whether `llama-cpp-python` is installed ("Ready" vs. "Not installed").
- [ ] With Local model active, try quick-add with a note that includes a relative date/time; confirm the first request downloads the default model (this can take a while) and later requests reuse the cached copy and are noticeably faster; confirm the due date and category are still parsed correctly.
- [ ] With at least one account already set to Local model, restart `manage.py runserver`; confirm the model starts loading in the background right away (check the console) rather than waiting for the first quick-add request after the restart.
- [ ] On the New/Edit Task form, manually set a category and confirm it appears under the right group on the Lists page.
- [ ] On the New Task form, leave all six due-date dropdowns (Month/Day/Year/Hour/Minute/AM-PM) blank and confirm the task saves with no due date.
- [ ] Fill in all six due-date dropdowns, including a 12:00 AM and a 12:00 PM case, and confirm the saved/displayed due date matches (12 AM → midnight, 12 PM → noon).
- [ ] Fill in only some of the six due-date dropdowns and confirm the form rejects the submission with a validation error instead of silently dropping the partial date.
- [ ] Edit a task that already has a due date and confirm the six dropdowns are pre-filled with its current date/time.
- [ ] Complete a task, confirm the points badge in the navbar increases by 10; un-complete it, confirm the badge drops back by 10.
- [ ] Visit the Shop page (`/shop/`) with too few points, confirm locked themes show their cost and a disabled "Need N pts" button.
- [ ] Earn or set enough points, unlock a paid theme (e.g. Cyborg), and confirm points are deducted, the theme shows "Unlocked," and the navbar/buttons/background visibly change everywhere while task cards/lists keep their retrowave styling.
- [ ] Switch back to an already-unlocked theme and confirm no points are deducted the second time.
- [ ] From the login page, click "Forgot your password?", enter a registered email, and confirm a reset link is printed to the terminal running `runserver`.
- [ ] Follow that link, set a new password, and confirm you can log in with it (and not with the old one).
- [ ] Request a reset for an email that isn't registered and confirm you get the same "check your email" page (no error, no hint that the account doesn't exist).
- [ ] With `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` set in `.env`, confirm "Sign in with Google" / "Sign up with Google" appears on the login/register pages; with them unset (or commented out), confirm the button is gone and password login/register still work normally.
- [ ] Click "Sign in with Google," complete the Google consent screen with a test-user Google account, and confirm you land back in the app logged in, with a new account and Profile created automatically on first sign-in.
- [ ] Sign in again with the same Google account and confirm it logs into the existing account rather than creating a duplicate.

## Deployment

Not yet deployed — see Day 10 of the project plan in `proposal.pdf`. Before deploying: set `DEBUG = False`, set `DJANGO_SECRET_KEY` in `.env` to a freshly generated value (see `.env.example` for the one-liner that generates one — don't reuse the dev fallback key in `settings.py`), set `ALLOWED_HOSTS`, and run `python manage.py collectstatic`.
