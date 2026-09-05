from django import template
from django.db.models import Count
from django.middleware.csrf import get_token

from ..models import Comment, Reaction, is_moderator

register = template.Library()


@register.inclusion_tag('feedback/panel.html', takes_context=True)
def show_feedback(context, entry_page_id):
    request = context.get('request')
    user = getattr(request, 'user', None)
    moderator = is_moderator(user)
    session_key = request.session.session_key or '' if request is not None else ''

    counts = dict(
        Reaction.objects.filter(entry_page_id=entry_page_id)
        .values('reaction_type')
        .annotate(c=Count('id'))
        .values_list('reaction_type', 'c')
    )

    my_reactions = Reaction.objects.filter(entry_page_id=entry_page_id)
    if user is not None and user.is_authenticated:
        my_reactions = my_reactions.filter(user=user)
    elif session_key:
        my_reactions = my_reactions.filter(user__isnull=True, session_key=session_key)
    else:
        my_reactions = my_reactions.none()
    user_reactions = set(my_reactions.values_list('reaction_type', flat=True))

    reactions = [
        {
            'type': rtype,
            'emoji': emoji,
            'count': counts.get(rtype, 0),
            'active': rtype in user_reactions,
        }
        for rtype, emoji in Reaction.TYPES
    ]

    entry_comments = Comment.objects.filter(entry_page_id=entry_page_id).select_related('user')
    if moderator:
        visible = entry_comments
    else:
        # Everyone sees approved comments; you also see your own while it waits.
        visible = entry_comments.approved() | entry_comments.owned_by(user, session_key)
    visible = list(visible.distinct())

    replies = {}
    for comment in visible:
        comment.can_delete = comment.can_be_deleted_by(user, session_key)
        if comment.parent_id:
            replies.setdefault(comment.parent_id, []).append(comment)

    threads = []
    for comment in visible:
        if comment.parent_id:
            continue
        comment.visible_replies = replies.get(comment.id, [])
        threads.append(comment)

    return {
        'entry_page_id': entry_page_id,
        'reactions': reactions,
        'threads': threads,
        'approved_total': sum(1 for c in visible if c.is_approved),
        'pending_total': sum(1 for c in visible if not c.is_approved),
        'user': user,
        'is_moderator': moderator,
        'request': request,
        'comment_state': request.GET.get('comment', '') if request else '',
        'csrf_token': get_token(request) if request else '',
    }


@register.simple_tag
def comment_count(entry_page_id):
    return Comment.objects.filter(entry_page_id=entry_page_id).approved().count()
