from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from django.contrib.auth.models import User
import logging

logger = logging.getLogger(__name__)


class SempriniOIDCBackend(OIDCAuthenticationBackend):
    """Extends the default OIDC backend with Keycloak-specific behaviour:
    - Uses preferred_username as the Django username.
    - Maps the Keycloak realm role 'wagtail_admin' to is_staff.
    - Maps the Keycloak realm role 'superuser' to is_superuser.
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

            self._sync_roles(user, claims, access_token)
            user.save()
            logger.info(f'OIDC user saved: {user.username}, is_staff={user.is_staff}, is_superuser={user.is_superuser}')
            return user
        except Exception as e:
            logger.error(f'OIDC error: {e}', exc_info=True)
            raise

    def _sync_roles(self, user, claims, access_token):
        # Extract roles from both realm and client scopes
        roles = []

        # Realm roles (global roles in Keycloak)
        if 'realm_access' in claims and isinstance(claims['realm_access'], dict):
            realm_roles = claims['realm_access'].get('roles', [])
            roles.extend(realm_roles)

        # Client roles (client-specific roles for semprini-blog)
        if 'resource_access' in claims and isinstance(claims['resource_access'], dict):
            client_roles_obj = claims['resource_access'].get('semprini-blog', {})
            if isinstance(client_roles_obj, dict):
                client_roles = client_roles_obj.get('roles', [])
                roles.extend(client_roles)

        # If still empty, try to decode access_token to get roles
        if not roles and access_token:
            try:
                import json
                import base64
                # JWT is header.payload.signature
                parts = access_token.split('.')
                if len(parts) >= 2:
                    # Decode payload (add padding if needed)
                    payload_b64 = parts[1]
                    padding = 4 - len(payload_b64) % 4
                    if padding != 4:
                        payload_b64 += '=' * padding
                    access_claims = json.loads(base64.urlsafe_b64decode(payload_b64))
                    if 'realm_access' in access_claims:
                        roles.extend(access_claims['realm_access'].get('roles', []))
                    if 'resource_access' in access_claims:
                        client_roles_obj = access_claims['resource_access'].get('semprini-blog', {})
                        if isinstance(client_roles_obj, dict):
                            roles.extend(client_roles_obj.get('roles', []))
            except Exception as e:
                logger.warning(f'Could not decode access_token for roles: {e}')

        # Remove duplicates while preserving order
        roles = list(dict.fromkeys(roles))
        user.is_staff = 'wagtail_admin' in roles or 'superuser' in roles
        user.is_superuser = 'superuser' in roles

