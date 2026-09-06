from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.admin.action_menu import ActionMenuItem
from wagtail.admin.ui.tables import Column, DateColumn
from wagtail.admin.widgets import PageListingButton
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from . import views
from .models import AudioEntryPage, Rendition, Voice


class VoiceViewSet(SnippetViewSet):
    """The narrator. One default per site - there is no per-page picker."""

    model = Voice
    icon = "user"
    menu_label = _("Voices")
    menu_name = "narration_voices"
    list_display = ["label", "key", "engine", "site"]
    search_fields = ["key", "label"]
    add_to_admin_menu = False


class RenditionViewSet(SnippetViewSet):
    """What has been rendered, what it cost, and what failed."""

    model = Rendition
    icon = "media"
    menu_label = _("Narrations")
    menu_name = "narrations"
    list_display = [
        "__str__",
        Column("page", label=_("Page")),
        Column("status", label=_("Status")),
        Column("char_count", label=_("Characters")),
        Column("billed_chars", label=_("Bought")),
        DateColumn("created_at", label=_("Queued")),
    ]
    list_filter = ["status", "voice"]
    ordering = ["-created_at"]
    add_view_enabled = False
    copy_view_enabled = False
    inspect_view_enabled = True
    inspect_view_fields = [
        "page", "voice", "engine", "engine_rev", "script_hash",
        "status", "audio", "duration_ms", "char_count", "billed_chars", "error",
        "created_at", "completed_at",
    ]


register_snippet(VoiceViewSet)
register_snippet(RenditionViewSet)


@hooks.register("register_admin_urls")
def devcast_admin_urls():
    return [
        path(
            "devcast/render-narration/<int:page_id>/",
            views.render_narration,
            name="devcast_render_narration",
        )
    ]


@hooks.register("register_page_listing_more_buttons")
def render_narration_button(page, user, view_name=None, next_url=None):
    # Deliberately no freshness label here: working it out costs several
    # queries per row, and the explorer lists every blog entry.
    if not isinstance(page.specific_deferred, AudioEntryPage):
        return
    if not user.has_perm("devcast.render_narration"):
        return
    yield PageListingButton(
        _("Render narration"),
        reverse("devcast_render_narration", args=[page.pk]),
        icon_name="media",
        priority=60,
    )


class RenderNarrationMenuItem(ActionMenuItem):
    """Sits alongside Save and Publish: rendering is an editorial decision
    about this page, not a background chore."""

    name = "action-render-narration"
    label = _("Render narration")
    icon_name = "media"
    order = 60

    def is_shown(self, context):
        page = context.get("page")
        return (
            context["view"] == "edit"
            and isinstance(page, AudioEntryPage)
            and page.narration_enabled
            and context["request"].user.has_perm("devcast.render_narration")
        )

    def get_url(self, context):
        return reverse("devcast_render_narration", args=[context["page"].pk])


@hooks.register("register_page_action_menu_item")
def render_narration_menu_item():
    return RenderNarrationMenuItem()
