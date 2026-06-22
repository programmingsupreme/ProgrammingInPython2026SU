"""Natural-language task parsing via OpenAI or Google Gemini.

Given a short free-text note like "remind me to call mom tomorrow at 5pm",
ask the configured AI provider to return structured JSON (title / description /
due_date / category) so we can create a real Task from it.

Designed to fail safely: any problem (missing package, missing API key,
network error, bad JSON) raises AIParseError so the caller can fall back to
just storing the raw text as the task title instead of breaking the page.
"""
import ast
import json
import os
import re

from django.utils import timezone

try:
    import openai
except ImportError:  # pragma: no cover - exercised only if dependency missing
    openai = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:  # pragma: no cover - exercised only if dependency missing
    genai = None
    genai_types = None

try:
    from llama_cpp import Llama
except ImportError:  # pragma: no cover - exercised only if dependency missing
    Llama = None


class AIParseError(Exception):
    """Raised whenever AI parsing can't be completed; callers should fall back."""


DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"

# A small (~2GB), Apache-2.0 instruct model that runs on CPU on most modern
# laptops. llama_cpp.Llama.from_pretrained downloads this from Hugging Face
# the first time the local provider is used and caches it under
# ~/.cache/huggingface, so every later call (and every other user, on a
# shared deployment) reuses the same on-disk copy. Override via
# LOCAL_MODEL_REPO/LOCAL_MODEL_FILE, or point LOCAL_MODEL_PATH at a .gguf
# file already on disk to skip the download entirely.
DEFAULT_LOCAL_MODEL_REPO = "lmstudio-community/Qwen2.5-3B-Instruct-GGUF"
DEFAULT_LOCAL_MODEL_FILE = "*Q4_K_M.gguf"

VALID_CATEGORIES = {"work", "personal", "shopping", "health", "errands", "other"}

SYSTEM_PROMPT = (
    "You turn a short, informally written to-do note into structured task data. "
    "Reply with ONLY a single JSON object and nothing else (no prose, no markdown "
    "fences), matching this exact shape: "
    '{"title": string, "description": string|null, "due_date": string|null, '
    '"category": string}. '
    "Rules: "
    "title is a short imperative summary, 80 characters or fewer. "
    "description holds any extra detail from the note, or null if there isn't any. "
    "due_date is an ISO 8601 datetime (YYYY-MM-DDTHH:MM:SS) if the note mentions any "
    "date or time, absolute or relative (e.g. 'tomorrow', 'next Friday at 5pm'), "
    "resolved against the current date/time given to you below. If no date/time is "
    "mentioned, due_date must be null. "
    "category must be exactly one of: work, personal, shopping, health, errands, other "
    "-- pick whichever best fits the note; use \"other\" if none clearly fit."
)

_ENV_VAR_BY_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def _shared_key(provider):
    return os.environ.get(_ENV_VAR_BY_PROVIDER.get(provider, ""), "")


def has_configured_key(provider="openai", api_key=None):
    """True if there's any key to use for this provider -- either the one
    passed in (e.g. a user's personal key) or the matching shared env var.

    The local provider runs entirely on-machine and never needs a key, so
    it's always reported as "configured" here; if the model genuinely isn't
    usable (package missing, download failed), that surfaces as an
    AIParseError instead, which the caller shows as a different message."""
    if provider == "local":
        return True
    return bool(api_key) or bool(_shared_key(provider))


def _clean_exception_message(exc):
    """Best-effort short, human-readable text for an SDK exception.

    The OpenAI/Gemini client libraries often stringify HTTP errors as a
    status line followed by the raw error body, e.g.:
        503 UNAVAILABLE. {'error': {'code': 503, 'message': 'The model is
        overloaded. Please try again later.', 'status': 'UNAVAILABLE'}}
    That whole structure isn't something a user should have to read. If the
    string contains a dict literal with a nested "message", pull out just
    that (plus the leading HTTP status code, if any) instead. Falls back to
    the exception's own string unchanged if it doesn't look like one of
    these -- e.g. plain messages like "network timeout" pass straight
    through.
    """
    text = str(exc)
    brace = text.find("{")
    if brace == -1:
        return text

    try:
        data = ast.literal_eval(text[brace:])
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return text

    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict) or not error.get("message"):
        return text

    status_match = re.match(r"\s*(\d{3})\b", text)
    prefix = f"{status_match.group(1)}: " if status_match else ""
    return f"{prefix}{error['message']}"


def local_runtime_available():
    """True if the llama-cpp-python package is installed, i.e. the local
    provider can at least attempt to load/download a model."""
    return Llama is not None


def _get_openai_client(api_key=None):
    if openai is None:
        raise AIParseError("the 'openai' package is not installed")

    api_key = api_key or _shared_key("openai")
    if not api_key:
        raise AIParseError("no OpenAI API key is configured")

    return openai.OpenAI(api_key=api_key)


def _get_gemini_client(api_key=None):
    if genai is None:
        raise AIParseError("the 'google-genai' package is not installed")

    api_key = api_key or _shared_key("gemini")
    if not api_key:
        raise AIParseError("no Gemini API key is configured")

    return genai.Client(api_key=api_key)


def _call_openai(text, now, api_key):
    client = _get_openai_client(api_key=api_key)
    model = os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)

    response = client.chat.completions.create(
        model=model,
        max_tokens=300,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Current date/time: {now.isoformat()}\nNote: {text}",
            },
        ],
    )
    return response.choices[0].message.content.strip()


def _call_gemini(text, now, api_key):
    client = _get_gemini_client(api_key=api_key)
    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    response = client.models.generate_content(
        model=model,
        contents=f"Current date/time: {now.isoformat()}\nNote: {text}",
        config=genai_types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
        ),
    )
    return (response.text or "").strip()


# The loaded local model is cached at module level -- loading it is the slow
# part (first call downloads it; even from cache, constructing a Llama
# instance takes a couple seconds), so every quick-add request after the
# first reuses the same in-memory instance instead of reloading it.
_local_llm = None


def _get_local_llm():
    global _local_llm
    if _local_llm is not None:
        return _local_llm

    if Llama is None:
        raise AIParseError("the 'llama-cpp-python' package is not installed")

    model_path = os.environ.get("LOCAL_MODEL_PATH")
    try:
        if model_path:
            _local_llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)
        else:
            repo_id = os.environ.get("LOCAL_MODEL_REPO", DEFAULT_LOCAL_MODEL_REPO)
            filename = os.environ.get("LOCAL_MODEL_FILE", DEFAULT_LOCAL_MODEL_FILE)
            _local_llm = Llama.from_pretrained(
                repo_id=repo_id, filename=filename, n_ctx=2048, verbose=False
            )
    except Exception as exc:
        raise AIParseError(
            f"couldn't load local model: {_clean_exception_message(exc)}"
        ) from exc

    return _local_llm


def _call_local(text, now, api_key):
    llm = _get_local_llm()
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Current date/time: {now.isoformat()}\nNote: {text}",
            },
        ],
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    return response["choices"][0]["message"]["content"].strip()


_CALLERS = {
    "openai": _call_openai,
    "gemini": _call_gemini,
    "local": _call_local,
}


def parse_task_text(text, now=None, provider="openai", api_key=None):
    """Return {"title": str, "description": str|None, "due_date": aware datetime|None,
    "category": str (one of VALID_CATEGORIES, or "" if unrecognized)}.

    provider selects which AI to call ("openai" or "gemini"). api_key, if given
    (e.g. a user's personal key for that provider), takes priority over that
    provider's shared environment variable.

    Raises AIParseError on any failure (caller decides the fallback behavior).
    """
    text = (text or "").strip()
    if not text:
        raise AIParseError("empty input")

    caller = _CALLERS.get(provider)
    if caller is None:
        raise AIParseError(f"unknown AI provider: {provider}")

    now = now or timezone.localtime(timezone.now())

    try:
        raw = caller(text, now, api_key)
        data = json.loads(raw)
    except AIParseError:
        raise
    except Exception as exc:  # network/auth/parsing errors, etc.
        raise AIParseError(_clean_exception_message(exc)) from exc

    title = (data.get("title") or "").strip() or text[:200]
    description = data.get("description") or None

    due_date = None
    due_date_raw = data.get("due_date")
    if due_date_raw:
        try:
            due_date = timezone.datetime.fromisoformat(due_date_raw)
        except ValueError:
            due_date = None
        else:
            if timezone.is_naive(due_date):
                due_date = timezone.make_aware(due_date)

    category = (data.get("category") or "").strip().lower()
    if category not in VALID_CATEGORIES:
        category = ""

    return {
        "title": title[:200],
        "description": description,
        "due_date": due_date,
        "category": category,
    }
