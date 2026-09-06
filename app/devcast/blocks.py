"""The content vocabulary shared by every devcast page type.

Blocks carry their own narration contract: ``narration_text()`` returns the
plain text a speech engine should read for a block, or an empty string to skip
it. Doing it here means the audio pipeline never has to reverse-engineer
rendered markup, and a new block type cannot silently break narration.
"""

import html as html_lib
import re

import markdown
from django.utils.html import strip_tags
from wagtail import blocks
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.embeds.blocks import EmbedBlock
from wagtail.images.blocks import ImageChooserBlock
from wagtailmarkdown.blocks import MarkdownBlock

_WHITESPACE = re.compile(r"\s+")
_PREFORMATTED = re.compile(r"<pre\b.*?</pre>", re.DOTALL | re.IGNORECASE)
# Markdown link *targets* never survive to here - stripping the <a> tag leaves
# only the link text. What does survive is a URL an author wrote as the visible
# text, via an autolink or a pasted address.
_BARE_URL = re.compile(r"(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
_URL_TAIL = re.compile(r"[.,;:!?)\]]+$")


def _speakable_url(match):
    """A path read character by character is unlistenable, so only the host
    survives, with its dots said out loud."""
    url = match.group(0)
    # Sentence punctuation gets swept up by the URL match; it belongs to the
    # sentence, not the address.
    tail = _URL_TAIL.search(url)
    tail = tail.group(0) if tail else ""
    host = url[: len(url) - len(tail)].split("//")[-1].split("/")[0].split("?")[0]
    return host.removeprefix("www.").replace(".", " dot ") + tail


def to_speech(value):
    """Collapse arbitrary markup down to a single speakable line."""
    text = html_lib.unescape(strip_tags(str(value or "")))
    text = _BARE_URL.sub(_speakable_url, text)
    return _WHITESPACE.sub(" ", text).strip()


class NarratableBlock(blocks.StructBlock):
    """Struct blocks that may contribute a line to the narration script."""

    def narration_text(self, value):
        return to_speech(value.get("narration"))


class HeadingBlock(NarratableBlock):
    text = blocks.CharBlock(max_length=120)
    level = blocks.ChoiceBlock(
        choices=[("h2", "Section"), ("h3", "Sub-section"), ("h4", "Minor")],
        default="h2",
    )

    def narration_text(self, value):
        return to_speech(value.get("text"))

    class Meta:
        icon = "title"
        template = "devcast/blocks/heading.html"
        label = "Heading"


class ProseBlock(MarkdownBlock):
    """Markdown body text - the authoring path puput already established."""

    def narration_text(self, value):
        rendered = markdown.markdown(str(value or ""), extensions=["extra"])
        return to_speech(_PREFORMATTED.sub(" ", rendered))

    class Meta:
        icon = "pilcrow"
        label = "Text"


class ImageBlock(NarratableBlock):
    image = ImageChooserBlock()
    caption = blocks.CharBlock(required=False, max_length=250)
    narration = blocks.TextBlock(
        required=False,
        help_text="Spoken instead of the caption. Leave empty to skip this image in narration.",
    )

    def narration_text(self, value):
        return to_speech(value.get("narration") or value.get("caption"))

    class Meta:
        icon = "image"
        template = "devcast/blocks/image.html"
        label = "Image"


class GalleryBlock(NarratableBlock):
    images = blocks.ListBlock(ImageChooserBlock())
    caption = blocks.CharBlock(required=False, max_length=250)
    narration = blocks.TextBlock(required=False)

    class Meta:
        icon = "copy"
        template = "devcast/blocks/gallery.html"
        label = "Gallery"


class VideoBlock(NarratableBlock):
    embed = EmbedBlock()
    caption = blocks.CharBlock(required=False, max_length=250)
    narration = blocks.TextBlock(
        required=False,
        help_text="Spoken lead-in. The video's own audio is never part of the narration.",
    )

    class Meta:
        icon = "media"
        template = "devcast/blocks/video.html"
        label = "Video"


class CodeBlock(NarratableBlock):
    language = blocks.CharBlock(required=False, max_length=30, default="text")
    code = blocks.TextBlock()
    narration = blocks.TextBlock(
        required=False,
        help_text="Describe what the code does. The code itself is never read aloud.",
    )

    class Meta:
        icon = "code"
        template = "devcast/blocks/code.html"
        label = "Code"


class Model3DBlock(NarratableBlock):
    model = DocumentChooserBlock(help_text="A .glb file.")
    caption = blocks.CharBlock(required=False, max_length=250)
    autorotate = blocks.BooleanBlock(required=False, default=True)
    narration = blocks.TextBlock(required=False)

    class Meta:
        icon = "cogs"
        template = "devcast/blocks/model3d.html"
        label = "3D model"


class CalloutBlock(NarratableBlock):
    style = blocks.ChoiceBlock(
        choices=[("note", "Note"), ("warning", "Warning"), ("tip", "Tip")],
        default="note",
    )
    text = blocks.TextBlock()

    def narration_text(self, value):
        return to_speech(f"{value.get('style')}: {value.get('text')}")

    class Meta:
        icon = "help"
        template = "devcast/blocks/callout.html"
        label = "Callout"


class QuoteBlock(NarratableBlock):
    quote = blocks.TextBlock()
    attribution = blocks.CharBlock(required=False, max_length=120)

    def narration_text(self, value):
        spoken = to_speech(value.get("quote"))
        if value.get("attribution"):
            spoken = f"{spoken} - {to_speech(value['attribution'])}"
        return spoken

    class Meta:
        icon = "openquote"
        template = "devcast/blocks/quote.html"
        label = "Quote"


class NarrationAsideBlock(NarratableBlock):
    """Spoken but not shown - lets narration bridge two visual blocks."""

    narration = blocks.TextBlock()

    class Meta:
        icon = "comment"
        template = "devcast/blocks/aside.html"
        label = "Narration aside"


def _block_types():
    return [
        ("heading", HeadingBlock()),
        ("text", ProseBlock()),
        ("image", ImageBlock()),
        ("gallery", GalleryBlock()),
        ("video", VideoBlock()),
        ("code", CodeBlock()),
        ("model3d", Model3DBlock()),
        ("callout", CalloutBlock()),
        ("quote", QuoteBlock()),
    ]


SHOWCASE_BLOCKS = _block_types()
NARRATABLE_BLOCKS = _block_types() + [("aside", NarrationAsideBlock())]
