"""Turning an existing rich-text entry into narratable sections.

Wagtail rich text is one opaque HTML blob; the audio pipeline needs addressable
blocks, because the block id is what binds spoken audio to a paragraph on the
page. This walks the stored HTML and splits it back into blocks, keeping images
as image blocks and everything else as markdown - the authoring path the rest of
devcast already uses.
"""

import re

from bs4 import BeautifulSoup
from markdownify import markdownify
from wagtail.images import get_image_model
from wagtail.rich_text import expand_db_html

_BLANK_LINES = re.compile(r"\n{3,}")


def _to_markdown(fragment):
    """Rich-text HTML -> markdown, with Wagtail's internal link and embed
    references resolved to real URLs first."""
    text = markdownify(expand_db_html(fragment), heading_style="ATX", bullets="-")
    return _BLANK_LINES.sub("\n\n", text).strip()


def blocks_from_richtext(html):
    """``[(block_type, value)]`` ready to assign to a StreamField.

    ``<hr>`` and image embeds are treated as boundaries, so the prose between
    them becomes one addressable - and therefore separately narratable - block.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    image_model = get_image_model()

    blocks = []
    buffer = []

    def flush():
        if not buffer:
            return
        markdown = _to_markdown("".join(buffer))
        buffer.clear()
        if markdown:
            blocks.append(("text", markdown))

    for node in soup.children:
        name = getattr(node, "name", None)

        if name == "embed" and node.get("embedtype") == "image":
            flush()
            image = image_model.objects.filter(pk=node.get("id")).first()
            if image is None:
                continue
            blocks.append(
                (
                    "image",
                    {
                        "image": image,
                        # The alt text was the only description this image ever
                        # had, so it becomes both the caption and what is read.
                        "caption": (node.get("alt") or "").strip(),
                        "narration": "",
                    },
                )
            )
            continue

        if name == "hr":
            flush()
            continue

        buffer.append(str(node))

    flush()
    return blocks
