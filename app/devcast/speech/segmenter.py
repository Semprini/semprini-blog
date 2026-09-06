"""Segmented rendering: one clip per script segment, measured, then joined.

Cue boundaries fall out of the measured clip durations, so they are exact by
construction and work with any engine — including future local models that
expose no timing API at all.
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .. import conf
from .base import EngineError

FFMPEG_TIMEOUT = 600


@dataclass
class Rendered:
    audio: bytes
    duration_s: float
    cues: list
    words: list


def _run(args):
    """ffmpeg/ffprobe are invoked with an explicit argument list — never a shell
    string — on files this process wrote itself."""
    try:
        return subprocess.run(
            args, capture_output=True, check=True, timeout=FFMPEG_TIMEOUT
        )
    except FileNotFoundError:
        raise EngineError(f"{args[0]} is not installed") from None
    except subprocess.TimeoutExpired:
        raise EngineError(f"{args[0]} timed out") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise EngineError(f"{args[0]} failed: {detail[-1] if detail else exc.returncode}") from None


def probe_duration(path):
    result = _run(
        [
            conf.ffprobe(), "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json", str(path),
        ]
    )
    try:
        return float(json.loads(result.stdout)["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise EngineError("ffprobe reported no duration") from None


def _silence(path, seconds):
    _run(
        [
            conf.ffmpeg(), "-v", "error", "-y",
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
            "-t", f"{seconds:.3f}", "-c:a", "libmp3lame", "-b:a", "128k",
            str(path),
        ]
    )


def render(segments, clips):
    """Join per-segment clips into one file and time the cues against it.

    ``segments`` and ``clips`` are parallel: a clip may cover several segments
    only if the caller has already merged them.
    """
    if len(segments) != len(clips):
        raise EngineError("segment/clip mismatch")
    if not clips:
        raise EngineError("nothing to render")

    gap = max(0, conf.segment_gap_ms()) / 1000

    with tempfile.TemporaryDirectory(prefix="devcast-") as tmp:
        tmpdir = Path(tmp)
        parts, cues, words = [], [], []
        at = 0.0

        gap_file = tmpdir / "gap.mp3"
        if gap:
            _silence(gap_file, gap)

        for index, (segment, clip) in enumerate(zip(segments, clips)):
            part = tmpdir / f"{index:04d}.mp3"
            part.write_bytes(clip.audio)
            # Trust the file, not the provider: a clip's own report can exclude
            # leading silence, and drift compounds over a long article.
            duration = probe_duration(part)

            for start, end, word in clip.words:
                words.append([round(at + start, 3), round(at + end, 3), word])

            cues.append(
                {
                    "id": segment.block_id,
                    "kind": segment.kind,
                    "start": round(at, 3),
                    "end": round(at + duration, 3),
                }
            )
            parts.append(part)
            at += duration
            if gap and index < len(clips) - 1:
                parts.append(gap_file)
                at += gap

        listing = tmpdir / "parts.txt"
        listing.write_text("".join(f"file '{part.name}'\n" for part in parts))

        output = tmpdir / "narration.mp3"
        _run(
            [
                conf.ffmpeg(), "-v", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", str(listing),
                "-c:a", "libmp3lame", "-b:a", "128k", "-ar", "44100", "-ac", "1",
                str(output),
            ]
        )

        total = probe_duration(output)
        if cues:
            cues[-1]["end"] = round(max(cues[-1]["end"], total), 3)
        return Rendered(
            audio=output.read_bytes(), duration_s=total, cues=cues, words=words
        )
