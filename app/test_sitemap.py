import datetime

from django.test import TestCase
from wagtail.models import Page, Site

from puput.models import BlogPage, EntryPage


class SitemapTests(TestCase):
    """/sitemap.xml with the blog mounted at the site root.

    puput builds entry locations itself rather than using ``Page.get_full_url``,
    and the root-mounted case is the one it gets wrong - see
    ``semprini.puput_sitemap``.
    """

    def setUp(self):
        root = Page.objects.get(depth=1)
        self.blog = BlogPage(title="Semprini", slug="semprini", description="")
        root.add_child(instance=self.blog)

        self.entry = EntryPage(
            title="Vestigial Technology",
            slug="vestigial_technology",
            body="<p>Hello.</p>",
            date=datetime.datetime(2018, 12, 20, 9, 0),
        )
        self.blog.add_child(instance=self.entry)
        self.entry.save_revision().publish()

        # The blog *is* the site root, which is how semprini.me is laid out.
        site = Site.objects.get(is_default_site=True)
        site.root_page = self.blog
        site.hostname = "testserver"
        site.port = 80
        site.save()

    def test_sitemap_renders(self):
        response = self.client.get("/sitemap.xml")

        self.assertEqual(response.status_code, 200)

    def test_entry_uses_its_dated_url(self):
        response = self.client.get("/sitemap.xml")

        self.assertContains(
            response, "http://testserver/2018/12/20/vestigial_technology/"
        )

    def test_entry_sitemap_url_matches_the_url_templates_link_to(self):
        [url_info] = self.entry.get_sitemap_urls()

        self.assertEqual(
            url_info["location"],
            "http://testserver/2018/12/20/vestigial_technology/",
        )


class SitemapUnderPrefixTests(TestCase):
    """The blog sitting below the site root still gets its ``/blog/...`` path."""

    def setUp(self):
        root = Page.objects.get(depth=1)
        home = Page(title="Home", slug="home-2")
        root.add_child(instance=home)

        self.blog = BlogPage(title="Blog", slug="blog", description="")
        home.add_child(instance=self.blog)

        self.entry = EntryPage(
            title="Post",
            slug="post",
            body="<p>Hello.</p>",
            date=datetime.datetime(2018, 12, 20, 9, 0),
        )
        self.blog.add_child(instance=self.entry)
        self.entry.save_revision().publish()

        site = Site.objects.get(is_default_site=True)
        site.root_page = home
        site.hostname = "testserver"
        site.port = 80
        site.save()

    def test_entry_keeps_the_blog_path(self):
        [url_info] = self.entry.get_sitemap_urls()

        self.assertEqual(
            url_info["location"], "http://testserver/blog/2018/12/20/post/"
        )
