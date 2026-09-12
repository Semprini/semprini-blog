# Animating a draw.io export — findings for the editor UI

What building one real animated diagram taught us about the admin interface that has to
produce them. Companion to [§6 of the devcast design](../../docs/devcast-design.md#6-animated-diagrams),
which this trial was run to validate.

**Subject:** `Data_Architecture-Concept.svg`, a 71-cell enterprise data architecture exported
from draw.io 21.2.8. **Result:** `Data_Architecture-Concept.animated.html` — a 15-step animated
walkthrough of source → on-ramp → domain data product → analytics, and back out through the
off-ramp. Open it in a browser; `?t=<seconds>` jumps to any moment.

---

## 1. The headline problem for the UI

> **19 of the 42 things the script animates have no label anywhere in the SVG.**

That includes *every connector*, *every interface port*, and *all four data-product hexagons* —
which is to say, nearly everything you would actually want to animate on a flow diagram. Across
the whole export:

| | count |
| --- | --- |
| cells with their own label | 32 |
| cells with no text at all | 36 |
| cells inheriting only their children's text | 3 |

A target picker built from the SVG's own text would offer the editor a list of boxes and no way
to say "draw *this arrow*". The naming problem is the UI problem.

**What fixes it:** the `.drawio` model carries `source` and `target` on every edge, so
`fOdsYAS7zbKB1CYuf22Q-4` can be presented as **"Source System → on-ramp"**. The SVG does not
carry that — the relationship is only recoverable by geometry, badly. Two ways to get it:

1. Ask editors to tick **"Include a copy of my diagram"** when exporting SVG, which embeds the
   mxfile in a `content` attribute on the root `<svg>`. *This export does not have it* — so if we
   depend on it, the upload form has to check for it and refuse with an explanation, not fail
   silently later.
2. Accept the `.drawio` upload alongside (or instead of) the SVG.

Either way the index gets built from the model and the picker gets human labels. **This decision
gates the whole UI** — until targets can be named, there is nothing to put in a dropdown.

## 2. What the export actually contains

Settling [§6.8](../../docs/devcast-design.md#68-open-question-what-drawio-actually-exports), plus
four things that were not anticipated:

| Finding | Consequence for ingest / UI |
| --- | --- |
| `data-cell-id` **is** emitted on a `<g>` per cell, and matches the `.drawio` ids | Scripts key off ids, so they survive relabelling. §6.8 answered. |
| Each connector is **two paths**: the line (`fill="none"`) and a separately filled arrowhead | Confirms the §6.5 gotcha. "Draw a connector" is two tweens, and the UI must present it as one choice. |
| Labels are `<foreignObject>` **plus a base64 PNG of the same text** | The PNGs are **90% of the file** (688 KB → 70 KB once stripped) and go raster under camera zoom. The sanitiser therefore **cannot** just drop `<foreignObject>` — every label lives inside it — it has to sanitise *into* the XHTML. |
| `getBBox()` on any labelled cell returns **the whole viewport** | Because draw.io's foreignObject is `width="100%" height="100%"`. This silently zoomed every camera step back out to "fit". Camera framing must measure drawn geometry only, never the group. |
| Exports carry `color-scheme: light dark` and `light-dark()` colours | The diagram inverts with the viewer's OS theme unless pinned. Probably an ingest option — "follow the site theme" vs "keep the diagram's own colours". |

## 3. The step vocabulary that emerged

Writing the script by hand, five kinds of step turned out to be enough for a full narrative:

| Field | Used | What the editor is actually saying |
| --- | --- | --- |
| `camera` | 15 | "look here" |
| `draw` | 7 | "this link exists" |
| `flow` | 7 | "and it's carrying data" |
| `sequence` | 4 | "walk through what's inside this" |
| `pulse` | 6 | "notice this" |

**15 authored steps expanded to ~78 tweens.** Almost all the leverage came from one field:
`sequence` turned 4 entries into 18 element reveals (36 tweens). A UI that made the editor add a
step per element would have needed ~50 steps for the same result and would not have been used
twice. **`sequence` — an ordered multi-select that staggers automatically — is the single
highest-value control on the form.**

## 4. Implications, field by field

### Target picker
- Multi-select, not single. Camera steps named 2 shapes seven times, 3 shapes twice, 1 shape four
  times. `sequence` needs 4–6, **in order** (drag to reorder).
- Group the list by kind — shapes, connectors, interface ports — because the editor is thinking
  "which arrow", not "which cell".
- Show a swatch or thumbnail. 36 unlabelled cells cannot be told apart by name even once the
  edges are synthesised.

### Camera
- **Padding cannot have a single default.** I used eight different values (55, 60, 70, 80, 90,
  140, 150, 200) across 13 camera steps, tuned by eye each time. Either offer *tight / normal /
  wide* presets that compute from the target's size, or accept that padding is a slider the
  editor will move while watching.
- Keep `fit` as an explicit named target — it was used twice, to open and to close.
- Never expose coordinates or zoom factors. Every camera step in the trial named shapes, and the
  framing survived a browser resize because of it.

### Flow direction and style
Two things the trial proved need to be editor-visible:

- **Arrow direction ≠ data direction.** The off-ramp's subscribe arrow points *at* the Subscribe
  Interface — that is the subscribe/call direction — but the data travels back the other way.
  The form needs *"flows with the arrow / against the arrow"*, and it will be got wrong if it
  defaults silently.
- **Continuous data vs a request.** I gave the API lookups a thin, fast, sparse dash and the data
  paths a chunky slow one. That difference carries meaning and should be a **named style**
  ("data flow" / "request") rather than dash-pattern and speed number fields.

### Timing
I hand-tuned 15 `at` values by watching playback. In production those become narration phrase
anchors ([§6.2](../../docs/devcast-design.md#62-editors-never-type-a-number-or-an-id)), so the
editor never sees them. But note what stayed hidden even here: draw takes 1.4s, the arrowhead
fades at +1.15s, sequence staggers at 0.85s, camera moves take 1.7s. **These are engine
constants, not fields.** Exposing them would multiply the form's size for no gain.

### Validation the form must do
- **Steps targeting cells that no longer exist** after a re-export. The engine collects these and
  warns rather than dying; the admin must surface them on the snippet *and* on every page using
  it, or a re-export silently guts a script.
- **Draw before flow** on the same connector. They fight over the same dash properties otherwise.
- A `sequence` on a container should probably offer "all children of this shape" as a shortcut.

## 5. Preview is not optional

Every single thing that was wrong the first time was found by looking, not by reasoning: the
camera framing bug, the padding values, the flow direction on the subscribe arrow, the pacing of
the sequences, the caption spacing. None of it was visible in the step list.

An editor cannot hold "camera framing the on-ramp and the publish interface with 70px padding" in
their head. **The form needs a live preview with a scrubber next to it** — and because the whole
design already guarantees that state is a pure function of the playhead, that preview is the same
engine the front end runs, with the range input wired to the same `render(t)`. It is close to
free, and the UI is not usable without it.

## 6. What held up

The core bet from [§6.1](../../docs/devcast-design.md#61-the-timeline-is-seekable-not-triggered) —
one paused timeline whose playhead is driven — held. Nine checks were taken as **cold page loads
seeking straight to a given time**, which is a harder test than scrubbing because there is no
accumulated animation state at all. Each rendered correctly.

Two things were needed to get there, both worth keeping in `diagram.js`:

- **Flow is derived from the playhead, not tweened.** An infinitely repeating tween has infinite
  duration and would make the timeline unseekable — the exact property being protected. Flow
  overlays are cloned paths whose `stroke-dashoffset` is computed from `t`.
- **A failed engine leaves the diagram in its final state** and surfaces the reason. The SVG ships
  fully drawn and JS sets the "from" states, so a thrown error degrades to a static diagram
  rather than a blank box. This caught two real bugs during the trial.

## 7. Open questions

1. **Where does the model come from** — embedded mxfile, or a second upload? (§1 above; blocks
   the target picker.)
2. **Is a diagram reusable across pages** with a different script each time, or does the script
   belong to the diagram? Reuse argues for the script living on the block, which is what §6.4
   assumes, but then the same diagram animated three ways has three unrelated scripts.
3. **What happens to a script when the diagram is re-exported** and a targeted shape is gone —
   warn and keep, or drop the step? Currently: warn and keep.
4. **Should `sequence` read the diagram's own structure** — "walk the children of this container"
   — rather than an explicit ordered list? Cheaper to author, less controllable.
5. **Theme.** Do we pin the diagram's colours, or let draw.io's `light-dark()` follow the site?

## 8. Files

| | |
| --- | --- |
| `Data_Architecture.drawio` | source, 24 pages; the "Concept" page is the one used |
| `Data_Architecture-Concept.svg` | the export, as it came out of draw.io |
| `build_demo.py` | ingest: sanitise → strip raster labels → wrap camera group → index → emit page. Needs `lxml`. |
| `diagram-demo.js` | the engine (destined to become `diagram.js`) **and** this diagram's `ID` map and `STEPS` — split these when a second example arrives |
| `diagram-demo.css` | prototype styling |
| `diagram-index.json` | the extracted index — what would fill the editor's dropdown, label bug and all |
| `Data_Architecture-Concept.animated.html` | built output; open this |
