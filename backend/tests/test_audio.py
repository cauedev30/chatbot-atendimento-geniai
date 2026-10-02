import pytest

from geniai.audio import AUDIO_FORMATS, audio_seconds, ogg_opus_seconds
from tests.support.ogg import ogg_opus, ogg_page, opus_head


@pytest.mark.parametrize("seconds", [0.5, 61.25, 120, 300])
def test_reads_how_long_an_ogg_opus_audio_is_from_its_last_page(seconds: float) -> None:
    assert ogg_opus_seconds(ogg_opus(seconds)) == pytest.approx(seconds)


def test_takes_the_pre_skip_off_the_duration() -> None:
    assert ogg_opus_seconds(ogg_opus(10, pre_skip=4800)) == pytest.approx(10)


def test_reads_only_the_opus_stream_of_the_file() -> None:
    other = ogg_page(b"x" * 20, granule=999_999_999, serial=8, sequence=5)
    assert ogg_opus_seconds(ogg_opus(30) + other) == pytest.approx(30)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"ID3\x03" + bytes(200),
        ogg_page(b"OpusTags" + bytes(8), granule=0),
        ogg_page(b"\x01vorbis" + bytes(30), granule=0) + ogg_page(b"x" * 10, granule=48_000),
        ogg_opus(30)[:-50],
        ogg_opus(30) + b"junk",
        ogg_page(opus_head(), granule=0),
    ],
    ids=["empty", "mp3", "no-head", "vorbis", "truncated", "trailing-junk", "no-audio-page"],
)
def test_has_no_duration_for_anything_but_a_well_formed_ogg_opus_stream(data: bytes) -> None:
    assert ogg_opus_seconds(data) is None


def test_reads_the_duration_only_of_ogg_content_types() -> None:
    data = ogg_opus(42)
    assert audio_seconds(data, "audio/ogg") == pytest.approx(42)
    assert audio_seconds(data, "audio/opus") == pytest.approx(42)
    assert audio_seconds(data, "audio/mpeg") is None


def test_names_each_format_by_an_extension_the_transcription_api_accepts() -> None:
    assert set(AUDIO_FORMATS.values()) <= {"flac", "mp3", "mp4", "mpeg", "mpga", "m4a", "ogg", "wav", "webm"}
    assert AUDIO_FORMATS["audio/ogg"] == "ogg"
