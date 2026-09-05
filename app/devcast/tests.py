import datetime

from django.test import TestCase
from puput.models import BlogPage
from wagtail.models import Page

from .blocks import CodeBlock, ProseBlock
from .models import ChangelogEntry, DevProjectPage


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
