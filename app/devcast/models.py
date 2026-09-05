from collections import Counter

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
from .blocks import SHOWCASE_BLOCKS

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
