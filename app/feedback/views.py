from django.db.models import Count
from django.http import (
    Http404,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.shortcuts import get_object_or_404, redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from puput.models import EntryPage

from .models import Comment, Reaction, is_moderator

MAX_COMMENT_LENGTH = 4000
MAX_NAME_LENGTH = 80


def _session_key(request):
    """A stable per-browser key, used to identify visitors who are not logged in."""
    if not request.session.session_key:
        request.session.save()
    return request.session.session_key or ''


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _entry_page_or_404(entry_page_id):
    """Feedback is only accepted for entries that are actually published."""
    entry = EntryPage.objects.live().filter(id=entry_page_id).first()
    if entry is None:
        raise Http404('No such entry')
    return entry


def _redirect_back(request, entry, extra=''):
    target = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        target = entry.get_url(request) or '/'
    if extra:
        target = f'{target}{"&" if "?" in target else "?"}{extra}'
    return redirect(f'{target}#comments')


def _reaction_state(entry_page_id, user, session_key):
    counts = dict(
        Reaction.objects.filter(entry_page_id=entry_page_id)
        .values('reaction_type')
        .annotate(c=Count('id'))
        .values_list('reaction_type', 'c')
    )
    mine = Reaction.objects.filter(entry_page_id=entry_page_id)
    if user is not None and user.is_authenticated:
        mine = mine.filter(user=user)
    else:
        mine = mine.filter(user__isnull=True, session_key=session_key)
    return counts, list(mine.values_list('reaction_type', flat=True))


@require_POST
def react(request, entry_page_id):
    _entry_page_or_404(entry_page_id)
    reaction_type = request.POST.get('reaction_type')
    if reaction_type not in dict(Reaction.TYPES):
        return HttpResponseBadRequest()

    user = request.user if request.user.is_authenticated else None
    session_key = '' if user else _session_key(request)

    obj, created = Reaction.objects.get_or_create(
        entry_page_id=entry_page_id,
        user=user,
        session_key=session_key,
        reaction_type=reaction_type,
    )
    if not created:
        obj.delete()

    counts, user_reactions = _reaction_state(entry_page_id, user, session_key)
    return JsonResponse({'counts': counts, 'user_reactions': user_reactions})


@require_POST
def add_comment(request, entry_page_id):
    entry = _entry_page_or_404(entry_page_id)

    # Bots fill in every field they find; humans never see this one.
    if request.POST.get('website', '').strip():
        return _redirect_back(request, entry, 'comment=pending')

    body = request.POST.get('body', '').strip()[:MAX_COMMENT_LENGTH]
    if not body:
        return _redirect_back(request, entry)

    user = request.user if request.user.is_authenticated else None
    moderator = is_moderator(request.user)
    session_key = _session_key(request)

    parent = None
    parent_id = request.POST.get('parent_id', '')
    if parent_id.isdigit() and moderator:
        parent = Comment.objects.filter(
            id=parent_id, entry_page_id=entry_page_id
        ).first()
        if parent is not None and parent.parent_id:
            # Replies stay one level deep.
            parent = parent.parent

    Comment.objects.create(
        entry_page_id=entry_page_id,
        parent=parent,
        user=user,
        author_name='' if user else request.POST.get('author_name', '').strip()[:MAX_NAME_LENGTH],
        author_email='' if user else request.POST.get('author_email', '').strip()[:254],
        session_key=session_key,
        ip_address=_client_ip(request),
        body=body,
        # A moderator's own words go straight up; everything else waits for review.
        is_approved=moderator,
        by_moderator=moderator,
    )
    return _redirect_back(request, entry, 'comment=posted' if moderator else 'comment=pending')


@require_POST
def delete_comment(request, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    entry = _entry_page_or_404(comment.entry_page_id)
    if not comment.can_be_deleted_by(request.user, _session_key(request)):
        return HttpResponseForbidden()
    comment.delete()
    return _redirect_back(request, entry)


@require_POST
def moderate_comment(request, comment_id):
    """Approve or unapprove a comment from the entry page itself."""
    if not is_moderator(request.user):
        return HttpResponseForbidden()

    comment = get_object_or_404(Comment, id=comment_id)
    entry = _entry_page_or_404(comment.entry_page_id)
    action = request.POST.get('action')
    if action == 'approve':
        comment.approve(request.user)
    elif action == 'unapprove':
        comment.unapprove(request.user)
    else:
        return HttpResponseBadRequest()
    return _redirect_back(request, entry)
