"""The audio formats the bot transcribes, and how long an audio is, read from the file without a library."""

from collections.abc import Mapping
from typing import Final

AUDIO_FORMATS: Final[Mapping[str, str]] = {
    "audio/ogg": "ogg",
    "audio/opus": "ogg",
    "application/ogg": "ogg",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/webm": "webm",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
}
"""The content types Chatwoot serves for the formats the transcription API accepts, each with the file
extension the API recognizes the format by. A WhatsApp voice message is audio/ogg (Opus)."""

OPUS_RATE: Final = 48_000
"""Opus granule positions count samples at 48 kHz, whatever the input rate (RFC 7845)."""

_PAGE_HEADER: Final = 27
_NO_PACKET_ENDS: Final = -1


def ogg_opus_seconds(data: bytes) -> float | None:
    """How long an Ogg Opus audio lasts: the granule position of the last page of its stream, minus the
    pre-skip of its head, over 48 000. None when the data is not a whole, well-formed Ogg Opus stream."""
    pos, serial, pre_skip, last = 0, -1, 0, None
    while pos + _PAGE_HEADER <= len(data):
        if data[pos : pos + 4] != b"OggS":
            return None
        segments = data[pos + 26]
        body_start = pos + _PAGE_HEADER + segments
        body_end = body_start + sum(data[pos + _PAGE_HEADER : body_start])
        if body_end > len(data):
            return None
        granule = int.from_bytes(data[pos + 6 : pos + 14], "little", signed=True)
        page_serial = int.from_bytes(data[pos + 14 : pos + 18], "little")
        if serial == -1:
            head = data[body_start:body_end]
            if not head.startswith(b"OpusHead") or len(head) < 12:
                return None
            serial, pre_skip = page_serial, int.from_bytes(head[10:12], "little")
        elif page_serial == serial and granule != _NO_PACKET_ENDS:
            last = granule
        pos = body_end
    if pos != len(data) or last is None:
        return None
    return max(0, last - pre_skip) / OPUS_RATE


def audio_seconds(data: bytes, content_type: str) -> float | None:
    """The duration of an Ogg audio; None for the other formats, whose duration is not read."""
    return ogg_opus_seconds(data) if AUDIO_FORMATS.get(content_type) == "ogg" else None
