"""Optional puput glue, kept in one file so nothing else in devcast imports it.

puput's ``BlogPage`` names its allowed children by exact label, and Wagtail
resolves those labels once and caches the result on the class. Subclassing
``EntryPage`` is therefore not enough on its own - the label has to be added to
the list and the cache dropped before anything asks what can live under a blog.
"""

PAGE_TYPES = ("devcast.DevProjectPage",)


def install():
    from puput.models import BlogPage

    added = False
    for label in PAGE_TYPES:
        if label not in BlogPage.subpage_types:
            BlogPage.subpage_types.append(label)
            added = True
    if added:
        BlogPage._clean_subpage_models = None


def entry_url(page, request):
    """The dated ``/YYYY/MM/DD/slug/`` URL puput serves entries from."""
    from wagtail.models import Site
    from puput.urls import get_entry_url

    site = Site.find_for_request(request)
    if site is None:
        return page.url
    return get_entry_url(page, page.blog_page.page_ptr, site.root_page)


def default_blog_page(request):
    """The site's blog, so pages outside its subtree can still render puput's
    header and sidebar."""
    from wagtail.models import Site
    from puput.models import BlogPage

    site = Site.find_for_request(request)
    if site is None:
        return None
    return (
        BlogPage.objects.live()
        .descendant_of(site.root_page, inclusive=True)
        .first()
    )
