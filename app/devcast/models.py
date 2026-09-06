from collections import Counter
import hashlib
import json

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.module_loading import import_string
from django.utils.translation import gettext_lazy as _
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.documents import get_document_model_string
from wagtail.fields import RichTextField, StreamField
from wagtail.images import get_image_model_string
from wagtail.models import Orderable, Page
from wagtail.search import index
from wagtailmarkdown.fields import MarkdownField

from . import conf
from .blocks import NARRATABLE_BLOCKS, SHOWCASE_BLOCKS

# Which Page class the devcast page types extend is a deployment decision: this
# site grafts them onto puput's EntryPage so they inherit its URLs, feeds and
# archives. See conf.page_base().
PageBase = import_string(conf.page_base())


class ProjectStatus(models.TextChoices):
    CONCEPT = "concept", _("Concept")
    PROTOTYPE = "prototype", _("Prototype")
    ALPHA = "alpha", _("Alpha")
    BETA = "beta", _("Beta")
    RELEASED = "released", _("Released")
    MAINTENANCE = "maintenance", _("Maintenance")
    SHELVED = "shelved", _("Shelved")


class ChangeKind(models.TextChoices):
    ADDED = "added", _("Added")
    CHANGED = "changed", _("Changed")
    FIXED = "fixed", _("Fixed")
    REMOVED = "removed", _("Removed")
    NOTE = "note", _("Note")


class RoadmapState(models.TextChoices):
    PLANNED = "planned", _("Planned")
    IN_PROGRESS = "in_progress", _("In progress")
    DONE = "done", _("Done")
    DROPPED = "dropped", _("Dropped")


class ProjectStackTag(TaggedItemBase):
    """Tech-stack tags, kept in their own namespace so they never mix with the
    blog's topic tags in sidebars and archives."""

    content_object = ParentalKey("devcast.DevProjectPage", related_name="stack_tags")


class DevProjectPage(PageBase):
    tagline = models.CharField(
        max_length=200,
        blank=True,
        verbose_name=_("tagline"),
        help_text=_("One line shown under the title and on cards."),
    )
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.CONCEPT
    )
    started_on = models.DateField(null=True, blank=True, verbose_name=_("started"))
    hero_image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    hero_model = models.ForeignKey(
        get_document_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("hero 3D model"),
        help_text=_("A .glb shown in place of the hero image."),
    )
    repo_url = models.URLField(blank=True, verbose_name=_("source"))
    demo_url = models.URLField(blank=True, verbose_name=_("live demo"))
    download_url = models.URLField(blank=True, verbose_name=_("download"))
    stack = ClusterTaggableManager(through=ProjectStackTag, blank=True)
    showcase = StreamField(SHOWCASE_BLOCKS, blank=True, verbose_name=_("showcase"))

    content_panels = PageBase.content_panels + [
        MultiFieldPanel(
            [
                FieldPanel("tagline"),
                FieldPanel("status"),
                FieldPanel("started_on"),
                FieldPanel("hero_image"),
                FieldPanel("hero_model"),
                FieldPanel("stack"),
            ],
            heading=_("Project"),
        ),
        MultiFieldPanel(
            [
                FieldPanel("repo_url"),
                FieldPanel("demo_url"),
                FieldPanel("download_url"),
                InlinePanel("links", label=_("Extra link")),
            ],
            heading=_("Links"),
        ),
        FieldPanel("showcase"),
        InlinePanel("features", label=_("Feature")),
        InlinePanel("roadmap", label=_("Roadmap item")),
        InlinePanel("changelog", label=_("Change")),
    ]

    search_fields = PageBase.search_fields + [index.SearchField("tagline")]

    subpage_types = []

    class Meta:
        verbose_name = _("Dev project")

    @property
    def updated(self):
        """When the project last changed, for the 'evergreen page' case where
        the publish date says little."""
        return self.last_published_at or self.latest_revision_created_at

    @property
    def has_3d(self):
        """Whether the page needs the GLB viewer, which pulls in three.js."""
        if self.hero_model_id:
            return True
        return any(block.block_type == "model3d" for block in self.showcase)

    @property
    def changelog_groups(self):
        """Changelog rows collapsed into releases, newest first."""
        groups = []
        for entry in self.changelog.all().order_by("-released_on", "sort_order"):
            key = (entry.version, entry.released_on)
            if not groups or groups[-1]["key"] != key:
                groups.append(
                    {
                        "key": key,
                        "version": entry.version,
                        "released_on": entry.released_on,
                        "entries": [],
                    }
                )
            groups[-1]["entries"].append(entry)
        for group in groups:
            counts = Counter(entry.kind for entry in group["entries"])
            group["counts"] = [
                {"kind": kind, "label": ChangeKind(kind).label, "count": count}
                for kind, count in counts.items()
            ]
        return groups

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        groups = self.changelog_groups
        limit = conf.changelog_initial_releases()
        show_all = request.GET.get("releases") == "all"
        context["base_template"] = conf.base_template()
        context["changelog_groups"] = groups if show_all else groups[:limit]
        context["changelog_truncated"] = not show_all and len(groups) > limit
        context["changelog_total"] = len(groups)
        return context


class ProjectLink(Orderable):
    page = ParentalKey(DevProjectPage, on_delete=models.CASCADE, related_name="links")
    label = models.CharField(max_length=60)
    url = models.URLField()
    icon = models.CharField(
        max_length=40,
        blank=True,
        help_text=_("Font Awesome name without the 'fa-' prefix, e.g. 'github'."),
    )

    panels = [FieldPanel("label"), FieldPanel("url"), FieldPanel("icon")]

    def __str__(self):
        return self.label


class ProjectFeature(Orderable):
    page = ParentalKey(DevProjectPage, on_delete=models.CASCADE, related_name="features")
    title = models.CharField(max_length=80)
    description = models.CharField(max_length=250, blank=True)
    icon = models.CharField(max_length=40, blank=True)

    panels = [FieldPanel("title"), FieldPanel("description"), FieldPanel("icon")]

    def __str__(self):
        return self.title


class RoadmapItem(Orderable):
    page = ParentalKey(DevProjectPage, on_delete=models.CASCADE, related_name="roadmap")
    title = models.CharField(max_length=120)
    state = models.CharField(
        max_length=20, choices=RoadmapState.choices, default=RoadmapState.PLANNED
    )

    panels = [FieldPanel("title"), FieldPanel("state")]

    def __str__(self):
        return self.title


class ChangelogEntry(Orderable):
    page = ParentalKey(DevProjectPage, on_delete=models.CASCADE, related_name="changelog")
    version = models.CharField(
        max_length=40,
        blank=True,
        help_text=_("Leave empty for changes that are not tied to a release."),
    )
    released_on = models.DateField(verbose_name=_("date"))
    kind = models.CharField(
        max_length=20, choices=ChangeKind.choices, default=ChangeKind.CHANGED
    )
    summary = models.CharField(max_length=200)
    detail = MarkdownField(blank=True)
    image = models.ForeignKey(
        get_image_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    commit_url = models.URLField(blank=True, verbose_name=_("commit or PR"))

    panels = [
        FieldPanel("version"),
        FieldPanel("released_on"),
        FieldPanel("kind"),
        FieldPanel("summary"),
        FieldPanel("detail"),
        FieldPanel("image"),
        FieldPanel("commit_url"),
    ]

    class Meta(Orderable.Meta):
        verbose_name = _("change")
        verbose_name_plural = _("changes")

    def __str__(self):
        return f"{self.version} {self.summary}".strip()


class AudioEntryPage(PageBase):
    intro = RichTextField(blank=True)
    sections = StreamField(NARRATABLE_BLOCKS, blank=True, verbose_name=_("sections"))
    narration_enabled = models.BooleanField(default=True)
    voice = models.ForeignKey(
        "devcast.Voice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="pages",
        verbose_name=_("voice"),
        help_text=_("Leave empty to use the site's default voice."),
    )
    manual_audio = models.ForeignKey(
        get_document_model_string(),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        verbose_name=_("narration audio"),
        help_text=_("Uploaded audio. Generated narration replaces this later."),
    )
    audio_duration = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_("audio length (seconds)"),
        help_text=_("Used as the end of the final cue."),
    )

    content_panels = PageBase.content_panels + [
        FieldPanel("intro"),
        FieldPanel("sections"),
        MultiFieldPanel(
            [
                FieldPanel("narration_enabled"),
                FieldPanel("voice"),
                FieldPanel("manual_audio"),
                FieldPanel("audio_duration"),
                InlinePanel("cues", label=_("Cue")),
            ],
            heading=_("Narration"),
        ),
    ]

    search_fields = PageBase.search_fields + [index.SearchField("sections")]

    subpage_types = []

    class Meta:
        verbose_name = _("Audio entry")
        verbose_name_plural = _("Audio entries")

    def clean(self):
        # puput insists on body or markdown_body; for an audio entry the
        # sections are the content.
        if self.sections and not (self.body or self.markdown_body):
            Page.clean(self)
        else:
            super().clean()

    @property
    def audio_url(self):
        return self.manual_audio.url if self.manual_audio else None

    @property
    def has_3d(self):
        return any(block.block_type == "model3d" for block in self.sections)

    @property
    def narration(self):
        """``(rendition, stale)`` for the generated narration, if any."""
        from .narration import current_rendition

        if not self.narration_enabled:
            return None, False
        return current_rendition(self)

    @property
    def cue_track(self):
        """The cue payload the player consumes.

        A generated rendition wins when there is one. Otherwise hand-authored
        cues bind to blocks by position, which is throwaway authoring
        ergonomics; the JSON that comes out is the same block-id keyed shape
        either way, so the player never has to know the difference.
        """
        if not self.narration_enabled:
            return None

        rendition, stale = self.narration
        if rendition:
            return rendition.track(stale=stale)

        if not self.audio_url:
            return None
        blocks = list(self.sections)
        cues = list(self.cues.all().order_by("sort_order"))
        if not (blocks and cues):
            return None

        entries = []
        for position, cue in enumerate(cues[: len(blocks)]):
            block = blocks[position]
            following = cues[position + 1] if position + 1 < len(cues) else None
            entries.append(
                {
                    "id": str(block.id),
                    "start": cue.start,
                    "end": following.start if following else self.audio_duration,
                    "kind": block.block_type,
                }
            )
        return {
            "version": 1,
            "audio": {"src": self.audio_url, "duration": self.audio_duration},
            "stale": False,
            "cues": entries,
        }

    def narration_script(self):
        """The segments the speech engine reads."""
        from .narration import build_script

        return build_script(self)

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["base_template"] = conf.base_template()
        context["cue_track"] = self.cue_track
        return context


class AudioCue(Orderable):
    page = ParentalKey(AudioEntryPage, on_delete=models.CASCADE, related_name="cues")
    start = models.FloatField(
        verbose_name=_("starts at (seconds)"),
        help_text=_("Cues bind to sections in order: the first cue times the first section."),
    )
    note = models.CharField(max_length=120, blank=True)

    panels = [FieldPanel("start"), FieldPanel("note")]

    def __str__(self):
        return f"{self.start}s {self.note}".strip()


class DevProjectIndexPage(Page):
    intro = RichTextField(blank=True)

    content_panels = Page.content_panels + [FieldPanel("intro")]

    class Meta:
        verbose_name = _("Dev project index")

    def get_projects(self, request):
        projects = (
            DevProjectPage.objects.live().public().order_by("-last_published_at")
        )
        stack = request.GET.get("stack")
        if stack:
            projects = projects.filter(stack_tags__tag__slug=stack)
        status = request.GET.get("status")
        if status in ProjectStatus.values:
            projects = projects.filter(status=status)
        return projects

    def get_context(self, request, *args, **kwargs):
        context = super().get_context(request, *args, **kwargs)
        context["base_template"] = conf.base_template()
        context["projects"] = self.get_projects(request)
        context["selected_stack"] = request.GET.get("stack", "")
        context["selected_status"] = request.GET.get("status", "")
        if conf.puput_integration() and "blog_page" not in context:
            from .integrations.puput import default_blog_page

            context["blog_page"] = default_blog_page(request)
        return context


class Voice(models.Model):
    """A narrator. One is the default for a site, and a page may override it.

    Deliberately holds **no credentials** - engines read API keys from the
    environment, so an editor picks a voice, never a key.
    """

    site = models.ForeignKey(
        "wagtailcore.Site", on_delete=models.CASCADE, related_name="narration_voices"
    )
    key = models.SlugField(
        max_length=60, help_text=_("Stable identifier used by --voice and in logs.")
    )
    label = models.CharField(max_length=120)
    engine = models.CharField(max_length=32, default="elevenlabs")
    engine_voice_id = models.CharField(
        max_length=64, help_text=_("The provider's id for this voice.")
    )

    # The four sliders on the ElevenLabs voice page, plus speaker boost. Each is
    # nullable, and empty means "leave the provider's own default alone" rather
    # than sending a value we invented.
    speed = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.7), MaxValueValidator(1.2)],
        help_text=_("0.7 slowest to 1.2 fastest. 1.0 is unmodified. Empty uses 1.0."),
    )
    stability = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text=_(
            "0.0 to 1.0. Lower is more expressive and more variable between "
            "renders; higher is steadier but flatter. Empty uses 0.5."
        ),
    )
    similarity_boost = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name=_("similarity"),
        help_text=_(
            "0.0 to 1.0. How closely to match the original voice. Very high "
            "values can reproduce artefacts from the source recording. "
            "Empty uses 0.75."
        ),
    )
    style = models.FloatField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        verbose_name=_("style exaggeration"),
        help_text=_(
            "0.0 to 1.0. Amplifies the speaker's delivery. Anything above 0 "
            "costs latency and can destabilise long passages. Empty uses 0.0."
        ),
    )
    use_speaker_boost = models.BooleanField(
        null=True,
        blank=True,
        help_text=_("Increases similarity to the original speaker. Empty uses on."),
    )
    extra_settings = models.JSONField(
        default=dict,
        blank=True,
        help_text=_(
            "Escape hatch for engine parameters that have no field above. "
            "Merged into the request as-is."
        ),
    )
    is_default = models.BooleanField(default=False)

    panels = [
        FieldPanel("site"),
        FieldPanel("key"),
        FieldPanel("label"),
        FieldPanel("engine"),
        FieldPanel("engine_voice_id"),
        MultiFieldPanel(
            [
                FieldPanel("speed"),
                FieldPanel("stability"),
                FieldPanel("similarity_boost"),
                FieldPanel("style"),
                FieldPanel("use_speaker_boost"),
                FieldPanel("extra_settings"),
            ],
            heading=_("Delivery"),
        ),
        FieldPanel("is_default"),
    ]

    class Meta:
        verbose_name = _("voice")
        constraints = [
            models.UniqueConstraint(fields=["site", "key"], name="devcast_voice_key"),
            models.UniqueConstraint(
                fields=["site"],
                condition=models.Q(is_default=True),
                name="devcast_one_default_voice_per_site",
            ),
        ]

    def __str__(self):
        return f"{self.label} ({self.key})"

    @property
    def engine_settings(self):
        """What actually goes on the wire. Unset sliders are omitted entirely,
        so the provider's defaults stay the provider's business."""
        tuning = {
            "speed": self.speed,
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "use_speaker_boost": self.use_speaker_boost,
        }
        settings = {key: value for key, value in tuning.items() if value is not None}
        settings.update(self.extra_settings or {})
        return settings

    @property
    def tuning_rev(self):
        """A fingerprint of the delivery settings, so retuning a voice
        invalidates renditions the same way an engine upgrade does."""
        payload = json.dumps(
            self.engine_settings, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:8]


class RenditionStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    RENDERING = "rendering", _("Rendering")
    READY = "ready", _("Ready")
    FAILED = "failed", _("Failed")


def narration_path(instance, filename):
    """Content-addressed, with no user-controlled path components: the object is
    immutable, so it can be cached forever."""
    return "{prefix}/{page}/{digest}.mp3".format(
        prefix=conf.audio_prefix(),
        page=instance.page_id or "utterance",
        digest=f"{instance.script_hash[:32]}-{instance.engine_rev[:16]}",
    )


class Rendition(models.Model):
    """One narration of one script by one voice.

    ``page`` is nullable and points at ``Page`` rather than ``AudioEntryPage``
    so the same pipeline can later voice standalone avatar utterances.
    """

    page = models.ForeignKey(
        "wagtailcore.Page",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="narrations",
    )
    voice = models.ForeignKey(Voice, on_delete=models.PROTECT, related_name="renditions")
    script_hash = models.CharField(max_length=64, db_index=True)
    engine = models.CharField(max_length=32)
    engine_rev = models.CharField(
        max_length=64, help_text=_("Model revision plus voice tuning fingerprint.")
    )
    status = models.CharField(
        max_length=20, choices=RenditionStatus.choices, default=RenditionStatus.PENDING
    )
    audio = models.FileField(upload_to=narration_path, blank=True)
    duration_ms = models.IntegerField(null=True, blank=True)
    cues = models.JSONField(default=list, blank=True)
    words = models.JSONField(default=list, blank=True)
    visemes = models.JSONField(default=list, blank=True)
    char_count = models.IntegerField(default=0)
    cost_cents = models.IntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("narration")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["page", "voice", "script_hash", "engine_rev"],
                name="devcast_rendition_unique",
            )
        ]
        permissions = [("render_narration", _("Can render narration"))]

    def __str__(self):
        return f"{self.script_hash[:8]} {self.voice_id} {self.status}"

    @property
    def duration_s(self):
        return (self.duration_ms or 0) / 1000

    def track(self, *, stale=False):
        """The payload the player consumes."""
        return {
            "version": 1,
            "audio": {"src": self.audio.url, "duration": self.duration_s},
            "voice": self.voice.key,
            "hash": self.script_hash,
            "stale": stale,
            "cues": self.cues,
            "words": self.words,
        }


class JobState(models.TextChoices):
    QUEUED = "queued", _("Queued")
    LEASED = "leased", _("Leased")
    DONE = "done", _("Done")
    FAILED = "failed", _("Failed")
    CANCELLED = "cancelled", _("Cancelled")


class RenderJob(models.Model):
    """Work for the narrator container. Leasing is what keeps a duplicate start
    from paying twice for the same audio."""

    rendition = models.OneToOneField(
        Rendition, on_delete=models.CASCADE, related_name="job"
    )
    state = models.CharField(
        max_length=20, choices=JobState.choices, default=JobState.QUEUED, db_index=True
    )
    leased_by = models.CharField(max_length=120, blank=True)
    leased_until = models.DateTimeField(null=True, blank=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("render job")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.rendition_id} {self.state}"
