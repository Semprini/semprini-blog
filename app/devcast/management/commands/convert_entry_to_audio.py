"""Promote an existing blog entry to an audio entry, in place.

The page keeps its id, URL, comments, reactions and revision history: because
``AudioEntryPage`` is a multi-table subclass of the entry model, converting is
adding the child row and repointing the content type, not creating a new page.
"""

from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from devcast.conversion import blocks_from_richtext
from devcast.models import AudioEntryPage, PageBase


class Command(BaseCommand):
    help = "Convert an existing entry page into an AudioEntryPage."

    def add_arguments(self, parser):
        parser.add_argument("page_id", type=int)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--publish",
            action="store_true",
            help="Publish the converted page, which also queues narration.",
        )
        parser.add_argument(
            "--drop-body",
            action="store_true",
            help="Clear the original rich-text body. It is kept by default, because "
            "feeds, search and the blog listing still read from it.",
        )

    def handle(self, *args, **options):
        page_id = options["page_id"]
        if AudioEntryPage.objects.filter(pk=page_id).exists():
            raise CommandError(f"Page {page_id} is already an audio entry")

        entry = PageBase.objects.filter(pk=page_id).first()
        if entry is None:
            raise CommandError(f"No entry page with id {page_id}")

        blocks = blocks_from_richtext(entry.body)
        if not blocks:
            raise CommandError("The entry body produced no blocks")

        self.stdout.write(f"{entry.title} -> {len(blocks)} block(s)")
        for block_type, value in blocks:
            preview = value if isinstance(value, str) else value.get("caption", "")
            self.stdout.write(f"  {block_type}: {' '.join(str(preview).split())[:90]}")

        if options["dry_run"]:
            return

        with transaction.atomic():
            audio = AudioEntryPage(entrypage_ptr_id=entry.pk)
            # Copy the loaded parent-table values across so saving the subclass
            # rewrites them unchanged instead of blanking them.
            audio.__dict__.update(
                {key: value for key, value in entry.__dict__.items() if not key.startswith("_")}
            )
            # This row already exists in the parent tables, so validation must
            # compare against everything *except* itself; without this the
            # uniqueness checks report the page as a duplicate of itself.
            audio._state.adding = False
            audio._state.db = entry._state.db
            audio.content_type = ContentType.objects.get_for_model(AudioEntryPage)
            audio.sections = blocks
            audio.narration_enabled = True
            if options["drop_body"]:
                audio.body = ""
            audio.save()

            revision = audio.save_revision(changed=True)
            if options["publish"]:
                revision.publish()

        self.stdout.write(
            self.style.SUCCESS(
                f"Converted page {page_id}"
                + (" and published it" if options["publish"] else " (draft revision saved)")
            )
        )
