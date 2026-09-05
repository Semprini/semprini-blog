import os

from django.conf import settings
from django.http import JsonResponse

from mozilla_django_oidc.views import OIDCAuthenticationRequestView


def heartbeat(request):
    return JsonResponse({ 'build_number': f'{os.environ.get("BUILD_NUMBER", "0")}' })


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
