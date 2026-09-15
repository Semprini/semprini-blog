import base64
import json

from django.contrib.auth.models import Group, User
from django.test import TestCase

from oidc_backend import SempriniOIDCBackend


def claims(username, client_roles=None, realm_roles=None):
    """ID token claims as Keycloak issues them for the semprini-blog client."""
    c = {'preferred_username': username, 'email': f'{username}@example.com'}
    if client_roles is not None:
        c['resource_access'] = {'semprini-blog': {'roles': client_roles}}
    if realm_roles is not None:
        c['realm_access'] = {'roles': realm_roles}
    return c


def access_token(payload):
    segment = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip('=')
    return f'header.{segment}.signature'


class OIDCBackendAccessTests(TestCase):
    def setUp(self):
        self.backend = SempriniOIDCBackend()
        # Wagtail's own migrations create both groups.
        self.editors = Group.objects.get_or_create(name='Editors')[0]
        self.moderators = Group.objects.get_or_create(name='Moderators')[0]

    def login(self, id_claims, token=None):
        return self.backend.get_or_create_user(token, None, id_claims)

    def assert_no_access(self, user):
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
        self.assertEqual(list(user.groups.all()), [])
        self.assertFalse(user.has_perm('wagtailadmin.access_admin'))

    def test_guest_gets_no_access(self):
        user = self.login(claims('visitor', realm_roles=['default-roles-semprini', 'guest']))
        self.assert_no_access(user)

    def test_guest_loses_access_granted_by_hand(self):
        user = User.objects.create(username='visitor', is_superuser=True, is_staff=True)
        user.groups.set([self.editors, self.moderators])
        self.login(claims('visitor', realm_roles=['guest']))
        self.assert_no_access(user)

    def test_realm_superuser_grants_nothing(self):
        user = self.login(claims('conk-editor', realm_roles=['superuser', 'wagtail_admin']))
        self.assert_no_access(user)

    def test_other_clients_roles_grant_nothing(self):
        c = claims('someone')
        c['resource_access'] = {'grafana': {'roles': ['superuser', 'wagtail_moderator']}}
        self.assert_no_access(self.login(c))

    def test_client_superuser(self):
        user = self.login(claims('owner', client_roles=['superuser']))
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_staff)

    def test_wagtail_admin_is_staff_only(self):
        user = self.login(claims('staffer', client_roles=['wagtail_admin']))
        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_editor_and_moderator_roles_set_groups(self):
        user = self.login(claims('writer', client_roles=['wagtail_editor']))
        self.assertEqual({g.name for g in user.groups.all()}, {'Editors'})
        self.login(claims('writer', client_roles=['wagtail_moderator']))
        self.assertEqual({g.name for g in user.groups.all()}, {'Moderators'})

    def test_roles_read_from_access_token_when_id_token_lacks_them(self):
        token = access_token({'resource_access': {'semprini-blog': {'roles': ['superuser']}}})
        user = self.login(claims('owner'), token=token)
        self.assertTrue(user.is_superuser)

    def test_unreadable_access_token_grants_nothing(self):
        user = self.login(claims('visitor'), token='not-a-jwt')
        self.assert_no_access(user)
