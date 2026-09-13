"""Build the looping platform animation for Data_Architecture-Platform.svg.

    PYTHONPATH=<lxml dir>:app .venv/bin/python examples/data-architecture/gen_platform.py

The animation: the camera opens on the Digital Core concept with its connectors
flowing, follows down to Option A as it is revealed, across to Option B as that
is revealed, then pulls back and holds on the whole diagram before it loops.

Targets come from the export's own cell ids, which this diagram names usefully
(`dc25-a-*` for Option A, `dc25-b-*` for Option B). That is worth having: an
earlier export of the same diagram carried no ids at all, so the script had to
be generated from geometry and keyed on positional `auto-N` names that would
shift on the next edit.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "app"))
from devcast import svgtools  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "Data_Architecture-Platform.svg")
OUT = os.path.join(HERE, "script-platform.json")

markup, cells, stats = svgtools.ingest(open(SVG, "rb").read())
by_key = {c["key"]: c for c in cells}

option_a = sorted(k for k in by_key if k.startswith("dc25-a-"))
# The rule between the panels belongs with B: a divider shown while only one
# option exists reads as a stray line.
option_b = sorted(
    k for k in by_key
    if k.startswith("dc25-b-") or (k.startswith("dc25-") and not k.startswith("dc25-a-"))
)
# the core's connectors: edges that are not part of either option panel
core = sorted(
    k for k, c in by_key.items()
    if c["kind"] == "edge" and not k.startswith("dc25-")
)
# What the camera frames for the concept. Shapes only: draw.io's root cells "0"
# and "1" index as edges and span the whole drawing, so framing the core's edges
# would never zoom in at all.
concept = sorted(
    k for k, c in by_key.items()
    if c["kind"] == "shape" and not k.startswith("dc25-")
)

if not (option_a and option_b and core and concept):
    raise SystemExit(
        "expected dc25-a-*/dc25-b-* panels and core shapes and connectors; "
        f"found {len(option_a)}/{len(option_b)}/{len(concept)}/{len(core)}. "
        "Has the diagram been re-exported?"
    )

# Each reveal starts a second after its camera move does (diagram.js moves take
# 1.7s), so the panel is seen arriving rather than already there or off-screen.
script = {
    "loop": True,
    "duration": 19,
    "steps": [
        {
            "at": 0.0,
            "camera": concept,
            "padding": 40,
            "flow": [[k, {"speed": 55, "dash": "10 18"}] for k in core],
        },
        {"at": 3.5, "camera": option_a, "padding": 30},
        {"at": 4.5, "appear": option_a},
        {"at": 8.5, "camera": option_b, "padding": 30},
        {"at": 9.5, "appear": option_b},
        # pull back, then hold on the whole diagram until the loop comes round
        {"at": 13.5, "camera": "fit"},
    ],
}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(script, fh, indent=1)

print(f"cells {stats['cells']} | core connectors {len(core)} | concept shapes {len(concept)} | "
      f"Option A {len(option_a)} | Option B {len(option_b)}")
print("wrote", os.path.relpath(OUT))
