"""Admin-only views. The render trigger is POST + CSRF and permissioned, because
it is a button that costs money."""

from django.contrib.auth.decorators import permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods
from wagtail.admin import messages

from .models import AudioEntryPage
from .narration import queue_render, script_chars, voice_for_page
from .speech import EngineError


@permission_required("devcast.render_narration", raise_exception=True)
@require_http_methods(["GET", "POST"])
def render_narration(request, page_id):
    page = get_object_or_404(AudioEntryPage, pk=page_id)
    segments = page.narration_script()

    if request.method == "POST":
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
            "segment_count": len(segments),
            "char_count": script_chars(segments),
            "voice": voice_for_page(page),
            "voice_is_override": page.voice_id is not None,
        },
    )
