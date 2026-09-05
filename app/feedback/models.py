from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _

User = get_user_model()


def is_moderator(user):
    """Moderators are superusers plus anyone a group grants comment edit rights to."""
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.has_perm('feedback.change_comment'))
    )


class Reaction(models.Model):
    TYPES = [
        ('upvote',    '👍'),
        ('funny',     '😄'),
        ('love',      '❤️'),
        ('surprised', '😮'),
        ('angry',     '😠'),
        ('sad',       '😢'),
    ]
    entry_page_id = models.IntegerField(db_index=True)
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name='reactions'
    )
    # Identifies an anonymous reactor so they can toggle their own reaction back off.
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    reaction_type = models.CharField(max_length=20, choices=TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # NULL user columns never collide in Postgres, so the two cases need
            # separate partial constraints rather than one unique_together.
            models.UniqueConstraint(
                fields=['entry_page_id', 'user', 'reaction_type'],
                condition=Q(user__isnull=False),
                name='feedback_reaction_unique_per_user',
            ),
            models.UniqueConstraint(
                fields=['entry_page_id', 'session_key', 'reaction_type'],
                condition=Q(user__isnull=True),
                name='feedback_reaction_unique_per_session',
            ),
        ]


class CommentQuerySet(models.QuerySet):
    def approved(self):
        return self.filter(is_approved=True)

    def pending(self):
        return self.filter(is_approved=False)

    def owned_by(self, user=None, session_key=''):
        """Comments the given visitor posted, by account or by browser session."""
        query = Q(pk__in=[])
        if user is not None and user.is_authenticated:
            query |= Q(user=user)
        if session_key:
            query |= Q(user__isnull=True, session_key=session_key)
        return self.filter(query)


class Comment(models.Model):
    entry_page_id = models.IntegerField(db_index=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.CASCADE, related_name='replies'
    )
    user = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.CASCADE, related_name='blog_comments'
    )
    author_name = models.CharField(
        _('name'), max_length=80, blank=True,
        help_text=_('Name supplied by a visitor who was not logged in.'),
    )
    author_email = models.EmailField(
        _('email'), blank=True,
        help_text=_('Never published; for the moderator only.'),
    )
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    body = models.TextField()
    is_approved = models.BooleanField(_('approved'), default=False, db_index=True)
    by_moderator = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderated_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='moderated_comments',
    )

    objects = CommentQuerySet.as_manager()

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.display_name}: {self.body[:60]}'

    @cached_property
    def entry_page(self):
        from puput.models import EntryPage

        return EntryPage.objects.filter(id=self.entry_page_id).first()

    @property
    def entry_title(self):
        entry = self.entry_page
        return entry.title if entry else f'#{self.entry_page_id}'

    @property
    def display_name(self):
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        return self.author_name or _('Anonymous')

    def approve(self, moderator=None):
        self.is_approved = True
        self.moderated_at = timezone.now()
        self.moderated_by = moderator if moderator and moderator.is_authenticated else None
        self.save(update_fields=['is_approved', 'moderated_at', 'moderated_by'])

    def unapprove(self, moderator=None):
        self.is_approved = False
        self.moderated_at = timezone.now()
        self.moderated_by = moderator if moderator and moderator.is_authenticated else None
        self.save(update_fields=['is_approved', 'moderated_at', 'moderated_by'])

    def can_be_deleted_by(self, user=None, session_key=''):
        if is_moderator(user):
            return True
        if self.user_id and user is not None and user.is_authenticated:
            return self.user_id == user.pk
        return bool(session_key) and not self.user_id and self.session_key == session_key
