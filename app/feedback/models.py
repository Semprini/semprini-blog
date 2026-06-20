from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


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
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reactions')
    reaction_type = models.CharField(max_length=20, choices=TYPES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('entry_page_id', 'user', 'reaction_type')


class Comment(models.Model):
    entry_page_id = models.IntegerField(db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blog_comments')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
