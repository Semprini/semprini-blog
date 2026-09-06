"""Speech synthesis behind one small interface.

Nothing outside this package knows which provider is in use: engines are named
in ``DEVCAST_ENGINES`` and resolved by name, so swapping a hosted provider for a
local voice-clone sidecar is a settings change.
"""

from django.utils.module_loading import import_string

from .. import conf
from .base import Clip, EngineError, Segment, SpeechEngine

__all__ = ["Clip", "EngineError", "Segment", "SpeechEngine", "get_engine"]


def get_engine(name=None, **kwargs):
    """Instantiate the named engine. Raises ``EngineError`` if it is unknown or
    unusable (a missing API key is a configuration error, not a runtime one)."""
    name = name or conf.default_engine()
    try:
        path = conf.engines()[name]
    except KeyError:
        raise EngineError(f"Unknown speech engine {name!r}") from None
    return import_string(path)(**kwargs)
