"""Deciding what to narrate, when to pay for it, and stitching the result.

The one rule that keeps this cheap: a rendition is identified by *what it says*
(``script_hash``), *who says it* (``voice``) and *how* (``engine_rev``). Anything
that already exists is never synthesized again.
"""

import hashlib
import re
import socket
import unicodedata
from dataclasses import dataclass, field
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from . import conf
from .models import (
    JobState,
    RenderJob,
    Rendition,
    RenditionStatus,
    SegmentClip,
    Voice,
)
from .speech import EngineError, Segment, get_engine, get_engine_class
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


def text_hash(text):
    """Identity of a single spoken passage, independent of where it sits.

    Deliberately not keyed on the block id: moving a section must not re-buy it.
    """
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


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
        revision = getattr(get_engine_class(engine_name), "revision", engine_name)
    except EngineError:
        revision = engine_name
    # An engine that is not configured here, or that only reveals its revision
    # once constructed, is still identified by name - the value has to be
    # deterministic wherever it is computed, credentials or not.
    if not isinstance(revision, str):
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
    """Characters actually bought this month. Reused clips cost nothing, so
    they are not counted against the budget."""
    now = now or timezone.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (
        Rendition.objects.filter(
            status=RenditionStatus.READY, completed_at__gte=start
        ).aggregate(total=Sum("billed_chars"))["total"]
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


def split_pieces(segments):
    """The script as the engine will actually be asked for it."""
    limit = conf.max_segment_chars()
    return [
        Segment(segment.block_id, segment.kind, chunk)
        for segment in segments
        for chunk in split_text(segment.text, limit)
    ]


def clip_cache(digests, voice, revision):
    """``{text_hash: SegmentClip}`` for passages this voice has already read."""
    if not digests:
        return {}
    clips = SegmentClip.objects.filter(
        voice=voice, engine_rev=revision, text_hash__in=set(digests)
    ).exclude(audio="")
    return {clip.text_hash: clip for clip in clips}


def store_clip(voice, revision, text, digest, clip):
    """Bank a freshly synthesized passage so the next publish is cheaper."""
    record = SegmentClip(
        voice=voice,
        engine_rev=revision,
        text_hash=digest,
        char_count=len(text),
        duration_ms=int(round(clip.duration_s * 1000)) if clip.duration_s else None,
        words=clip.words,
    )
    record.audio.save("clip.mp3", ContentFile(clip.audio), save=False)
    record.save()
    return record


def forget_clips(page, voice=None):
    """Drop the cached audio for a page's current script, so the next render
    buys every section again. The 're-record everything' escape hatch."""
    voice = voice or voice_for_page(page)
    if voice is None:
        return 0
    digests = [text_hash(piece.text) for piece in split_pieces(build_script(page))]
    removed = 0
    for clip in SegmentClip.objects.filter(voice=voice, text_hash__in=set(digests)):
        clip.audio.delete(save=False)
        clip.delete()
        removed += 1
    return removed


def prune_clips(days=None):
    """Forget passages nothing has asked for in a long time. Losing one only
    costs a re-synthesis, so the cache is allowed to be lossy."""
    days = conf.clip_cache_days() if days is None else days
    if not days:
        return 0
    cutoff = timezone.now() - timedelta(days=days)
    removed = 0
    for clip in SegmentClip.objects.filter(last_used_at__lt=cutoff):
        clip.audio.delete(save=False)
        clip.delete()
        removed += 1
    return removed


@dataclass
class RenderPlan:
    """What a render would actually buy, as opposed to what it would produce."""

    sections: int = 0
    resynthesized: int = 0
    chars: int = 0
    billable_chars: int = 0
    voice: object = None

    @property
    def reused(self):
        return self.sections - self.resynthesized

    @property
    def is_free(self):
        return self.billable_chars == 0


def render_plan(page, voice=None, segments=None):
    segments = build_script(page) if segments is None else segments
    voice = voice or voice_for_page(page)
    plan = RenderPlan(
        sections=len(segments), chars=script_chars(segments), voice=voice
    )
    if not segments or voice is None:
        plan.resynthesized = plan.sections
        plan.billable_chars = plan.chars
        return plan

    pieces = split_pieces(segments)
    digests = [text_hash(piece.text) for piece in pieces]
    cached = clip_cache(digests, voice, engine_revision(voice.engine, voice))
    missing = [
        (piece, digest)
        for piece, digest in zip(pieces, digests)
        if digest not in cached
    ]
    plan.resynthesized = len({piece.block_id for piece, _digest in missing})
    plan.billable_chars = sum(len(piece.text) for piece, _digest in missing)
    return plan


@dataclass
class NarrationState:
    """Whether a page's audio still matches the page, phrased for an editor."""

    code: str
    label: str
    detail: str = ""
    rendition: object = None
    plan: RenderPlan = field(default_factory=RenderPlan)

    CSS = {
        "current": "help-info",
        "queued": "help-info",
        "rendering": "help-info",
        "stale": "help-warning",
        "none": "help-warning",
        "no_voice": "help-warning",
        "failed": "help-critical",
    }

    @property
    def is_current(self):
        return self.code == "current"

    @property
    def css_class(self):
        return self.CSS.get(self.code, "help-info")


def narration_state(page):
    """The freshness of a page's generated audio, for the admin to display."""
    if not getattr(page, "narration_enabled", False):
        return NarrationState(
            "disabled",
            _("Narration is off"),
            _("Turn narration on to generate audio for this page."),
        )

    segments = build_script(page)
    if not segments:
        return NarrationState(
            "empty",
            _("Nothing to narrate"),
            _("None of the sections contain anything that can be read aloud."),
        )

    voice = voice_for_page(page)
    if voice is None:
        return NarrationState(
            "no_voice",
            _("No voice configured"),
            _("Add a voice and mark it as the site default before rendering."),
        )

    plan = render_plan(page, voice=voice, segments=segments)
    suffix = f"+{voice.tuning_rev}"
    current = (
        Rendition.objects.filter(
            page_id=page.pk,
            script_hash=script_hash(segments),
            voice=voice,
            engine_rev__endswith=suffix,
        )
        .order_by("-created_at")
        .first()
    )

    if current and current.status == RenditionStatus.READY and current.audio:
        return NarrationState(
            "current",
            _("Audio is up to date"),
            _("%(voice)s, %(sections)s sections, recorded %(when)s.")
            % {
                "voice": voice.label,
                "sections": plan.sections,
                "when": (current.completed_at or current.created_at).strftime(
                    "%d %b %Y %H:%M"
                ),
            },
            rendition=current,
            plan=plan,
        )

    if current and current.status == RenditionStatus.RENDERING:
        return NarrationState(
            "rendering",
            _("Recording now"),
            _("%(count)s of %(total)s sections are being synthesized.")
            % {"count": plan.resynthesized, "total": plan.sections},
            rendition=current,
            plan=plan,
        )

    if current and current.status == RenditionStatus.PENDING:
        return NarrationState(
            "queued",
            _("Queued for recording"),
            _("%(count)s of %(total)s sections will be synthesized; the rest are reused.")
            % {"count": plan.resynthesized, "total": plan.sections},
            rendition=current,
            plan=plan,
        )

    if current and current.status == RenditionStatus.FAILED:
        return NarrationState(
            "failed",
            _("Last render failed"),
            current.error or _("No reason was recorded."),
            rendition=current,
            plan=plan,
        )

    previous = (
        Rendition.objects.filter(page_id=page.pk, status=RenditionStatus.READY)
        .exclude(audio="")
        .order_by("-created_at")
        .first()
    )
    if previous is None:
        return NarrationState(
            "none",
            _("No audio yet"),
            _("Publishing the page, or rendering it by hand, records all %(total)s sections.")
            % {"total": plan.sections},
            plan=plan,
        )

    voice_changed = previous.voice_id != voice.pk or not previous.engine_rev.endswith(
        suffix
    )
    if voice_changed:
        detail = _(
            "The voice has changed, so all %(total)s sections will be re-recorded."
        ) % {"total": plan.sections}
    else:
        detail = _(
            "%(count)s of %(total)s sections have changed; the other %(reused)s "
            "are reused from the existing audio."
        ) % {
            "count": plan.resynthesized,
            "total": plan.sections,
            "reused": plan.reused,
        }
    return NarrationState(
        "stale", _("Audio is out of date"), detail, rendition=previous, plan=plan
    )


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
    """Synthesize what is new, reuse what is not, join, and store.

    Raises ``EngineError`` on failure.
    """
    page = rendition.page.specific if rendition.page_id else None
    if page is None:
        raise EngineError("Rendition has no page")

    segments = build_script(page)
    if not segments:
        raise EngineError("Nothing to narrate")
    if script_hash(segments) != rendition.script_hash:
        raise EngineError("Page changed since this rendition was queued")

    voice = rendition.voice
    pieces = split_pieces(segments)
    digests = [text_hash(piece.text) for piece in pieces]
    # The rendition carries the revision it was queued under, so the cache is
    # keyed on exactly what this recording claims to be.
    cached = clip_cache(digests, voice, rendition.engine_rev)

    chars = script_chars(segments)
    billable = sum(
        len(piece.text)
        for piece, digest in zip(pieces, digests)
        if digest not in cached
    )

    budget = conf.monthly_char_budget()
    if budget and billable and month_char_usage() + billable > budget:
        raise BudgetExceeded(
            f"DEVCAST_MONTHLY_CHAR_BUDGET ({budget}) would be exceeded by this render"
        )

    engine = engine or get_engine(rendition.voice.engine)

    rendition.status = RenditionStatus.RENDERING
    rendition.save(update_fields=["status"])

    # Each piece is generated on its own so cue boundaries stay exact, but it is
    # told what surrounds it, so the article is read as one continuous piece
    # instead of a stack of cold starts. A cached piece is reused as it stands:
    # that context only shapes delivery, and the words are identical.
    clips = []
    for index, (piece, digest) in enumerate(zip(pieces, digests)):
        stored = cached.get(digest)
        if stored is not None:
            clips.append(stored.as_clip())
            continue
        clip = engine.synthesize(
            piece.text,
            voice,
            previous_text=pieces[index - 1].text if index else "",
            next_text=pieces[index + 1].text if index + 1 < len(pieces) else "",
        )
        # Banked immediately: a failure halfway through a long article must not
        # throw away the passages already paid for.
        cached[digest] = store_clip(voice, rendition.engine_rev, piece.text, digest, clip)
        clips.append(clip)

    SegmentClip.objects.filter(
        pk__in=[clip.pk for clip in cached.values()]
    ).update(last_used_at=timezone.now())

    result = segmenter.render(pieces, clips)

    rendition.audio.save(
        "narration.mp3", ContentFile(result.audio), save=False
    )
    rendition.duration_ms = int(round(result.duration_s * 1000))
    rendition.cues = _merge_cues(result.cues)
    rendition.words = result.words
    rendition.char_count = chars
    rendition.billed_chars = billable
    rendition.status = RenditionStatus.READY
    rendition.error = ""
    rendition.completed_at = timezone.now()
    rendition.save()
    return rendition

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
