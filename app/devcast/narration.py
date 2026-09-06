"""Deciding what to narrate, when to pay for it, and stitching the result.

The one rule that keeps this cheap: a rendition is identified by *what it says*
(``script_hash``), *who says it* (``voice``) and *how* (``engine_rev``). Anything
that already exists is never synthesized again.
"""

import hashlib
import re
import socket
import unicodedata
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from . import conf
from .models import JobState, RenderJob, Rendition, RenditionStatus, Voice
from .speech import EngineError, Segment, get_engine
from .speech import segmenter
from .speech.base import truncate_error

_WHITESPACE = re.compile(r"\s+")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


class BudgetExceeded(EngineError):
    """The month's character budget is spent. Deliberately loud."""


def normalise(text):
    """What the hash is taken over. Cosmetic edits must not burn credits, so
    whitespace and unicode form are flattened first."""
    return _WHITESPACE.sub(" ", unicodedata.normalize("NFC", str(text or ""))).strip()


def sanitise(text):
    """What is actually sent to a provider: printable characters only."""
    cleaned = "".join(
        ch for ch in normalise(text) if ch == " " or not unicodedata.category(ch).startswith("C")
    )
    return cleaned


def build_script(page):
    """``[Segment]`` - the single source of truth for narration."""
    segments = []
    for block in page.sections:
        narrate = getattr(block.block, "narration_text", None)
        text = sanitise(narrate(block.value)) if narrate else ""
        if text:
            segments.append(Segment(block_id=str(block.id), kind=block.block_type, text=text))
    return segments


def script_hash(segments):
    payload = "\x1f".join(f"{s.block_id}\x1e{normalise(s.text)}" for s in segments)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def script_chars(segments):
    return sum(len(s.text) for s in segments)


def resolve_voice(site=None):
    """The site's default voice, or one materialised from ``DEVCAST_DEFAULT_VOICE``
    so a fresh install can render before anyone opens the admin."""
    voices = Voice.objects.filter(is_default=True)
    if site is not None:
        voices = voices.filter(site=site)
    voice = voices.order_by("pk").first()
    if voice:
        return voice

    fallback = conf.default_voice()
    if not fallback or site is None:
        return None
    tuning = {
        field: fallback[field]
        for field in ("speed", "stability", "similarity_boost", "style", "use_speaker_boost")
        if field in fallback
    }
    voice, _created = Voice.objects.get_or_create(
        site=site,
        key=fallback.get("key", "default"),
        defaults={
            "label": fallback.get("label", "Default"),
            "engine": fallback.get("engine", conf.default_engine()),
            "engine_voice_id": fallback.get("engine_voice_id", ""),
            "extra_settings": fallback.get("extra_settings", {}),
            "is_default": True,
            **tuning,
        },
    )
    return voice


def voice_for_page(page):
    """The page's own voice if an editor picked one, otherwise the site's."""
    from wagtail.models import Site

    chosen = getattr(page, "voice", None)
    if chosen is not None:
        return chosen

    site = page.get_site() or Site.objects.filter(is_default_site=True).first()
    return resolve_voice(site)


def engine_revision(engine_name, voice):
    """Model revision plus voice tuning, so both invalidate old renditions."""
    try:
        revision = get_engine(engine_name).revision
    except EngineError:
        # No credentials here (the web container has none); the revision is
        # still deterministic from the engine class.
        revision = engine_name
    return f"{revision}+{voice.tuning_rev}"


def current_rendition(page):
    """``(rendition, stale)``: the audio to play, and whether the page has been
    edited since it was recorded."""
    ready = Rendition.objects.filter(
        page_id=page.pk, status=RenditionStatus.READY
    ).exclude(audio="")
    digest = script_hash(build_script(page))
    fresh = ready.filter(script_hash=digest).order_by("-created_at").first()
    if fresh:
        return fresh, False
    return ready.order_by("-created_at").first(), True


@transaction.atomic
def queue_render(page, voice=None, force=False):
    """Ensure a rendition exists for the page's current script.

    Returns the rendition, or ``None`` when there is nothing to narrate.
    """
    if not getattr(page, "narration_enabled", False):
        return None

    segments = build_script(page)
    if not segments:
        return None

    chars = script_chars(segments)
    if chars > conf.max_script_chars():
        raise BudgetExceeded(
            f"Script is {chars} characters, over DEVCAST_MAX_SCRIPT_CHARS "
            f"({conf.max_script_chars()})"
        )

    voice = voice or voice_for_page(page)
    if voice is None:
        return None

    digest = script_hash(segments)
    revision = engine_revision(voice.engine, voice)

    rendition, created = Rendition.objects.get_or_create(
        page_id=page.pk,
        voice=voice,
        script_hash=digest,
        engine_rev=revision,
        defaults={"engine": voice.engine, "char_count": chars},
    )

    if not created and rendition.status == RenditionStatus.READY and not force:
        _cancel_superseded(page, keep=rendition)
        return rendition

    if rendition.status in (RenditionStatus.FAILED, RenditionStatus.READY) or force:
        rendition.status = RenditionStatus.PENDING
        rendition.error = ""
        rendition.char_count = chars
        rendition.save(update_fields=["status", "error", "char_count"])

    job, job_created = RenderJob.objects.get_or_create(rendition=rendition)
    if not job_created and job.state in (JobState.DONE, JobState.FAILED, JobState.CANCELLED):
        job.state = JobState.QUEUED
        job.attempts = 0
        job.last_error = ""
        job.save(update_fields=["state", "attempts", "last_error"])

    _cancel_superseded(page, keep=rendition)
    return rendition


def _cancel_superseded(page, keep):
    """An edit during a render makes the in-flight job obsolete: stop it before
    it bills rather than after."""
    RenderJob.objects.filter(
        rendition__page_id=page.pk, state=JobState.QUEUED
    ).exclude(rendition_id=keep.pk).update(state=JobState.CANCELLED)


def month_char_usage(now=None):
    now = now or timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        Rendition.objects.filter(
            status=RenditionStatus.READY, completed_at__gte=start
        ).aggregate(total=Sum("char_count"))["total"]
        or 0
    )


def claim_job(worker=None):
    """Lease one queued job. ``skip_locked`` plus the lease fence means two
    workers can never pay for the same synthesis."""
    worker = worker or f"{socket.gethostname()}"
    now = timezone.now()
    with transaction.atomic():
        job = (
            RenderJob.objects.select_for_update(skip_locked=True)
            .filter(
                Q(state=JobState.QUEUED)
                | Q(state=JobState.LEASED, leased_until__lt=now)
            )
            .filter(attempts__lt=conf.render_attempts())
            .order_by("created_at")
            .first()
        )
        if job is None:
            return None
        job.state = JobState.LEASED
        job.leased_by = worker[:120]
        job.leased_until = now + timedelta(seconds=conf.lease_seconds())
        job.attempts += 1
        job.save(update_fields=["state", "leased_by", "leased_until", "attempts"])
    return job


def split_text(text, limit):
    """Split on sentence boundaries so no single request is oversized. The
    pieces stay in one cue, so the reader never sees the seam."""
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for sentence in _SENTENCE.split(text):
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > limit:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    # A single sentence longer than the limit still has to go somewhere.
    return [chunk[:limit] for chunk in chunks if chunk]


def _merge_cues(cues):
    """Sub-segments of one block collapse back into that block's single cue."""
    merged = []
    for cue in cues:
        if merged and merged[-1]["id"] == cue["id"]:
            merged[-1]["end"] = cue["end"]
        else:
            merged.append(dict(cue))
    return merged


def render(rendition, engine=None):
    """Synthesize, join, and store. Raises ``EngineError`` on failure."""
    page = rendition.page.specific if rendition.page_id else None
    if page is None:
        raise EngineError("Rendition has no page")

    segments = build_script(page)
    if not segments:
        raise EngineError("Nothing to narrate")
    if script_hash(segments) != rendition.script_hash:
        raise EngineError("Page changed since this rendition was queued")

    budget = conf.monthly_char_budget()
    chars = script_chars(segments)
    if budget and month_char_usage() + chars > budget:
        raise BudgetExceeded(
            f"DEVCAST_MONTHLY_CHAR_BUDGET ({budget}) would be exceeded by this render"
        )

    engine = engine or get_engine(rendition.voice.engine)

    rendition.status = RenditionStatus.RENDERING
    rendition.save(update_fields=["status"])

    limit = conf.max_segment_chars()
    pieces = [
        Segment(segment.block_id, segment.kind, chunk)
        for segment in segments
        for chunk in split_text(segment.text, limit)
    ]

    # Each piece is generated on its own so cue boundaries stay exact, but it is
    # told what surrounds it, so the article is read as one continuous piece
    # instead of a stack of cold starts.
    clips = [
        engine.synthesize(
            piece.text,
            rendition.voice,
            previous_text=pieces[index - 1].text if index else "",
            next_text=pieces[index + 1].text if index + 1 < len(pieces) else "",
        )
        for index, piece in enumerate(pieces)
    ]

    result = segmenter.render(pieces, clips)

    rendition.audio.save(
        "narration.mp3", ContentFile(result.audio), save=False
    )
    rendition.duration_ms = int(round(result.duration_s * 1000))
    rendition.cues = _merge_cues(result.cues)
    rendition.words = result.words
    rendition.char_count = chars
    rendition.status = RenditionStatus.READY
    rendition.error = ""
    rendition.completed_at = timezone.now()
    rendition.save()
    return rendition


def run_job(job, engine=None):
    """Render one leased job, recording failure rather than raising."""
    try:
        render(job.rendition, engine=engine)
    except EngineError as exc:
        message = truncate_error(exc)
        rendition = job.rendition
        rendition.status = RenditionStatus.FAILED
        rendition.error = message
        rendition.save(update_fields=["status", "error"])
        job.last_error = message
        job.state = (
            JobState.FAILED if job.attempts >= conf.render_attempts() else JobState.QUEUED
        )
        job.save(update_fields=["last_error", "state"])
        return False

    job.state = JobState.DONE
    job.last_error = ""
    job.leased_until = None
    job.save(update_fields=["state", "last_error", "leased_until"])
    prune_page(job.rendition.page_id)
    return True


def prune_page(page_id, keep_previous=None):
    """Keep the newest ready rendition plus a configured number of previous
    ones, so a link shared mid-re-render still plays."""
    if not page_id:
        return 0
    keep_previous = conf.keep_previous_renditions() if keep_previous is None else keep_previous
    ready = list(
        Rendition.objects.filter(page_id=page_id, status=RenditionStatus.READY).order_by(
            "-created_at"
        )
    )
    removed = 0
    for rendition in ready[1 + keep_previous :]:
        rendition.audio.delete(save=False)
        rendition.delete()
        removed += 1
    return removed
