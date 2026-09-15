from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.contrib.auth.models import Group, User
import base64
import json
import logging

logger = logging.getLogger(__name__)

# The Keycloak client whose roles grant access to this blog.
CLIENT_ID = 'semprini-blog'

# semprini-blog client roles -> the Django groups they grant.
ROLE_GROUPS = {
    'wagtail_editor': 'Editors',
    'wagtail_moderator': 'Moderators',
}


class SempriniOIDCBackend(OIDCAuthenticationBackend):
    """Keycloak login, with Keycloak as the only source of blog permissions.

    - preferred_username is the Django username.
    - Only client roles on the semprini-blog Keycloak client count. Realm roles are
      ignored: other apps use realm roles such as `superuser` (conk), and holding
      one must not grant anything here.
    - Every login rebuilds the user's access from those roles:
        superuser          -> is_superuser and is_staff
        wagtail_admin      -> is_staff
        wagtail_editor     -> Editors group
        wagtail_moderator  -> Moderators group
      and removes every other group. An admin flag or group set by hand in the
      Wagtail admin lasts only until that user's next login, so grant access in
      Keycloak instead. Without the group sync, a guest whose groups had been
      edited by hand kept moderator access indefinitely.
    """

    def get_username(self, claims):
        username = claims.get('preferred_username') or super().get_username(claims)
        return username

    def get_or_create_user(self, access_token, id_token, payload):
        """Called by the parent authenticate() with the token response payload."""
        claims = payload
        username = self.get_username(claims)
        email = claims.get('email', '')
        logger.info(f'OIDC authenticate: username={username}, email={email}')

        try:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': claims.get('given_name', ''),
                    'last_name': claims.get('family_name', ''),
                }
            )
            if not created:
                user.email = email
                user.first_name = claims.get('given_name', '')
                user.last_name = claims.get('family_name', '')

            self._sync_access(user, self._client_roles(claims, access_token))
            user.save()
            logger.info(f'OIDC user saved: {user.username}, is_staff={user.is_staff}, is_superuser={user.is_superuser}')
            return user
        except Exception as e:
            logger.error(f'OIDC error: {e}', exc_info=True)
            raise

    @staticmethod
    def _client_roles(claims, access_token):
        """The user's semprini-blog client roles.

        Read from the ID token. Keycloak leaves resource_access out when the user
        holds no roles on any client, so fall back to the access token, which came
        straight from Keycloak's token endpoint.
        """
        def from_claims(c):
            access = c.get('resource_access')
            if not isinstance(access, dict):
                return None
            client = access.get(CLIENT_ID)
            roles = client.get('roles', []) if isinstance(client, dict) else []
            return [r for r in roles if isinstance(r, str)]

        roles = from_claims(claims)
        if roles is None and access_token:
            try:
                segment = access_token.split('.')[1]
                segment += '=' * (-len(segment) % 4)
                roles = from_claims(json.loads(base64.urlsafe_b64decode(segment)))
            except (IndexError, ValueError) as e:
                logger.warning(f'Could not read roles from the access token: {e}')
        return set(roles or [])

    @staticmethod
    def _sync_access(user, roles):
        user.is_superuser = 'superuser' in roles
        user.is_staff = user.is_superuser or 'wagtail_admin' in roles

        wanted = {group for role, group in ROLE_GROUPS.items() if role in roles}
        groups = list(Group.objects.filter(name__in=wanted))
        missing = wanted - {g.name for g in groups}
        if missing:
            logger.warning(f'OIDC roles for {user.username} name missing Django groups: {sorted(missing)}')
        before = set(user.groups.values_list('name', flat=True))
        user.groups.set(groups)
        after = {g.name for g in groups}
        if before != after:
            logger.info(f'OIDC groups for {user.username}: {sorted(before)} -> {sorted(after)}')
