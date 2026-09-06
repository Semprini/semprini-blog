"""Queue every audio entry for re-narration - after a voice change, say.

A voice switch is meant to be a deliberate, costed operation, so this reports
the character total and refuses to exceed the monthly budget silently.
"""

from django.core.management.base import BaseCommand, CommandError

from devcast import conf
from devcast.models import AudioEntryPage, Voice
from devcast.narration import build_script, month_char_usage, queue_render, script_chars
from devcast.speech import EngineError


class Command(BaseCommand):
    help = "Queue narration for every live audio entry."

    def add_arguments(self, parser):
        parser.add_argument("--voice", help="Voice key to render with.")
        parser.add_argument("--page", type=int, action="append", help="Limit to page id(s).")
        parser.add_argument("--force", action="store_true", help="Re-render ready narrations.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        voice = None
        if options["voice"]:
            voice = Voice.objects.filter(key=options["voice"]).first()
            if voice is None:
                raise CommandError(f"No voice with key {options['voice']!r}")

        pages = AudioEntryPage.objects.live().filter(narration_enabled=True)
        if options["page"]:
            pages = pages.filter(pk__in=options["page"])

        budget = conf.monthly_char_budget()
        total = 0
        queued = 0
        for page in pages:
            chars = script_chars(build_script(page))
            if not chars:
                continue
            total += chars
            self.stdout.write(f"{page.pk}: {page.title} ({chars} characters)")
            if options["dry_run"]:
                continue
            try:
                rendition = queue_render(page, voice=voice, force=options["force"])
            except EngineError as exc:
                self.stderr.write(f"  skipped: {exc}")
                continue
            if rendition is not None:
                queued += 1

        self.stdout.write(f"{total} characters across {pages.count()} page(s)")
        if budget:
            self.stdout.write(f"month usage so far: {month_char_usage()}/{budget}")
        if not options["dry_run"]:
            self.stdout.write(self.style.SUCCESS(f"{queued} narration(s) queued"))
