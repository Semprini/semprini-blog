import datetime

from django.test import TestCase
from puput.models import BlogPage
from wagtail.models import Page

from .blocks import CodeBlock, ProseBlock
from .models import AudioCue, AudioEntryPage, ChangelogEntry, DevProjectPage


class ProjectPlacementTests(TestCase):
    """The puput graft is the fragile part: Wagtail matches subpage_types by
    exact class and caches the result, so a subclass is only allowed under a
    blog because integrations.puput patched the list at startup."""

    def setUp(self):
        root = Page.objects.get(depth=1)
        self.blog = BlogPage(title="Blog", slug="blog")
        root.add_child(instance=self.blog)

    def test_project_page_allowed_under_blog(self):
        self.assertIn(DevProjectPage, BlogPage.allowed_subpage_models())

    def test_project_page_appears_in_blog_entries(self):
        project = DevProjectPage(
            title="Avatar rig", slug="avatar-rig", body="<p>about</p>"
        )
        self.blog.add_child(instance=project)
        project.save_revision().publish()
        self.assertIn(project.page_ptr_id, self.blog.get_entries().values_list("id", flat=True))


class ChangelogGroupingTests(TestCase):
    def setUp(self):
        root = Page.objects.get(depth=1)
        blog = BlogPage(title="Blog", slug="blog")
        root.add_child(instance=blog)
        self.project = DevProjectPage(title="Thing", slug="thing", body="<p>x</p>")
        blog.add_child(instance=self.project)

    def _add(self, version, day, kind="changed"):
        self.project.changelog.add(
            ChangelogEntry(
                version=version,
                released_on=datetime.date(2025, 1, day),
                kind=kind,
                summary=f"{version} {kind}",
            )
        )

    def test_entries_group_by_release_newest_first(self):
        self._add("0.1.0", 1)
        self._add("0.2.0", 5, "added")
        self._add("0.2.0", 5, "fixed")

        groups = self.project.changelog_groups

        self.assertEqual([g["version"] for g in groups], ["0.2.0", "0.1.0"])
        self.assertEqual(len(groups[0]["entries"]), 2)
        self.assertEqual(
            sorted(c["kind"] for c in groups[0]["counts"]), ["added", "fixed"]
        )


class NarrationContractTests(TestCase):
    def test_code_is_never_read_aloud(self):
        block = CodeBlock()
        value = block.to_python(
            {"language": "python", "code": "secret = 1", "narration": "sets a flag"}
        )
        self.assertEqual(block.narration_text(value), "sets a flag")

    def test_prose_drops_code_but_keeps_sentences(self):
        block = ProseBlock()
        spoken = block.narration_text("Some **markdown**.\n\n    print('code')")
        self.assertEqual(spoken, "Some markdown.")


class CueTrackTests(TestCase):
    def setUp(self):
        root = Page.objects.get(depth=1)
        blog = BlogPage(title="Blog", slug="blog")
        root.add_child(instance=blog)
        self.page = AudioEntryPage(
            title="Listen",
            slug="listen",
            sections=[
                {"type": "heading", "value": {"text": "One", "level": "h2"}},
                {"type": "text", "value": "First part."},
                {"type": "text", "value": "Second part."},
            ],
            audio_duration=90.0,
        )
        blog.add_child(instance=self.page)

    def _cue(self, start):
        self.page.cues.add(AudioCue(start=start))

    def test_no_track_without_audio(self):
        self._cue(0)
        self.assertIsNone(self.page.cue_track)

    def test_cues_bind_to_blocks_in_order_and_chain_ends(self):
        self.page.manual_audio = _document()
        for start in (0, 12.5, 40):
            self._cue(start)

        track = self.page.cue_track
        block_ids = [str(b.id) for b in self.page.sections]

        self.assertEqual([c["id"] for c in track["cues"]], block_ids)
        self.assertEqual([c["start"] for c in track["cues"]], [0, 12.5, 40])
        # each cue ends where the next begins; the last runs to the audio length
        self.assertEqual([c["end"] for c in track["cues"]], [12.5, 40, 90.0])

    def test_extra_cues_beyond_the_sections_are_ignored(self):
        self.page.manual_audio = _document()
        for start in (0, 10, 20, 30, 40):
            self._cue(start)

        self.assertEqual(len(self.page.cue_track["cues"]), 3)

    def test_narration_enabled_off_suppresses_the_player(self):
        self.page.manual_audio = _document()
        self._cue(0)
        self.page.narration_enabled = False
        self.assertIsNone(self.page.cue_track)

    def test_script_skips_blocks_with_nothing_to_say(self):
        self.page.sections = [
            {"type": "heading", "value": {"text": "Intro", "level": "h2"}},
            {"type": "image", "value": {"image": None, "caption": "", "narration": ""}},
        ]
        kinds = [kind for _, kind, _ in self.page.narration_script()]
        self.assertEqual(kinds, ["heading"])


def _document():
    from django.core.files.base import ContentFile
    from wagtail.documents import get_document_model

    doc = get_document_model()(title="narration")
    doc.file.save("narration.mp3", ContentFile(b"not really audio"), save=True)
    return doc
