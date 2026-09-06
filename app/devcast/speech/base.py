"""The contract every speech engine implements."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Provider error bodies can be long and can echo back the request; they are
# stored on the rendition for the editor to read, so they get truncated first.
MAX_ERROR_CHARS = 500


class EngineError(RuntimeError):
    """Anything that stops a synthesis: bad config, provider failure, refusal."""


@dataclass(frozen=True)
class Segment:
    """One narratable unit of a page. ``block_id`` is the StreamField child's
    UUID, which is the join key between HTML, script and cue track."""

    block_id: str
    kind: str
    text: str


@dataclass
class Clip:
    """Audio for a single segment."""

    audio: bytes
    mime: str = "audio/mpeg"
    duration_s: float | None = None
    words: list = field(default_factory=list)


@runtime_checkable
class SpeechEngine(Protocol):
    name: str
    revision: str

    def synthesize(
        self, text: str, voice, previous_text: str = "", next_text: str = ""
    ) -> Clip: ...


def truncate_error(text) -> str:
    text = " ".join(str(text or "").split())
    return text[:MAX_ERROR_CHARS]
