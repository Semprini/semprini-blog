from django import template

from .. import conf

register = template.Library()


@register.simple_tag(takes_context=True)
def devcast_url(context, page):
    """Link to a devcast page the way its host blog expects.

    Under puput that is the dated ``/YYYY/MM/DD/slug/`` form rather than
    Wagtail's tree URL, which puput does not route.
    """
    request = context.get("request")
    if conf.puput_integration() and request is not None and hasattr(page, "blog_page"):
        from ..integrations.puput import entry_url

        return entry_url(page, request)
    return page.url


@register.filter
def is_dev_project(page):
    from ..models import DevProjectPage

    return isinstance(page, DevProjectPage)
