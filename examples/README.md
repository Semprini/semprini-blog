# Examples

Trials that inform features before they get built. One folder per example.

| Example | What it explores |
| --- | --- |
| [data-architecture/](data-architecture/) | Animating a draw.io SVG export with GSAP — camera pans and zooms, connectors that draw and flow. Validates [§6 of the devcast design](../docs/devcast-design.md#6-animated-diagrams). Start with its [FINDINGS.md](data-architecture/FINDINGS.md). |

## Adding another diagram example

1. Make a folder and drop the `.drawio` and its SVG export in it.
2. Copy `build_demo.py`, `diagram-demo.js` and `diagram-demo.css` across, and point the two
   filename constants at the top of `build_demo.py` at the new SVG. Everything else resolves
   relative to the script, so it runs from anywhere.
3. Rewrite the `ID` map and `STEPS` at the top of `diagram-demo.js`. The rest of that file is the
   generic engine — **when the second example lands, lift the engine out to `examples/engine/`
   rather than maintaining two copies.** It was left inline here because splitting it for a single
   example would have been speculative.
4. Build it:

   ```
   PYTHONPATH=<dir with lxml> .venv/bin/python examples/<folder>/build_demo.py
   ```

   `lxml` is not in the project venv — these are throwaway trials, so it is deliberately not a
   project dependency. `uv pip install --target <dir> lxml` is enough.

5. Open the generated `*.animated.html`. `?t=<seconds>` jumps straight to any moment, which is
   also how the screenshots in the findings were taken.
