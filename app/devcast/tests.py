import base64
import datetime
from io import BytesIO
from unittest import mock

from django.core.files.base import ContentFile
from django.core.files.images import ImageFile
from django.test import TestCase, override_settings
from django.utils import timezone
from puput.models import BlogPage
from wagtail.images.models import Image
from wagtail.models import Page, Site

from . import narration
from .blocks import CodeBlock, ProseBlock
from .conversion import blocks_from_richtext
from .models import (
    AudioCue,
    AudioEntryPage,
    ChangelogEntry,
    DevProjectPage,
    JobState,
    RenderJob,
    Rendition,
    RenditionStatus,
    Voice,
)
from .speech import Clip, EngineError, Segment, segmenter
from .speech.elevenlabs import words_from_alignment


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

    def test_a_link_is_read_as_its_text_never_its_url(self):
        spoken = ProseBlock().narration_text(
            "See the [canonical data model](https://eip.com/patterns/Canonical.html) pattern."
        )
        self.assertEqual(spoken, "See the canonical data model pattern.")

    def test_a_url_written_as_the_visible_text_is_reduced_to_its_host(self):
        block = ProseBlock()
        self.assertEqual(
            block.narration_text("Docs at <https://dataengineering.wiki/Concepts/Medallion>."),
            "Docs at dataengineering dot wiki.",
        )
        self.assertEqual(
            block.narration_text("Go to https://www.semprini.me/data_products/ for part one."),
            "Go to semprini dot me for part one.",
        )


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
        kinds = [segment.kind for segment in self.page.narration_script()]
        self.assertEqual(kinds, ["heading"])


def _document():
    from django.core.files.base import ContentFile
    from wagtail.documents import get_document_model

    doc = get_document_model()(title="narration")
    doc.file.save("narration.mp3", ContentFile(b"not really audio"), save=True)
    return doc


class FakeEngine:
    """Records what it was asked to say. Nothing in the test suite may ever
    reach a real provider - that would cost money on every CI run."""

    name = "fake"
    revision = "fake-v1"

    def __init__(self):
        self.said = []
        self.context = []

    def synthesize(self, text, voice, previous_text="", next_text=""):
        self.said.append(text)
        self.context.append((previous_text, next_text))
        return Clip(audio=b"\x00" * 16, duration_s=1.0, words=[[0.0, 0.5, text.split()[0]]])


def _fake_render(pieces, clips):
    """Stands in for ffmpeg: one second per clip, no gap."""
    cues, at = [], 0.0
    for piece in pieces:
        cues.append({"id": piece.block_id, "kind": piece.kind, "start": at, "end": at + 1.0})
        at += 1.0
    return segmenter.Rendered(audio=b"mp3", duration_s=at, cues=cues, words=[])


class NarrationPageMixin:
    def make_page(self, sections=None, title="Listen", slug="listen"):
        root = Page.objects.get(depth=1)
        blog = BlogPage.objects.first()
        if blog is None:
            blog = BlogPage(title="Blog", slug="blog")
            root.add_child(instance=blog)
        page = AudioEntryPage(
            title=title,
            slug=slug,
            sections=sections
            or [
                {"type": "heading", "value": {"text": "One", "level": "h2"}},
                {"type": "text", "value": "First part."},
            ],
        )
        blog.add_child(instance=page)
        return page

    def make_voice(self):
        return Voice.objects.create(
            site=Site.objects.first(),
            key="test",
            label="Test",
            engine="fake",
            engine_voice_id="abc123",
            is_default=True,
        )


class ScriptHashTests(NarrationPageMixin, TestCase):
    """The hash is the spend guard: it must ignore cosmetics and notice order.

    It is taken over block ids as well as text, which is why these work at the
    segment level - re-assigning a StreamField mints new ids and would hide the
    behaviour under test.
    """

    def test_whitespace_changes_do_not_rerecord(self):
        tidy = [Segment("b1", "text", "First part.")]
        messy = [Segment("b1", "text", " First   part.\n")]
        self.assertEqual(narration.script_hash(tidy), narration.script_hash(messy))

    def test_reordering_blocks_does_rerecord(self):
        segments = [Segment("b1", "text", "One."), Segment("b2", "text", "Two.")]
        self.assertNotEqual(
            narration.script_hash(segments), narration.script_hash(list(reversed(segments)))
        )

    def test_rewriting_a_page_changes_its_hash(self):
        page = self.make_page()
        before = narration.script_hash(narration.build_script(page))
        page.sections = [{"type": "text", "value": "Something else entirely."}]
        self.assertNotEqual(narration.script_hash(narration.build_script(page)), before)

    def test_control_characters_never_reach_the_engine(self):
        self.assertEqual(narration.sanitise("hi\x07 there\u200b"), "hi there")


class QueueTests(NarrationPageMixin, TestCase):
    def setUp(self):
        self.voice = self.make_voice()
        self.page = self.make_page()

    def test_queueing_creates_a_pending_rendition_and_job(self):
        rendition = narration.queue_render(self.page)
        self.assertEqual(rendition.status, RenditionStatus.PENDING)
        self.assertEqual(rendition.job.state, JobState.QUEUED)

    def test_an_existing_ready_rendition_is_never_paid_for_twice(self):
        rendition = narration.queue_render(self.page)
        Rendition.objects.filter(pk=rendition.pk).update(status=RenditionStatus.READY)

        again = narration.queue_render(self.page)

        self.assertEqual(again.pk, rendition.pk)
        self.assertEqual(Rendition.objects.count(), 1)

    def test_editing_cancels_the_superseded_job(self):
        first = narration.queue_render(self.page)
        self.page.sections = [{"type": "text", "value": "Completely different."}]
        second = narration.queue_render(self.page)

        first.job.refresh_from_db()
        self.assertEqual(first.job.state, JobState.CANCELLED)
        self.assertEqual(second.job.state, JobState.QUEUED)

    def test_oversized_scripts_are_rejected_before_any_request(self):
        self.page.sections = [{"type": "text", "value": "word " * 200}]
        with override_settings(DEVCAST_MAX_SCRIPT_CHARS=50):
            with self.assertRaises(narration.BudgetExceeded):
                narration.queue_render(self.page)
        self.assertFalse(Rendition.objects.exists())

    def test_narration_disabled_queues_nothing(self):
        self.page.narration_enabled = False
        self.assertIsNone(narration.queue_render(self.page))

    def test_the_site_voice_is_used_when_the_page_names_none(self):
        self.assertEqual(narration.queue_render(self.page).voice, self.voice)

    def test_a_page_may_override_the_site_voice(self):
        guest = Voice.objects.create(
            site=Site.objects.first(),
            key="guest",
            label="Guest",
            engine="fake",
            engine_voice_id="def456",
        )
        self.page.voice = guest
        self.page.save()

        self.assertEqual(narration.queue_render(self.page).voice, guest)


class LeaseTests(NarrationPageMixin, TestCase):
    def setUp(self):
        self.make_voice()
        self.page = self.make_page()
        narration.queue_render(self.page)

    def test_a_leased_job_is_not_handed_out_twice(self):
        self.assertIsNotNone(narration.claim_job("worker-a"))
        self.assertIsNone(narration.claim_job("worker-b"))

    def test_an_expired_lease_is_reclaimed(self):
        job = narration.claim_job("worker-a")
        RenderJob.objects.filter(pk=job.pk).update(
            leased_until=timezone.now() - datetime.timedelta(minutes=1)
        )
        self.assertIsNotNone(narration.claim_job("worker-b"))

    def test_a_job_stops_being_retried_after_the_attempt_cap(self):
        with override_settings(DEVCAST_RENDER_ATTEMPTS=1):
            self.assertIsNotNone(narration.claim_job())
            RenderJob.objects.update(state=JobState.QUEUED)
            self.assertIsNone(narration.claim_job())


class RenderTests(NarrationPageMixin, TestCase):
    def setUp(self):
        self.make_voice()
        self.page = self.make_page()
        self.rendition = narration.queue_render(self.page)
        self.engine = FakeEngine()

    def render(self):
        with mock.patch.object(segmenter, "render", _fake_render):
            return narration.render(self.rendition, engine=self.engine)

    def test_rendering_stores_audio_cues_and_duration(self):
        rendition = self.render()
        self.assertEqual(rendition.status, RenditionStatus.READY)
        self.assertEqual(rendition.duration_ms, 2000)
        self.assertEqual(
            [cue["id"] for cue in rendition.cues],
            [str(block.id) for block in self.page.sections],
        )

    def test_each_clip_is_told_what_surrounds_it(self):
        self.render()
        first, second = self.engine.context
        self.assertEqual(first, ("", self.engine.said[1]))
        self.assertEqual(second, (self.engine.said[0], ""))

    def test_a_stale_job_is_refused_rather_than_recording_the_wrong_words(self):
        self.page.sections = [{"type": "text", "value": "Rewritten."}]
        self.page.save()
        with self.assertRaises(EngineError):
            self.render()

    def test_the_monthly_budget_stops_a_render(self):
        with override_settings(DEVCAST_MONTHLY_CHAR_BUDGET=1):
            with self.assertRaises(narration.BudgetExceeded):
                self.render()

    def test_a_failure_is_recorded_and_retried(self):
        job = narration.claim_job()
        self.engine.synthesize = mock.Mock(side_effect=EngineError("provider exploded"))

        with mock.patch.object(segmenter, "render", _fake_render):
            self.assertFalse(narration.run_job(job, engine=self.engine))

        job.refresh_from_db()
        self.rendition.refresh_from_db()
        self.assertEqual(job.state, JobState.QUEUED)
        self.assertEqual(self.rendition.status, RenditionStatus.FAILED)
        self.assertIn("provider exploded", self.rendition.error)

    def test_long_blocks_split_for_the_engine_but_stay_one_cue(self):
        long_text = " ".join(f"Sentence number {n}." for n in range(60))
        self.page.sections = [{"type": "text", "value": long_text}]
        self.page.save()
        rendition = narration.queue_render(self.page, force=True)
        self.rendition = rendition

        with override_settings(DEVCAST_MAX_SEGMENT_CHARS=100):
            self.render()

        self.assertGreater(len(self.engine.said), 1)
        self.assertEqual(len(rendition.cues), 1)
        self.assertEqual(rendition.cues[0]["end"], len(self.engine.said))


class CueTrackFromRenditionTests(NarrationPageMixin, TestCase):
    def setUp(self):
        self.make_voice()
        self.page = self.make_page()
        self.rendition = narration.queue_render(self.page)

    def _make_ready(self, rendition):
        rendition.audio.save("n.mp3", ContentFile(b"mp3"), save=False)
        rendition.status = RenditionStatus.READY
        rendition.duration_ms = 2000
        rendition.cues = [{"id": str(self.page.sections[0].id), "start": 0, "end": 2}]
        rendition.completed_at = timezone.now()
        rendition.save()

    def test_a_ready_rendition_becomes_the_track(self):
        self._make_ready(self.rendition)
        track = self.page.cue_track
        self.assertFalse(track["stale"])
        self.assertEqual(track["audio"]["duration"], 2.0)

    def test_an_edit_marks_the_old_recording_stale_rather_than_hiding_it(self):
        self._make_ready(self.rendition)
        self.page.sections = [{"type": "text", "value": "Rewritten."}]
        self.assertTrue(self.page.cue_track["stale"])

    def test_pending_narration_falls_back_to_no_player(self):
        self.assertIsNone(self.page.cue_track)


class VoiceTuningTests(NarrationPageMixin, TestCase):
    def test_unset_sliders_are_left_to_the_provider(self):
        voice = self.make_voice()
        voice.stability = 0.45
        self.assertEqual(voice.engine_settings, {"stability": 0.45})

    def test_extra_settings_ride_alongside_the_sliders(self):
        voice = self.make_voice()
        voice.speed = 1.1
        voice.extra_settings = {"seed": 7}
        self.assertEqual(voice.engine_settings, {"speed": 1.1, "seed": 7})

    def test_retuning_invalidates_existing_renditions(self):
        voice = self.make_voice()
        voice.stability = 0.45
        before = voice.tuning_rev
        voice.stability = 0.9
        self.assertNotEqual(voice.tuning_rev, before)


class PruneTests(NarrationPageMixin, TestCase):
    def test_the_previous_recording_survives_a_re_render(self):
        voice = self.make_voice()
        page = self.make_page()
        for index in range(4):
            Rendition.objects.create(
                page_id=page.pk,
                voice=voice,
                script_hash=f"{index:064d}",
                engine="fake",
                engine_rev="fake-v1",
                status=RenditionStatus.READY,
            )
        narration.prune_page(page.pk)
        self.assertEqual(Rendition.objects.count(), 2)


class AlignmentTests(TestCase):
    def test_character_timings_collapse_into_words(self):
        words = words_from_alignment(
            {
                "characters": list("hi there"),
                "character_start_times_seconds": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7],
                "character_end_times_seconds": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
            }
        )
        self.assertEqual(words, [[0.0, 0.2, "hi"], [0.3, 0.8, "there"]])

    def test_mismatched_alignment_is_dropped_not_guessed(self):
        self.assertEqual(
            words_from_alignment({"characters": ["a"], "character_start_times_seconds": []}),
            [],
        )


class RichTextConversionTests(TestCase):
    def test_rules_and_images_split_prose_into_addressable_blocks(self):
        image = Image.objects.create(
            title="Diagram",
            file=ImageFile(BytesIO(_PNG), name="diagram.png"),
            width=1,
            height=1,
        )
        html = (
            '<p data-block-key="a">First.</p><hr/>'
            '<p data-block-key="b">Second.</p>'
            f'<embed embedtype="image" format="fullwidth" id="{image.pk}" alt="A diagram"/>'
            '<p data-block-key="c">Third.</p>'
        )

        blocks = blocks_from_richtext(html)

        self.assertEqual(
            [kind for kind, _ in blocks], ["text", "text", "image", "text"]
        )
        self.assertEqual(blocks[0][1], "First.")
        self.assertEqual(blocks[2][1]["caption"], "A diagram")

    def test_empty_paragraphs_do_not_become_silent_blocks(self):
        self.assertEqual(blocks_from_richtext('<p data-block-key="a"></p><hr/>'), [])


# A 1x1 PNG, so the conversion test can make a real image without a fixture.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)
