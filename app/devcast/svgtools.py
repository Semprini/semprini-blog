"""Turn an uploaded draw.io SVG into something safe to inline and possible to animate.

Three passes, run once when a ``Diagram`` is saved rather than at render time -
a sanitiser miss at render time is served straight to the reader.

Everything here is shaped by what draw.io actually exports, which was established
by the trial in ``examples/data-architecture`` (see its FINDINGS.md):

* ``data-cell-id`` on a ``<g>`` per cell, matching the ids in the .drawio model,
  so an animation script keyed on them survives the diagram being relabelled.
* Each connector is **two** paths in one cell: the line (``fill="none"``) and a
  separately filled arrowhead.
* Every label is a ``<switch>`` holding a ``<foreignObject>`` of real HTML *and*
  a base64 PNG of the same text. The PNGs are ~90% of the file and go raster
  under camera zoom, so they are dropped. The sanitiser therefore cannot simply
  drop ``<foreignObject>`` - that is where every label lives - it has to
  sanitise into the XHTML, which is why the allowlist covers HTML tags too.
* Half the cells carry no label at all - including every connector and every
  interface port - so ``index()`` synthesises names where it can.
"""

import base64
import re
import urllib.parse
import zlib

from lxml import etree

SVG_NS = "http://www.w3.org/2000/svg"
XHTML_NS = "http://www.w3.org/1999/xhtml"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Elements that may survive into a reader's DOM. Everything else is dropped whole.
ALLOWED = {
    "svg", "g", "defs", "style", "path", "rect", "ellipse", "circle", "line",
    "polygon", "polyline", "text", "tspan", "image", "switch", "foreignObject",
    "clipPath", "linearGradient", "radialGradient", "stop", "pattern", "marker",
    "use", "title", "desc",
    # the XHTML draw.io puts inside foreignObject: this is where labels live
    "div", "span", "br", "b", "i", "u", "em", "strong", "font", "p", "sub", "sup",
}
ON_ATTR = re.compile(r"^on", re.I)
URL_ATTRS = {"href", f"{{{XLINK_NS}}}href", "src"}
# Artwork pasted into a diagram arrives as a data: URI on an <image>. Refusing
# those silently deletes the picture - which is how five vendor logos went
# missing. Safe to keep: a browser renders anything referenced from <image> in
# secure static mode, so even an SVG payload gets no script and no network.
DATA_IMAGE = re.compile(r"^data:image/(png|jpe?g|gif|webp|svg\+xml)[;,]", re.I)
# any url() that is not a same-document #fragment, plus @import
CSS_DANGER = re.compile(r"@import|url\s*\(\s*['\"]?\s*(?!#)", re.I)
GEOMETRY = ("path", "rect", "ellipse", "circle", "polygon", "polyline", "line")

CAMERA_ATTR = "data-dgm-camera"
CELL_ATTR = "data-cell-id"


class DiagramError(ValueError):
    """The upload is not an SVG we can work with."""


def _local(tag):
    return etree.QName(tag).localname if isinstance(tag, str) and "}" in tag else tag


def parse(data):
    """Parse bytes into an SVG root, with entity expansion refused."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        root = etree.fromstring(data, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise DiagramError(f"not parseable as XML: {exc}") from exc
    if _local(root.tag) != "svg":
        raise DiagramError("the root element is not <svg>")
    return root


def sanitise(root):
    """Allowlist pass over the parsed tree. Returns (elements, attributes) dropped."""
    dropped = attrs = 0
    for el in list(root.iter()):
        if not isinstance(el.tag, str):              # comments, processing instructions
            el.getparent().remove(el)
            dropped += 1
            continue
        if _local(el.tag) not in ALLOWED:
            el.getparent().remove(el)
            dropped += 1
            continue
        if _local(el.tag) == "style" and el.text and CSS_DANGER.search(el.text):
            el.text = ""
            attrs += 1
        for name, value in list(el.attrib.items()):
            bad = bool(ON_ATTR.match(_local(name)))
            if not bad and name in URL_ATTRS:
                # same-document refs always; inline artwork only on <image>
                bad = not (
                    str(value).startswith("#")
                    or (_local(el.tag) == "image" and DATA_IMAGE.match(str(value)))
                )
            if not bad and _local(name) == "style" and CSS_DANGER.search(str(value)):
                bad = True
            if bad:
                del el.attrib[name]
                attrs += 1
    return dropped, attrs


def strip_raster_labels(root):
    """Drop draw.io's base64 PNG label fallbacks; keep the real text.

    draw.io emits ``<switch><foreignObject requiredFeatures=…>HTML</foreignObject>
    <image href="data:image/png;base64,…"/></switch>``. Browsers no longer
    evaluate ``requiredFeatures``, so which branch renders is not something to
    leave to chance when a camera is going to zoom into it."""
    images = 0
    for sw in root.iter(f"{{{SVG_NS}}}switch"):
        for child in list(sw):
            if _local(child.tag) == "image":
                sw.remove(child)
                images += 1
            elif _local(child.tag) == "foreignObject":
                child.attrib.pop("requiredFeatures", None)
    return images


def take_embedded_model(root):
    """Pull draw.io's "Include a copy of my diagram" payload off the root, and
    always remove it.

    It has to go. On the export this was written against it was 1.4 MB - 98% of
    the file - and it carries **every page of the author's .drawio**, not just
    the one exported. Shipping that to a reader is both a needless megabyte and
    a disclosure of diagrams that were never published."""
    content = root.get("content")
    if content is None:
        return None
    del root.attrib["content"]
    return content if content.lstrip().startswith("<mxfile") else None


def pin_colour_scheme(root):
    """draw.io ships ``color-scheme: light dark`` and light-dark() colours, so the
    diagram inverts with the reader's OS theme. A diagram's colours carry meaning;
    don't let the host page restyle them."""
    style = root.get("style", "")
    root.set("style", re.sub(r"color-scheme\s*:[^;]*;?", "", style).strip() + " color-scheme: light;")


def stamp_synthetic_ids(root):
    """Give an export with no ``data-cell-id`` something to target.

    Only older draw.io builds omit them (the same exports tend to embed the
    mxfile in a ``content`` attribute instead). Without ids the index comes back
    empty and nothing can be animated at all, so synthesise one per drawn group,
    in document order.

    These keys are weaker than real cell ids: they are positional, so editing
    the diagram and re-exporting renumbers everything after the edit and a
    script written against them silently shifts. ``ingest`` reports it in
    ``stats["synthetic_ids"]`` so the admin can say so. Re-exporting from a
    draw.io that emits ``data-cell-id`` is always the better answer."""
    if root.find(f".//*[@{CELL_ATTR}]") is not None:
        return 0
    n = 0
    for group in root.iter(f"{{{SVG_NS}}}g"):
        if group.get(CELL_ATTR):
            continue
        # A "cell" is the group that directly holds the drawn shapes, which is
        # the level draw.io would have tagged. Label groups count too: without
        # ids a shape and its label are separate siblings, so leaving labels out
        # makes them float visible over a panel that has not been revealed yet.
        if not any(
            _local(c.tag) in GEOMETRY + ("image", "switch", "text", "foreignObject")
            for c in group
        ):
            continue
        group.set(CELL_ATTR, f"auto-{n}")
        n += 1
    return n


def add_camera(root):
    """Wrap the drawing in the group the camera transforms."""
    if root.find(f".//{{{SVG_NS}}}g[@{CAMERA_ATTR}]") is not None:
        return
    cam = etree.SubElement(root, f"{{{SVG_NS}}}g")
    cam.set(CAMERA_ATTR, "")
    for child in list(root):
        if child is cam or _local(child.tag) in ("style", "defs"):
            continue
        root.remove(child)
        cam.append(child)


def _own_text(el):
    """Text belonging to this cell, not to cells nested inside it.

    Without this the root wrappers inherit every descendant's label and the
    editor's dropdown opens with three entries reading like the whole diagram."""
    nested = {
        d
        for c in el.iter()
        if c is not el and isinstance(c.tag, str) and c.get(CELL_ATTR)
        for d in c.iter()
    }
    parts = [
        t.strip()
        for e in el.iter()
        if e not in nested
        for t in (e.text, e.tail)
        if t and t.strip()
    ]
    seen, out = set(), []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return " ".join(out)[:120]


def index(root, model=None):
    """The targetable list an editor's picker is built from.

    ``model`` is the optional .drawio model from ``model_from_drawio``. It is
    worth having for two things the SVG cannot tell you: which cells are really
    connectors (the SVG only offers unreliable geometric hints), and which
    shapes each connector runs between, which is the only way to name it "A to
    B". Half a diagram's cells carry no label of their own.

    Some cells are nameable from nothing at all - draw.io's interface ports are
    unnamed ellipses in the model too - and come back with an empty label for
    the picker to fall back on position or a thumbnail."""
    model = model or {}
    edges = model.get("edges", {})
    values = model.get("labels", {})
    kinds = model.get("kinds", {})
    labels, order = {}, []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        cid = el.get(CELL_ATTR)
        if not cid:
            continue
        paths = el.findall(f".//{{{SVG_NS}}}path")
        lines = [p for p in paths if p.get("fill") == "none"]
        heads = [p for p in paths if p.get("fill") and p.get("fill") != "none"]
        if cid in kinds:
            is_edge = kinds[cid] == "edge"      # the model knows; trust it
        else:
            # draw.io marks a connector's line with pointer-events="stroke" and a
            # shape's fill with "all". Without the model that is the best signal:
            # a cylinder is also drawn from unfilled paths and would otherwise
            # be misread as a connector.
            is_edge = any(p.get("pointer-events") == "stroke" for p in lines)
        labels[cid] = {
            "key": cid,
            "kind": "edge" if is_edge else "shape",
            "label": values.get(cid) or _own_text(el),
            "head": bool(heads) if is_edge else False,
        }
        order.append(cid)

    for cid, entry in labels.items():
        if entry["label"]:
            continue
        src, dst = edges.get(cid, (None, None))
        names = [labels.get(x, {}).get("label") for x in (src, dst)]
        if all(names):
            entry["label"] = f"{names[0]} → {names[1]}"
        elif any(names):
            entry["label"] = next(n for n in names if n)
    return [labels[c] for c in order]


def model_from_drawio(data, page=None):
    """``{"edges": {...}, "labels": {...}, "kinds": {...}}`` for one .drawio page.

    Optional but worth uploading - see ``index``. An export made with "Include a
    copy of my diagram" carries the same model inside the SVG itself, which
    would remove the need for a second upload entirely."""
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise DiagramError(f"not parseable as a .drawio file: {exc}") from exc
    diagrams = root.findall(".//diagram") if _local(root.tag) == "mxfile" else [root]
    if page is not None:
        diagrams = [d for d in diagrams if d.get("name") == page] or diagrams[:1]
    diagrams = [_inflate(d) for d in diagrams]
    diagrams = [d for d in diagrams if d is not None]
    edges, labels, kinds = {}, {}, {}
    for diagram in diagrams[:1]:
        for cell in diagram.iter("mxCell"):
            parent = cell.getparent()
            wrapped = parent is not None and _local(parent.tag) == "object"
            cid = cell.get("id") or (parent.get("id") if wrapped else None)
            if not cid:
                continue
            value = cell.get("value") or (parent.get("label") if wrapped else "") or ""
            value = re.sub(r"<[^>]+>", " ", value)
            value = re.sub(r"\s+", " ", value).strip()
            if value:
                labels[cid] = value[:120]
            if cell.get("edge"):
                kinds[cid] = "edge"
                if cell.get("source") or cell.get("target"):
                    edges[cid] = (cell.get("source"), cell.get("target"))
            elif cell.get("vertex"):
                kinds[cid] = "shape"
    return {"edges": edges, "labels": labels, "kinds": kinds}


def _inflate(diagram):
    """A .drawio page is either plain XML or a deflated, base64'd, url-encoded
    blob. Exports that embed the model always use the compressed form."""
    if diagram.find(".//mxCell") is not None:
        return diagram
    payload = (diagram.text or "").strip()
    if not payload:
        return None
    try:
        raw = zlib.decompress(base64.b64decode(payload), -15).decode("utf8")
        return etree.fromstring(urllib.parse.unquote(raw).encode())
    except Exception:
        return None


def ingest(svg_bytes, drawio_bytes=None, page=None):
    """Full pass. Returns (markup, index, stats)."""
    root = parse(svg_bytes)
    embedded = take_embedded_model(root)
    rasters = strip_raster_labels(root)
    dropped, attrs = sanitise(root)
    pin_colour_scheme(root)
    synthetic = stamp_synthetic_ids(root)
    add_camera(root)
    # An uploaded .drawio wins; otherwise fall back to whatever the export
    # embedded, which is the same model and saves a second upload.
    source = drawio_bytes or (embedded.encode() if embedded else None)
    model = model_from_drawio(source, page) if source else None
    cells = index(root, model)
    markup = etree.tostring(root, encoding="unicode")
    stats = {
        "embedded_model_stripped": bool(embedded),
        "synthetic_ids": synthetic,
        "cells": len(cells),
        "edges": sum(1 for c in cells if c["kind"] == "edge"),
        "named": sum(1 for c in cells if c["label"]),
        "rasters_stripped": rasters,
        "elements_dropped": dropped,
        "attributes_dropped": attrs,
        "bytes": len(markup),
    }
    return markup, cells, stats
