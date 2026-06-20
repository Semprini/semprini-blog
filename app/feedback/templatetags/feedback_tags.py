from django import template
from django.db.models import Count
from django.middleware.csrf import get_token

from ..models import Comment, Reaction

register = template.Library()


@register.inclusion_tag('feedback/panel.html', takes_context=True)
def show_feedback(context, entry_page_id):
    request = context.get('request')
    user = getattr(request, 'user', None)

    counts = dict(
        Reaction.objects.filter(entry_page_id=entry_page_id)
        .values('reaction_type')
        .annotate(c=Count('id'))
        .values_list('reaction_type', 'c')
    )

    user_reactions = set()
    if user and user.is_authenticated:
        user_reactions = set(
            Reaction.objects.filter(entry_page_id=entry_page_id, user=user)
            .values_list('reaction_type', flat=True)
        )

    reactions = [
        {
            'type': rtype,
            'emoji': emoji,
            'count': counts.get(rtype, 0),
            'active': rtype in user_reactions,
        }
        for rtype, emoji in Reaction.TYPES
    ]

    comments = list(
        Comment.objects.filter(entry_page_id=entry_page_id).select_related('user')
    )

    return {
        'entry_page_id': entry_page_id,
        'reactions': reactions,
        'comments': comments,
        'user': user,
        'request': request,
        'csrf_token': get_token(request) if request else '',
    }


@register.simple_tag
def comment_count(entry_page_id):
    return Comment.objects.filter(entry_page_id=entry_page_id).count()
