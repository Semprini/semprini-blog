"""Letting a diagram be dropped into a rich text body.

puput entries store their body as Draftail rich text, not a StreamField, so a
block cannot reach them. The mechanism that can is the same one images use:
``<embed embedtype="diagram" id="3"/>`` in the stored HTML, expanded to real
markup on the way out. See ``wagtail_hooks`` for the editor half.
"""

from django.template.loader import render_to_string
from draftjs_exporter.dom import DOM
from wagtail.admin.rich_text.converters.contentstate_models import Entity
from wagtail.admin.rich_text.converters.html_to_contentstate import (
    AtomicBlockEntityElementHandler,
)
from wagtail.rich_text import EmbedHandler

from .models import Diagram


class DiagramEmbedHandler(EmbedHandler):
    identifier = "diagram"

    @staticmethod
    def get_model():
        return Diagram

    @classmethod
    def expand_db_attributes(cls, attrs):
        try:
            diagram = cls.get_instance(attrs)
        except Diagram.DoesNotExist:
            # A deleted diagram must not take the article down with it.
            return ""
        return render_to_string("devcast/embeds/diagram.html", {"diagram": diagram})

    @classmethod
    def extract_references(cls, attrs):
        yield Diagram, str(attrs["id"]), "", ""


# --- editor <-> database conversion -----------------------------------------
# Only the id crosses the boundary. Everything else about a diagram lives on the
# snippet, so a hand-written embed in a body cannot smuggle anything in.


class DiagramElementHandler(AtomicBlockEntityElementHandler):
    """Stored HTML -> editor state."""

    def create_entity(self, name, attrs, state, contentstate):
        title = ""
        try:
            title = Diagram.objects.get(id=attrs["id"]).title
        except (Diagram.DoesNotExist, ValueError, KeyError):
            pass
        return Entity("DIAGRAM", "IMMUTABLE", {"id": attrs["id"], "title": title})


def diagram_entity(props):
    """Editor state -> stored HTML."""
    return DOM.create_element("embed", {"embedtype": "diagram", "id": props.get("id")})


ContentstateDiagramConversionRule = {
    "from_database_format": {
        'embed[embedtype="diagram"]': DiagramElementHandler(),
    },
    "to_database_format": {"entity_decorators": {"DIAGRAM": diagram_entity}},
}
