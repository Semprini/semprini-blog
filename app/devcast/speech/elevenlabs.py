"""ElevenLabs, via the ``with-timestamps`` endpoint.

The timestamps are the reason this is the phase-3 engine: character-level
alignment collapses into word timings, which is what makes word-level
highlighting and a precomputed viseme track possible without forced alignment.
"""

import base64
import os
import re

import requests

from .base import Clip, EngineError, truncate_error

# Provider ids go into a URL path, so they are checked rather than trusted:
# they come from editable model data.
VOICE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def words_from_alignment(alignment):
    """Character timings -> ``[[start, end, word], ...]``."""
    if not alignment:
        return []
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if not (len(chars) == len(starts) == len(ends)):
        return []

    words = []
    current, start, end = "", None, None
    for char, char_start, char_end in zip(chars, starts, ends):
        if char.isspace():
            if current:
                words.append([round(start, 3), round(end, 3), current])
                current, start, end = "", None, None
            continue
        if not current:
            start = char_start
        current += char
        end = char_end
    if current:
        words.append([round(start, 3), round(end, 3), current])
    return words


class ElevenLabsEngine:
    name = "elevenlabs"
    model_id = "eleven_multilingual_v2"
    base_url = "https://api.elevenlabs.io"
    output_format = "mp3_44100_128"
    mime = "audio/mpeg"
    timeout = 180
    # eleven_multilingual_v2 accepts 10,000 characters per request.
    text_limit = 10000
    context_chars = 500

    def __init__(self, api_key=None, model_id=None, base_url=None):
        self.api_key = api_key or os.environ.get("ELEVEN_LABS_API_KEY", "")
        if not self.api_key:
            raise EngineError("ELEVEN_LABS_API_KEY is not set")
        self.model_id = model_id or self.model_id
        self.base_url = (base_url or self.base_url).rstrip("/")

    @property
    def revision(self):
        return self.model_id

    def synthesize(self, text, voice, previous_text="", next_text=""):
        voice_id = (voice.engine_voice_id or "").strip()
        if not VOICE_ID.match(voice_id):
            raise EngineError(f"Voice {voice.key!r} has an invalid engine voice id")

        payload = {"text": text, "model_id": self.model_id}
        if voice.engine_settings:
            payload["voice_settings"] = voice.engine_settings
        # The surrounding text is not spoken; it only tells the model where this
        # clip sits, so the seams between stitched clips stop sounding like cuts.
        if previous_text:
            payload["previous_text"] = previous_text[-self.context_chars :]
        if next_text:
            payload["next_text"] = next_text[: self.context_chars]

        try:
            response = requests.post(
                f"{self.base_url}/v1/text-to-speech/{voice_id}/with-timestamps",
                params={"output_format": self.output_format},
                json=payload,
                headers={"xi-api-key": self.api_key, "accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise EngineError(f"ElevenLabs request failed: {type(exc).__name__}") from None

        if response.status_code != 200:
            # The body is provider-controlled and may echo the request back, so
            # it is truncated before it ever reaches the database.
            raise EngineError(
                f"ElevenLabs returned {response.status_code}: {truncate_error(response.text)}"
            )

        try:
            data = response.json()
            audio = base64.b64decode(data["audio_base64"])
        except (ValueError, KeyError, TypeError):
            raise EngineError("ElevenLabs returned an unreadable response") from None

        words = words_from_alignment(
            data.get("alignment") or data.get("normalized_alignment")
        )
        duration = words[-1][1] if words else None
        return Clip(audio=audio, mime=self.mime, duration_s=duration, words=words)
