"""Every project-tunable value devcast reads, in one place.

Nothing else in the package touches ``django.conf.settings``: keeping the reads
here is what lets devcast be lifted out into a standalone distribution later.
"""

from django.conf import settings


def _get(name, default):
    return getattr(settings, f"DEVCAST_{name}", default)


def page_base():
    """Dotted path to the Page class devcast's page types inherit from.

    Defaults to plain Wagtail. semprini points it at ``puput.models.EntryPage``
    so project and audio pages join the blog's listing, feeds and archives.
    Changing this after the first migration changes the table shape, so it has
    to be decided up front.
    """
    return _get("PAGE_BASE", "wagtail.models.Page")


def puput_integration():
    return _get("PUPUT_INTEGRATION", False)


def base_template():
    """Template devcast pages extend. It must provide ``content`` and
    ``extra_content`` blocks; this site points it at puput's, so project pages
    keep the blog header, avatar and sidebar."""
    return _get("BASE_TEMPLATE", "base.html")


def changelog_initial_releases():
    """How many releases render expanded-capable before the rest are collapsed."""
    return _get("CHANGELOG_INITIAL_RELEASES", 10)
