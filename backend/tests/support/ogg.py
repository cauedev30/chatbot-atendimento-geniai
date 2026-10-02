"""Ogg Opus files built in memory for the tests: pages with the right layout, no real audio."""

OPUS_RATE = 48_000


def ogg_page(payload: bytes, *, granule: int, serial: int = 7, sequence: int = 0, header_type: int = 0) -> bytes:
    lacing = [255] * (len(payload) // 255) + [len(payload) % 255]
    header = b"OggS" + bytes([0, header_type]) + granule.to_bytes(8, "little", signed=True)
    header += serial.to_bytes(4, "little") + sequence.to_bytes(4, "little") + bytes(4)
    return header + bytes([len(lacing)]) + bytes(lacing) + payload


def opus_head(pre_skip: int = 312) -> bytes:
    return b"OpusHead" + bytes([1, 1]) + pre_skip.to_bytes(2, "little") + OPUS_RATE.to_bytes(4, "little") + bytes(3)


def ogg_opus(seconds: float, *, pre_skip: int = 312, audio_pages: int = 3) -> bytes:
    """An Ogg Opus stream lasting `seconds`: the head and tags pages, then audio pages up to that granule
    position; a page where no packet ends (granule -1) sits before the last one."""
    total = round(seconds * OPUS_RATE) + pre_skip
    pages = [
        ogg_page(opus_head(pre_skip), granule=0, header_type=2),
        ogg_page(b"OpusTags" + bytes(8), granule=0, sequence=1),
    ]
    for n in range(1, audio_pages + 1):
        pages.append(ogg_page(b"\xfc" * 300, granule=total * n // audio_pages, sequence=n + 1))
    pages.insert(-1, ogg_page(b"\xfc" * 10, granule=-1, sequence=99))
    return b"".join(pages)
