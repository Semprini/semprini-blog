from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Comment, Reaction


@login_required
@require_POST
def react(request, entry_page_id):
    reaction_type = request.POST.get('reaction_type')
    if reaction_type not in dict(Reaction.TYPES):
        return HttpResponseBadRequest()

    obj, created = Reaction.objects.get_or_create(
        entry_page_id=entry_page_id,
        user=request.user,
        reaction_type=reaction_type,
    )
    if not created:
        obj.delete()

    counts = dict(
        Reaction.objects.filter(entry_page_id=entry_page_id)
        .values('reaction_type')
        .annotate(c=Count('id'))
        .values_list('reaction_type', 'c')
    )
    user_reactions = list(
        Reaction.objects.filter(entry_page_id=entry_page_id, user=request.user)
        .values_list('reaction_type', flat=True)
    )
    return JsonResponse({'counts': counts, 'user_reactions': user_reactions})


@login_required
@require_POST
def add_comment(request, entry_page_id):
    body = request.POST.get('body', '').strip()
    if body:
        Comment.objects.create(
            entry_page_id=entry_page_id,
            user=request.user,
            body=body,
        )
    return redirect(request.POST.get('next', '/'))


@require_POST
def delete_comment(request, comment_id):
    if not request.user.is_authenticated:
        return HttpResponseForbidden()
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.user == request.user or request.user.is_staff:
        comment.delete()
    return redirect(request.POST.get('next', '/'))
