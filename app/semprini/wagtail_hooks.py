# wagtail_hooks.py
from wagtail.admin.ui.tables import UpdatedAtColumn
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from semprini.models import Subtitle


class SubtitleViewSet(SnippetViewSet):
    model = Subtitle
    icon = "user"
    list_display = ["site", "value", "reference", UpdatedAtColumn()]
    list_per_page = 50
    copy_view_enabled = False
    inspect_view_enabled = True
    admin_url_namespace = "subtitle_views"
    base_url_path = "internal/subtitle"

register_snippet(SubtitleViewSet)
