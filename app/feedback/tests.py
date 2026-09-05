from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from puput.models import BlogPage, EntryPage
from wagtail.models import Page, Site

from .models import Comment, Reaction

User = get_user_model()


class FeedbackTestCase(TestCase):
    def setUp(self):
        root = Page.objects.get(depth=1)
        self.blog = BlogPage(title='Blog', slug='blog')
        root.add_child(instance=self.blog)
        self.entry = EntryPage(title='A post', slug='a-post', body='<p>hi</p>')
        self.blog.add_child(instance=self.entry)
        self.entry.save_revision().publish()
        Site.objects.all().update(root_page=root)

        self.moderator = User.objects.create_superuser('mod', 'mod@example.com', 'pw')
        self.entry_url = self.entry.url

    def post_comment(self, client=None, **data):
        client = client or self.client
        payload = {'body': 'hello there', 'next': self.entry_url}
        payload.update(data)
        return client.post(
            reverse('feedback_add_comment', args=[self.entry.id]), payload
        )

    # --- commenting ---------------------------------------------------------

    def test_anonymous_can_comment_and_it_waits_for_approval(self):
        response = self.post_comment(author_name='Ada')

        comment = Comment.objects.get()
        self.assertEqual(comment.author_name, 'Ada')
        self.assertIsNone(comment.user_id)
        self.assertFalse(comment.is_approved)
        self.assertTrue(comment.session_key)
        self.assertIn('comment=pending', response['Location'])

    def test_anonymous_comment_without_a_name_shows_as_anonymous(self):
        self.post_comment()
        self.assertEqual(str(Comment.objects.get().display_name), 'Anonymous')

    def test_pending_comment_is_hidden_from_other_visitors(self):
        self.post_comment(body='super secret', author_name='Ada')

        other = self.client_class()
        self.assertNotContains(other.get(self.entry_url), 'super secret')

    def test_author_sees_their_own_pending_comment(self):
        self.post_comment(body='super secret', author_name='Ada')

        page = self.client.get(self.entry_url)
        self.assertContains(page, 'super secret')
        self.assertContains(page, 'awaiting approval')

    def test_approved_comment_is_public(self):
        self.post_comment(body='super secret')
        Comment.objects.get().approve(self.moderator)

        other = self.client_class()
        self.assertContains(other.get(self.entry_url), 'super secret')

    def test_moderator_comment_is_approved_on_arrival(self):
        self.client.force_login(self.moderator)
        response = self.post_comment(body='from the desk of the mod')

        self.assertTrue(Comment.objects.get().is_approved)
        self.assertIn('comment=posted', response['Location'])

    def test_honeypot_silently_drops_the_comment(self):
        self.post_comment(website='http://spam.example')
        self.assertFalse(Comment.objects.exists())

    def test_empty_comment_is_ignored(self):
        self.post_comment(body='   ')
        self.assertFalse(Comment.objects.exists())

    def test_comment_on_unknown_entry_is_404(self):
        response = self.client.post(
            reverse('feedback_add_comment', args=[999999]), {'body': 'hi'}
        )
        self.assertEqual(response.status_code, 404)

    def test_next_cannot_redirect_off_site(self):
        response = self.post_comment(next='https://evil.example/steal')
        self.assertTrue(response['Location'].startswith(self.entry_url))

    # --- moderation ---------------------------------------------------------

    def test_moderator_can_approve_and_unapprove_from_the_page(self):
        self.post_comment()
        comment = Comment.objects.get()
        url = reverse('feedback_moderate_comment', args=[comment.id])

        self.client.force_login(self.moderator)
        self.client.post(url, {'action': 'approve', 'next': self.entry_url})
        comment.refresh_from_db()
        self.assertTrue(comment.is_approved)
        self.assertEqual(comment.moderated_by, self.moderator)

        self.client.post(url, {'action': 'unapprove', 'next': self.entry_url})
        comment.refresh_from_db()
        self.assertFalse(comment.is_approved)

    def test_visitors_cannot_moderate(self):
        self.post_comment()
        comment = Comment.objects.get()

        response = self.client.post(
            reverse('feedback_moderate_comment', args=[comment.id]),
            {'action': 'approve'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Comment.objects.get().is_approved)

    def test_moderator_sees_pending_comments(self):
        self.post_comment(body='super secret')

        self.client.force_login(self.moderator)
        page = self.client.get(self.entry_url)
        self.assertContains(page, 'super secret')
        self.assertContains(page, 'approve')

    # --- replies ------------------------------------------------------------

    def test_moderator_can_reply_to_a_comment(self):
        self.post_comment(body='a question')
        question = Comment.objects.get()

        self.client.force_login(self.moderator)
        self.post_comment(body='an answer', parent_id=question.id)

        reply = Comment.objects.get(parent=question)
        self.assertTrue(reply.by_moderator)
        self.assertTrue(reply.is_approved)

    def test_replies_do_not_nest_more_than_one_level(self):
        self.post_comment(body='a question')
        question = Comment.objects.get()
        self.client.force_login(self.moderator)
        self.post_comment(body='an answer', parent_id=question.id)
        reply = Comment.objects.get(parent=question)

        self.post_comment(body='a follow-up', parent_id=reply.id)
        self.assertEqual(Comment.objects.get(body='a follow-up').parent_id, question.id)

    def test_visitors_cannot_reply(self):
        self.post_comment(body='a question')
        question = Comment.objects.get()

        self.post_comment(body='me too', parent_id=question.id)
        self.assertIsNone(Comment.objects.get(body='me too').parent_id)

    # --- deleting -----------------------------------------------------------

    def test_anonymous_author_can_delete_their_own_comment(self):
        self.post_comment()
        comment = Comment.objects.get()

        self.client.post(
            reverse('feedback_delete_comment', args=[comment.id]),
            {'next': self.entry_url},
        )
        self.assertFalse(Comment.objects.exists())

    def test_other_visitors_cannot_delete_a_comment(self):
        self.post_comment()
        comment = Comment.objects.get()

        other = self.client_class()
        response = other.post(
            reverse('feedback_delete_comment', args=[comment.id]),
            {'next': self.entry_url},
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Comment.objects.exists())

    # --- reactions ----------------------------------------------------------

    def test_anonymous_visitor_can_react_and_unreact(self):
        url = reverse('feedback_react', args=[self.entry.id])

        response = self.client.post(url, {'reaction_type': 'love'})
        self.assertEqual(response.json()['counts'], {'love': 1})
        self.assertEqual(response.json()['user_reactions'], ['love'])

        response = self.client.post(url, {'reaction_type': 'love'})
        self.assertEqual(response.json()['counts'], {})
        self.assertFalse(Reaction.objects.exists())

    def test_reactions_are_kept_apart_per_visitor(self):
        url = reverse('feedback_react', args=[self.entry.id])
        self.client.post(url, {'reaction_type': 'love'})

        other = self.client_class()
        response = other.post(url, {'reaction_type': 'love'})
        self.assertEqual(response.json()['counts'], {'love': 2})

    def test_unknown_reaction_type_is_rejected(self):
        response = self.client.post(
            reverse('feedback_react', args=[self.entry.id]), {'reaction_type': 'shrug'}
        )
        self.assertEqual(response.status_code, 400)

    # --- counts -------------------------------------------------------------

    def test_public_comment_count_only_counts_approved_comments(self):
        from .templatetags.feedback_tags import comment_count

        self.post_comment()
        self.assertEqual(comment_count(self.entry.id), 0)

        Comment.objects.get().approve(self.moderator)
        self.assertEqual(comment_count(self.entry.id), 1)


class ModerationAdminTestCase(TestCase):
    def setUp(self):
        root = Page.objects.get(depth=1)
        self.blog = BlogPage(title='Blog', slug='blog')
        root.add_child(instance=self.blog)
        self.entry = EntryPage(title='A post', slug='a-post', body='<p>hi</p>')
        self.blog.add_child(instance=self.entry)
        self.entry.save_revision().publish()

        self.moderator = User.objects.create_superuser('mod', 'mod@example.com', 'pw')
        self.client.force_login(self.moderator)
        self.comment = Comment.objects.create(
            entry_page_id=self.entry.id, author_name='Ada', body='waiting on you'
        )

    def test_dashboard_shows_the_pending_count(self):
        self.assertContains(self.client.get('/admin/'), '1 comment awaiting approval')

    def test_comment_listing_is_reachable(self):
        response = self.client.get(reverse('comment_views:list'))
        self.assertContains(response, 'waiting on you')

    def test_dashboard_link_filters_the_listing_down_to_pending(self):
        approved = Comment.objects.create(
            entry_page_id=self.entry.id, body='already public', is_approved=True
        )
        response = self.client.get(reverse('comment_views:list'), {'is_approved': 'false'})
        self.assertContains(response, 'waiting on you')
        self.assertNotContains(response, approved.body)

    def bulk_url(self, action):
        return (
            reverse('wagtail_bulk_action', args=['feedback', 'comment', action])
            + f'?id={self.comment.id}'
        )

    def test_bulk_approve(self):
        self.assertContains(
            self.client.get(self.bulk_url('approve')), 'Yes, approve'
        )

        self.client.post(self.bulk_url('approve'))
        self.comment.refresh_from_db()
        self.assertTrue(self.comment.is_approved)
        self.assertEqual(self.comment.moderated_by, self.moderator)

    def test_bulk_unapprove(self):
        self.comment.approve(self.moderator)

        self.assertContains(
            self.client.get(self.bulk_url('unapprove')), "Yes, unapprove"
        )
        self.client.post(self.bulk_url('unapprove'))
        self.comment.refresh_from_db()
        self.assertFalse(self.comment.is_approved)
