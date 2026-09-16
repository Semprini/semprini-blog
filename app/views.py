import os

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage
from django.http import HttpResponse, JsonResponse
from django.views.generic.base import RedirectView

from mozilla_django_oidc.views import OIDCAuthenticationRequestView


def heartbeat(request):
    return JsonResponse({ 'build_number': f'{os.environ.get("BUILD_NUMBER", "0")}' })


def robots_txt(request):
    return HttpResponse(
        "User-agent: *\n"
        "Disallow: /admin/\n"
        "Disallow: /django-admin/\n"
        # The comment form's action is a POST-only endpoint, so a crawler that
        # treats it as a link just collects 405s. SemrushBot does exactly that.
        "Disallow: /feedback/\n"
        "Sitemap: https://www.semprini.me/sitemap.xml\n",
        content_type="text/plain",
    )


class FaviconRedirectView(RedirectView):
    """Points /favicon.ico at the real icon, wherever static happens to live.

    Resolved per request rather than at import time because STATIC_URL is S3 in
    production and a local path in development.
    """

    permanent = True

    def get_redirect_url(self, *args, **kwargs):
        return staticfiles_storage.url('images/favicon.ico')


favicon_ico = FaviconRedirectView.as_view()


class SempriniOIDCAuthenticationRequestView(OIDCAuthenticationRequestView):
    """Adds Keycloak's kc_idp_hint parameter so a link can name the provider.

    Without a hint Keycloak shows its own page with a button per identity
    provider; with one it redirects straight to that provider, which is what
    the header's GitHub button wants. The hint comes from ?idp= and is checked
    against OIDC_IDP_HINTS, so a crafted link cannot bounce visitors off to a
    provider the realm was never configured with.
    """

    def get_extra_params(self, request):
        params = super().get_extra_params(request)
        idp = request.GET.get('idp')
        if idp in settings.OIDC_IDP_HINTS:
            # A copy: the parent returns OIDC_AUTH_REQUEST_EXTRA_PARAMS itself.
            params = {**params, 'kc_idp_hint': idp}
        return params
