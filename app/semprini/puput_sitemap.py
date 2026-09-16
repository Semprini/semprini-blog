"""Fix puput's sitemap entries for a blog mounted at the site root.

``puput.models.EntryPage.get_sitemap_urls`` builds its own location rather than
using ``Page.get_full_url``, because entries are served from the dated
``/YYYY/MM/DD/slug/`` route and not from their Wagtail path. To do that it calls
``puput.urls.get_entry_url(entry, blog_page, root_page)``, which picks between
two URL names depending on whether the blog *is* the site root:

    entry_page_serve         /2018/12/20/slug/
    entry_page_serve_slug    /<blog_path>/2018/12/20/slug/

Every other caller - the ``entry_url`` template tag, the feeds, and
``devcast.integrations.puput`` - passes a ``Site.root_page``. ``get_sitemap_urls``
passes ``self.get_url_parts()[1]`` instead, which is the root *URL string*. A
string never equals a Page, so the comparison is always false and the slug
branch always wins. semprini.me mounts the blog at the site root, so
``blog_path`` comes out empty, ``<path:blog_path>`` will not reverse against an
empty string, and the whole of /sitemap.xml 500s on the first entry.

Passing the Site's actual root page is all that is needed. Entries under a blog
that is not the site root are unaffected - they took the slug branch before and
still do.
"""


def _get_sitemap_urls(self, request=None):
    from wagtail.models import Site
    from puput.urls import get_entry_url

    url_parts = self.get_url_parts(request)
    if url_parts is None:
        # No site routes to this page, so it has no canonical URL to list.
        return []
    site_id, root_url, page_path = url_parts

    lastmod = self.last_published_at or self.latest_revision_created_at

    site = Site.objects.filter(pk=site_id).select_related("root_page").first()
    if site is None:
        return [{"location": root_url + page_path, "lastmod": lastmod}]

    entry_url = get_entry_url(self, self.blog_page.page_ptr, site.root_page)
    return [{"location": root_url + entry_url, "lastmod": lastmod}]


def install():
    """Replace ``EntryPage.get_sitemap_urls``.

    Patching the model rather than subclassing it is what reaches the blog's
    existing plain ``EntryPage`` rows; devcast's page types inherit it too,
    since ``DEVCAST_PAGE_BASE`` resolves to this class.
    """
    from puput.models import EntryPage

    EntryPage.get_sitemap_urls = _get_sitemap_urls
