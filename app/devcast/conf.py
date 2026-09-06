"""Every project-tunable value devcast reads, in one place.

Nothing else in the package touches ``django.conf.settings``: keeping the reads
here is what lets devcast be lifted out into a standalone distribution later.
"""

from django.conf import settings


def _get(name, default):
    return getattr(settings, f"DEVCAST_{name}", default)


def page_base():
    """Dotted path to the Page class devcast's page types inherit from.

    Defaults to plain Wagtail. semprini points it at ``puput.models.EntryPage``
    so project and audio pages join the blog's listing, feeds and archives.
    Changing this after the first migration changes the table shape, so it has
    to be decided up front.
    """
    return _get("PAGE_BASE", "wagtail.models.Page")


def puput_integration():
    return _get("PUPUT_INTEGRATION", False)


def base_template():
    """Template devcast pages extend. It must provide ``content`` and
    ``extra_content`` blocks; this site points it at puput's, so project pages
    keep the blog header, avatar and sidebar."""
    return _get("BASE_TEMPLATE", "base.html")


def changelog_initial_releases():
    """How many releases render expanded-capable before the rest are collapsed."""
    return _get("CHANGELOG_INITIAL_RELEASES", 10)


def engines():
    """Engine name -> dotted path. Downstream projects add their own without
    forking; credentials never appear here, only in the environment."""
    return _get("ENGINES", {"elevenlabs": "devcast.speech.elevenlabs.ElevenLabsEngine"})


def default_engine():
    return _get("DEFAULT_ENGINE", "elevenlabs")


def default_voice():
    """Fallback voice for a site with no ``Voice`` snippet configured, as
    ``{"key", "label", "engine", "engine_voice_id", "settings"}``."""
    return _get("DEFAULT_VOICE", None)


def max_script_chars():
    """Hard reject: a page whose script exceeds this is never sent anywhere."""
    return _get("MAX_SCRIPT_CHARS", 60000)


def monthly_char_budget():
    """Characters the worker may synthesize per calendar month, across all
    pages. Exceeding it fails jobs loudly rather than spending quietly."""
    return _get("MONTHLY_CHAR_BUDGET", 250000)


def max_segment_chars():
    """Longer segments are split on sentence boundaries before synthesis.

    Bigger is better for prosody - the model reads a whole passage with one
    intonation arc - so this sits well below the engine's per-request ceiling
    (10,000 characters for eleven_multilingual_v2) rather than near a sentence.
    """
    return _get("MAX_SEGMENT_CHARS", 5000)


def segment_gap_ms():
    """Silence inserted between segments, which also separates cues audibly."""
    return _get("SEGMENT_GAP_MS", 350)


def render_attempts():
    return _get("RENDER_ATTEMPTS", 3)


def lease_seconds():
    """How long a worker owns a job before another may steal it."""
    return _get("LEASE_SECONDS", 900)


def ffmpeg():
    return _get("FFMPEG", "ffmpeg")


def ffprobe():
    return _get("FFPROBE", "ffprobe")


def audio_prefix():
    return _get("AUDIO_PREFIX", "narration")


def keep_previous_renditions():
    """Retained superseded renditions per page, so a permalink shared during a
    re-render still has something to play."""
    return _get("KEEP_PREVIOUS_RENDITIONS", 1)
