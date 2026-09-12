"""Build the looping platform animation for Data_Architecture-Platform.svg.

    PYTHONPATH=<lxml dir>:app .venv/bin/python examples/data-architecture/gen_platform.py

The animation: connectors in the Digital Core hexagon flow continuously, then
Option A is revealed, then Option B, then it loops.

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

if not (option_a and option_b and core):
    raise SystemExit(
        "expected dc25-a-*/dc25-b-* panels and core connectors; "
        f"found {len(option_a)}/{len(option_b)}/{len(core)}. Has the diagram been re-exported?"
    )

script = {
    "loop": True,
    "duration": 14,
    "steps": [
        {"at": 0.0, "flow": [[k, {"speed": 55, "dash": "10 18"}] for k in core]},
        {"at": 3.5, "appear": option_a},
        {"at": 7.5, "appear": option_b},
    ],
}
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(script, fh, indent=1)

print(f"cells {stats['cells']} | core connectors {len(core)} | "
      f"Option A {len(option_a)} | Option B {len(option_b)}")
print("wrote", os.path.relpath(OUT))
