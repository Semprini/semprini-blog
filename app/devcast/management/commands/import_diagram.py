"""Create or update a Diagram from files on disk.

There is no editor for the animation script yet, so this is how one gets in:

    manage.py import_diagram examples/data-architecture/Data_Architecture-Concept.svg \
        --title "Data Architecture - Concept" \
        --model examples/data-architecture/Data_Architecture.drawio --page Concept \
        --script examples/data-architecture/script.json

Re-running against the same --title updates in place, so a re-export keeps its
script and any page already embedding it.
"""

import json
import os

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from ...models import Diagram
from ...svgtools import DiagramError


class Command(BaseCommand):
    help = "Create or update a Diagram from an SVG export."

    def add_arguments(self, parser):
        parser.add_argument("svg", help="The .svg exported from draw.io")
        parser.add_argument("--title", help="Defaults to the SVG's filename")
        parser.add_argument("--model", help="The .drawio source; names the connectors")
        parser.add_argument("--page", help="Which page of the .drawio the SVG came from")
        parser.add_argument("--script", help="JSON animation script")

    def handle(self, *args, **options):
        svg_path = options["svg"]
        if not os.path.exists(svg_path):
            raise CommandError(f"no such file: {svg_path}")
        title = options["title"] or os.path.splitext(os.path.basename(svg_path))[0]

        diagram = Diagram.objects.filter(title=title).first() or Diagram(title=title)
        with open(svg_path, "rb") as fh:
            diagram.source.save(os.path.basename(svg_path), File(fh), save=False)
        if options["model"]:
            with open(options["model"], "rb") as fh:
                diagram.model_source.save(os.path.basename(options["model"]), File(fh), save=False)
        if options["page"]:
            diagram.page = options["page"]
        if options["script"]:
            with open(options["script"], encoding="utf-8") as fh:
                diagram.script = json.load(fh)

        try:
            diagram.save()
        except DiagramError as exc:
            raise CommandError(f"{svg_path}: {exc}") from exc

        stats = diagram.stats
        self.stdout.write(
            self.style.SUCCESS(f"diagram {diagram.pk} {diagram.title!r}")
            + f"\n  cells    {stats.get('cells')} ({stats.get('edges')} connectors, "
            f"{stats.get('named')} named)"
            + f"\n  stripped {stats.get('rasters_stripped')} raster labels, "
            f"{stats.get('elements_dropped')} elements, {stats.get('attributes_dropped')} attributes"
            + f"\n  markup   {stats.get('bytes', 0) / 1024:.0f} KB"
            + f"\n  script   {len(diagram.steps)} steps, {diagram.duration}s"
        )
        missing = diagram.missing_targets()
        if missing:
            self.stdout.write(self.style.WARNING(f"  steps target missing cells: {missing}"))
        self.stdout.write(f"\nEmbed with: <embed embedtype=\"diagram\" id=\"{diagram.pk}\"/>")
