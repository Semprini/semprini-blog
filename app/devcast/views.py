"""Admin-only views. The render trigger is POST + CSRF and permissioned, because
it is a button that costs money."""

from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from wagtail.admin import messages

from .models import AudioEntryPage
from .narration import (
    forget_clips,
    narration_state,
    queue_render,
    render_plan,
    voice_for_page,
)
from .speech import EngineError


@permission_required("devcast.render_narration", raise_exception=True)
@require_http_methods(["GET", "POST"])
def render_narration(request, page_id):
    page = get_object_or_404(AudioEntryPage, pk=page_id)
    voice = voice_for_page(page)

    if request.method == "POST":
        # Opt-in, because it throws away audio that has already been paid for.
        if request.POST.get("rerecord"):
            forget_clips(page, voice=voice)
        try:
            rendition = queue_render(page, force=True)
        except EngineError as exc:
            messages.error(request, _("Narration not queued: %s") % exc)
        else:
            if rendition is None:
                messages.warning(
                    request,
                    _("Nothing to narrate. Check that narration is enabled and a voice exists."),
                )
            else:
                messages.success(request, _("Narration queued for '%s'.") % page.title)
        return redirect("wagtailadmin_pages:edit", page.pk)

    return render(
        request,
        "devcast/admin/confirm_render.html",
        {
            "page": page,
            "state": narration_state(page),
            "plan": render_plan(page, voice=voice),
            "voice": voice,
            "voice_is_override": page.voice_id is not None,
        },
    )
