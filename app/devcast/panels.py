"""Admin panels that report on narration rather than edit it."""

from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, Panel, PanelGroup


def without_fields(panels, *field_names):
    """``panels`` with every ``FieldPanel`` for the named fields removed.

    Panel trees are shared by reference - a page type builds its own by
    concatenating its parent's list - so a group that loses a child is cloned
    rather than edited, leaving the parent's editor untouched.
    """
    kept = []
    for panel in panels:
        if isinstance(panel, FieldPanel) and panel.field_name in field_names:
            continue
        if isinstance(panel, PanelGroup):
            panel = panel.clone()
            panel.children = without_fields(panel.children, *field_names)
        kept.append(panel)
    return kept


class NarrationStatusPanel(Panel):
    """Says, in the editor, whether the generated audio still matches the page.

    Without it the only way to know a published page is speaking an old draft is
    to open the Narrations listing and compare hashes.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("heading", _("Audio status"))
        super().__init__(**kwargs)

    class BoundPanel(Panel.BoundPanel):
        template_name = "devcast/admin/narration_status_panel.html"

        def is_shown(self):
            # A page that has never been saved has no sections to compare.
            return self.instance is not None and self.instance.pk is not None

        def get_context_data(self, parent_context=None):
            from django.urls import reverse

            from .narration import narration_state

            context = super().get_context_data(parent_context)
            context["state"] = narration_state(self.instance)
            context["render_url"] = reverse(
                "devcast_render_narration", args=[self.instance.pk]
            )
            context["can_render"] = bool(
                self.request
                and self.request.user.has_perm("devcast.render_narration")
            )
            return context


class DiagramTargetsPanel(Panel):
    """Lists what a diagram's animation script is allowed to target.

    Writing a script means naming shapes and connectors by their draw.io cell
    id, and half of them carry no label at all - every connector and every
    interface port. Without this list in front of you the ids are unguessable.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("heading", _("Targets"))
        super().__init__(**kwargs)

    class BoundPanel(Panel.BoundPanel):
        template_name = "devcast/admin/diagram_targets_panel.html"

        def is_shown(self):
            return bool(self.instance and self.instance.pk and self.instance.cell_index)

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            index = self.instance.cell_index or []
            context["shapes"] = [c for c in index if c["kind"] == "shape"]
            context["edges"] = [c for c in index if c["kind"] == "edge"]
            context["unnamed"] = sum(1 for c in index if not c["label"])
            context["stats"] = self.instance.stats or {}
            context["aliases"] = (self.instance.script or {}).get("targets") or {}
            return context
