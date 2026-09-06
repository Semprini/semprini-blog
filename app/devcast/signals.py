"""Publishing is the only thing that spends money.

Draft autosave deliberately does not trigger a render: an author saving every
few seconds would otherwise queue a dozen jobs for one paragraph.
"""

import logging

from django.db import transaction
from wagtail.signals import page_published

logger = logging.getLogger(__name__)


def queue_narration(sender, instance, **kwargs):
    from .models import AudioEntryPage
    from .narration import queue_render
    from .speech import EngineError

    if not isinstance(instance, AudioEntryPage):
        return

    def run():
        try:
            queue_render(instance)
        except EngineError as exc:
            # A publish must never fail because narration cannot be queued.
            logger.warning("devcast: narration not queued for %s: %s", instance.pk, exc)

    transaction.on_commit(run)


def register():
    page_published.connect(queue_narration, dispatch_uid="devcast.queue_narration")
