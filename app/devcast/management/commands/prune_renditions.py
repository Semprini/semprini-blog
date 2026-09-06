"""Delete superseded narrations and their audio files."""

from django.core.management.base import BaseCommand

from devcast import conf
from devcast.models import Rendition
from devcast.narration import prune_page


class Command(BaseCommand):
    help = "Keep the current narration plus a configured number of previous ones."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-previous",
            type=int,
            default=None,
            help=f"Default: DEVCAST_KEEP_PREVIOUS_RENDITIONS ({conf.keep_previous_renditions()}).",
        )

    def handle(self, *args, **options):
        page_ids = (
            Rendition.objects.exclude(page_id=None)
            .values_list("page_id", flat=True)
            .distinct()
        )
        removed = sum(prune_page(pk, options["keep_previous"]) for pk in page_ids)
        self.stdout.write(self.style.SUCCESS(f"{removed} rendition(s) removed"))
