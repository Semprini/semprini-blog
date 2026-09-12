"""Turn a draw.io SVG export into the self-contained animated demo page.

    PYTHONPATH=<dir with lxml> .venv/bin/python examples/data-architecture/build_demo.py

This is the trial version of what `Diagram.save()` does in §6.3 of
docs/devcast-design.md — sanitise, index, stamp — reduced to what the prototype
needs, and run against a real export to find out what draw.io actually emits.

What the export turned out to contain, all of which this has to handle:

* `data-cell-id` on a `<g>` per shape and per connector. The §6.8 question is
  settled: the ids are there, they match the .drawio model, and they can key the
  animation script.
* Each connector is **two** paths in one cell - the line (`fill="none"`) and a
  separately filled arrowhead. Animating the cell as a whole swings the head
  about; they have to be driven separately.
* Every label is a `<switch>` holding a `<foreignObject>` of real HTML *and* a
  base64 PNG of the same text as the SVG 1.1 fallback. The PNGs are ~90% of the
  file and go raster the moment the camera zooms, so they are stripped and
  `requiredFeatures` is dropped so browsers take the crisp foreignObject.
  Note for the real sanitiser: it therefore cannot simply drop `<foreignObject>`,
  because that is where every label lives. It has to sanitise *into* the XHTML.

Sanitising here is an allowlist over a parsed tree, not regex over a string -
the output becomes live DOM in a logged-out reader's browser.
"""

import json
import os
import re
import sys

from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "Data_Architecture-Concept.svg")
OUT = os.path.join(HERE, "Data_Architecture-Concept.animated.html")
INDEX = os.path.join(HERE, "diagram-index.json")
GSAP = "https://cdnjs.cloudflare.com/ajax/libs/gsap/3.12.5/gsap.min.js"

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

# Elements that may survive into the page. Everything else is dropped whole.
ALLOWED = {
    "svg", "g", "defs", "style", "path", "rect", "ellipse", "circle", "line",
    "polygon", "polyline", "text", "tspan", "image", "switch", "foreignObject",
    "clipPath", "linearGradient", "radialGradient", "stop", "pattern", "marker",
    "use", "title", "desc",
    # the XHTML draw.io puts inside foreignObject - this is where labels live
    "div", "span", "br", "b", "i", "u", "em", "strong", "font", "p", "sub", "sup",
}
# Attributes are allowed by name; anything starting "on" is refused outright.
ATTR_DENY = re.compile(r"^on", re.I)
URL_ATTRS = {"href", f"{{{XLINK_NS}}}href", "src", "xlink:href"}
CSS_DANGER = re.compile(r"@import|url\s*\(\s*['\"]?\s*(?!#)", re.I)


def local(tag):
    return etree.QName(tag).localname if isinstance(tag, str) and "}" in tag else tag


def sanitise(root):
    """Allowlist pass. Returns (elements dropped, attributes dropped)."""
    dropped = attrs = 0
    for el in list(root.iter()):
        if not isinstance(el.tag, str):          # comments, PIs
            el.getparent().remove(el)
            dropped += 1
            continue
        if local(el.tag) not in ALLOWED:
            el.getparent().remove(el)
            dropped += 1
            continue
        if local(el.tag) == "style" and el.text and CSS_DANGER.search(el.text):
            el.text = ""
            attrs += 1
        for name, value in list(el.attrib.items()):
            bad = ATTR_DENY.match(local(name))
            if not bad and name in URL_ATTRS:
                # only same-document references survive; no network, no javascript:
                bad = not str(value).startswith("#")
            if not bad and local(name) == "style" and CSS_DANGER.search(str(value)):
                bad = True
            if bad:
                del el.attrib[name]
                attrs += 1
    return dropped, attrs


def strip_raster_labels(root):
    """Drop the base64 PNG fallbacks and let browsers use the real text.

    draw.io emits `<switch><foreignObject requiredFeatures=…>HTML</foreignObject>
    <image href="data:image/png;base64,…"/></switch>`. Browsers no longer
    evaluate `requiredFeatures`, so which branch renders is not something to
    leave to chance when the camera is going to zoom into it."""
    images = fo = 0
    for sw in root.iter(f"{{{SVG_NS}}}switch"):
        for child in list(sw):
            if local(child.tag) == "image":
                sw.remove(child)
                images += 1
            elif local(child.tag) == "foreignObject" and "requiredFeatures" in child.attrib:
                del child.attrib["requiredFeatures"]
                fo += 1
    return images, fo


def add_camera(root):
    """Wrap the drawing in the group the camera transforms (§6.6)."""
    cam = etree.SubElement(root, f"{{{SVG_NS}}}g")
    cam.set("data-dgm-camera", "")
    for child in list(root):
        if child is cam or local(child.tag) in ("style", "defs"):
            continue
        root.remove(child)
        cam.append(child)
    return cam


def index_cells(root):
    """The targetable list an editor's dropdown would be filled from (§6.3)."""
    out = []
    for el in root.iter():
        cid = el.get("data-cell-id") if isinstance(el.tag, str) else None
        if not cid:
            continue
        paths = el.findall(f"./{{{SVG_NS}}}g/{{{SVG_NS}}}path") or el.findall(f".//{{{SVG_NS}}}path")
        lines = [p for p in paths if p.get("fill") == "none"]
        heads = [p for p in paths if p.get("fill") and p.get("fill") != "none"]
        label = " ".join(t.strip() for t in el.itertext() if t and t.strip())[:70]
        kind = "edge" if len(lines) == 1 and len(heads) <= 1 and not el.findall(f".//{{{SVG_NS}}}rect") else "shape"
        out.append({"key": cid, "kind": kind, "label": label})
    return out


def main():
    src = SRC
    tree = etree.parse(src)
    root = tree.getroot()
    before = os.path.getsize(src)

    # draw.io ships `color-scheme: light dark` plus light-dark() colours, so the
    # diagram flips with the viewer's OS theme. Pin it: a diagram's colours carry
    # meaning here, and the host page's theme should not restyle them.
    style = root.get("style", "")
    root.set("style", re.sub(r"color-scheme\s*:[^;]*;?", "", style) + " color-scheme: light;")

    images, fo = strip_raster_labels(root)
    dropped, attrs = sanitise(root)
    add_camera(root)
    index = index_cells(root)

    svg = etree.tostring(root, encoding="unicode")
    here = os.path.dirname(src)
    css = open(os.path.join(here, "diagram-demo.css"), encoding="utf-8").read()
    js = open(os.path.join(here, "diagram-demo.js"), encoding="utf-8").read()

    steps = re.findall(r"\{\s*at:\s*([0-9.]+)", js)
    chips = "\n".join(
        f'      <button data-step="{s}">{i}. {float(s):.0f}s</button>'
        for i, s in enumerate(steps)
    )

    html = f"""<!doctype html>
<meta charset="utf-8">
<title>Data Architecture — animated</title>
<style>
{css}
</style>
<div class="wrap">
  <h1>Source &rarr; on-ramp &rarr; domain data product &rarr; analytics</h1>
  <p class="sub">Prototype of the <code>&sect;6</code> diagram engine, driven straight from a
     draw.io export. <strong>Drag the scrubber</strong> &mdash; the picture is a pure function of
     the playhead, which is the property the narration driver depends on.</p>

  <figure class="dgm">
{svg}
    <figcaption class="dgm-caption"></figcaption>
  </figure>

  <div class="bar">
    <button class="primary" data-play>Play</button>
    <input type="range" data-seek min="0" max="1000" value="0" aria-label="Scrub">
    <span class="t" data-clock>0.0s</span>
  </div>

  <div class="steps">
{chips}
  </div>

  <p class="note"><strong>What this is testing.</strong> Every effect is built into one paused
     GSAP timeline whose playhead is driven from outside, so seeking anywhere renders the right
     state. Connector "flow" is deliberately <em>not</em> a timeline tween &mdash; an infinite
     repeat has infinite duration and would make the timeline unseekable &mdash; so it is derived
     from the playhead instead. Camera steps name shapes, never coordinates.</p>
</div>
<script src="{GSAP}"></script>
<script>
{js}
</script>
"""
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html)

    labelled = sum(1 for c in index if c["label"])
    edges = sum(1 for c in index if c["kind"] == "edge")
    print(f"source          {before / 1024:8.0f} KB")
    print(f"raster labels   {images:8d} stripped ({fo} requiredFeatures dropped)")
    print(f"sanitiser       {dropped:8d} elements, {attrs} attributes removed")
    print(f"index           {len(index):8d} cells ({edges} edges, {labelled} labelled)")
    print(f"output          {os.path.getsize(OUT) / 1024:8.0f} KB  {os.path.relpath(OUT)}")
    with open(INDEX, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=1)


if __name__ == "__main__":
    sys.exit(main())
