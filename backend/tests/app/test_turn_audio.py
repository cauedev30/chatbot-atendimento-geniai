"""Turns with the customer's audios: transcribed at the start of the turn, they count as text for every rule;
too long, not downloaded or not transcribed, they follow the media rule."""

import asyncio
import itertools
from collections.abc import Callable

import pytest
from sqlalchemy import select

from geniai.app.ports import AudioData, FetchFailure, TranscribeFailure
from geniai.app.process_turn import process_turn
from geniai.db.schema import outbox
from geniai.domain.texts import TEXT
from geniai.domain.types import Attachment, AttachmentKind, UnreadMedia
from tests.app.test_process_turn import Chat
from tests.app.test_turn_images import history, payload, stored_attachments
from tests.conftest import Harness
from tests.support.fakes import Sent, turn_json

_links = itertools.count(1)


@pytest.fixture
def chat(h: Harness) -> Chat:
    h.transcribes()
    return Chat(h)


def voice(
    h: Harness,
    said: str | TranscribeFailure,
    *,
    seconds: float | None = 10.0,
    content_type: str = "audio/ogg",
    size: int = 0,
    opens: bool = True,
) -> Attachment:
    """An audio on the fictitious Chatwoot; FakeMedia serves it when it opens and FakeTranscriber hears `said`."""
    url = f"https://chatwoot.example/rails/active_storage/blobs/redirect/{next(_links)}/audio.oga"
    data = f"audio {url}".encode().ljust(size, b"\x00")
    h.media.audios[url] = AudioData(data, content_type, seconds) if opens else FetchFailure("status")
    h.transcriber.texts[data] = said
    return Attachment("audio", url)


def heard(said: str) -> str:
    return f'[áudio transcrito: "{said}"]'


def logs(h: Harness, msg: str) -> list[dict[str, object]]:
    return [e.obj for e in h.logger.infos if e.msg == msg]


async def test_an_audio_reaches_the_llm_as_what_the_customer_said_and_is_transcribed_once(
    h: Harness, chat: Chat
) -> None:
    conversation_id = await chat.greeted()
    audio = voice(h, "o painel não abre desde ontem")
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    assert await chat.customer(conversation_id, "", audio) == "ask_clarification"
    assert payload(h)["new_messages"] == [heard("o painel não abre desde ontem")]
    [_, stored] = await stored_attachments(h, conversation_id)
    assert stored == (Attachment("audio", audio.url, "transcribed", transcript="o painel não abre desde ontem"),)
    assert (await chat.ticket_of(conversation_id)).media_prompts == 0

    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Em qual tela?"))
    await chat.customer(conversation_id, "aparece tela branca")
    assert heard("o painel não abre desde ontem") in history(h)
    assert (h.media.fetched, len(h.transcriber.heard)) == ([audio.url], 1)


async def test_an_audio_with_a_caption_goes_with_its_caption(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual?"))
    await chat.customer(conversation_id, "olha", voice(h, "deu erro no login"))
    assert payload(h)["new_messages"] == [f"{heard('deu erro no login')} olha"]


async def test_a_first_audio_with_the_problem_only_asks_to_confirm_and_is_used_after_the_confirmation(
    h: Harness, chat: Chat
) -> None:
    conversation_id = 700
    assert await chat.customer(conversation_id, "", voice(h, "esqueci a senha do painel")) == "greeting"
    assert chat.last_sent() == TEXT.greeting_with_content("Ana Exemplo", "Unidade Exemplo Centro")
    assert h.llm.requests == []
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"]))
    assert await chat.customer(conversation_id, "sim, sou eu") == "send_faq"
    assert history(h)[0] == heard("esqueci a senha do painel")
    assert payload(h)["new_messages"] == ["sim, sou eu"]


async def test_a_first_audio_that_is_only_a_greeting_asks_for_the_problem(h: Harness, chat: Chat) -> None:
    assert await chat.customer(701, "", voice(h, "Bom dia!")) == "greeting"
    assert chat.last_sent() == TEXT.greeting("Ana Exemplo", "Unidade Exemplo Centro")


@pytest.mark.parametrize("first", [True, False], ids=["first-message", "mid-conversation"])
async def test_an_audio_asking_for_an_attendant_hands_over_before_the_llm_and_reaches_the_card_summary(
    h: Harness, chat: Chat, first: bool
) -> None:
    conversation_id = 702 if first else await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["other"], summary="Pede para falar com um atendente."))
    assert await chat.customer(conversation_id, "", voice(h, "quero falar com um atendente")) == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.summary) == ("human_requested", "Pede para falar com um atendente.")
    assert len(h.llm.requests) == 1
    assert payload(h)["new_messages"] == [heard("quero falar com um atendente")]


async def test_the_card_summary_without_the_llm_has_what_the_audio_said(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(RuntimeError("down"), RuntimeError("down"))
    assert await chat.customer(conversation_id, "", voice(h, "quero falar com um atendente")) == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert t.summary == f"oi / {heard('quero falar com um atendente')}"


async def test_an_audio_longer_than_two_minutes_asks_for_text_once_then_hands_over(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    assert await chat.customer(conversation_id, "", voice(h, "x", seconds=120.5)) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_audio_too_long
    assert h.transcriber.heard == []
    [_, [stored]] = await stored_attachments(h, conversation_id)
    assert (stored.outcome, stored.transcript) == ("too_long", None)
    assert await chat.customer(conversation_id, "", voice(h, "x", seconds=600)) == "handoff"
    assert (await chat.ticket_of(conversation_id)).handoff_reason == "media"


async def test_an_audio_of_exactly_two_minutes_is_transcribed(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual?"))
    assert await chat.customer(conversation_id, "", voice(h, "o painel caiu", seconds=120)) == "ask_clarification"


async def test_an_audio_whose_duration_is_not_read_is_too_long_past_the_size_ceiling(h: Harness, chat: Chat) -> None:
    h.with_rules(max_untimed_audio_bytes=200)
    conversation_id = await chat.greeted()
    big = voice(h, "x", seconds=None, content_type="audio/mpeg", size=201)
    assert await chat.customer(conversation_id, "", big) == "ask_for_text"
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual?"))
    fits = voice(h, "o painel caiu", seconds=None, content_type="audio/mpeg", size=200)
    assert await chat.customer(conversation_id, "", fits) == "ask_clarification"
    assert payload(h)["new_messages"] == [heard("o painel caiu")]


@pytest.mark.parametrize(
    ("said", "opens", "line"),
    [
        ("o painel caiu", False, "audio not read"),
        (TranscribeFailure("timeout"), True, "audio not transcribed"),
        ("  \n ", True, "audio not transcribed"),
    ],
    ids=["not-downloaded", "transcription-failed", "empty-text"],
)
async def test_an_audio_not_heard_follows_the_media_rule_and_is_named_for_the_llm(
    h: Harness, chat: Chat, said: str | TranscribeFailure, opens: bool, line: str
) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    assert await chat.customer(conversation_id, "", voice(h, said, opens=opens)) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_audio_failed
    assert logs(h, line)
    [_, [stored]] = await stored_attachments(h, conversation_id)
    assert stored.outcome == "failed"
    h.llm.push(turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Qual?"))
    await chat.customer(conversation_id, "é sobre o painel")
    assert history(h)[-2:] == ["[áudio — o bot não ouve]", TEXT.ask_for_text_audio_failed]
    assert len(h.transcriber.heard) == (1 if opens else 0)


async def test_an_audio_too_long_beside_one_not_transcribed_asks_for_a_shorter_one(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    await chat.receive(conversation_id, "", voice(h, TranscribeFailure("error")))
    assert await chat.customer(conversation_id, "", voice(h, "x", seconds=180)) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_audio_too_long


@pytest.mark.parametrize(
    ("reads_images", "kinds", "expected"),
    [
        (True, ("audio", "video"), "video_or_file"),
        (True, ("audio", "file"), "video_or_file"),
        (True, ("audio", "image"), "image"),
        (True, ("video",), "video_or_file"),
        (False, ("audio", "video"), "image_or_file"),
        (False, ("audio", "image"), "image_or_file"),
        (False, ("image",), "image_or_file"),
    ],
)
async def test_with_transcription_on_the_request_for_text_leaves_the_audio_out_beside_other_attachments(
    h: Harness, chat: Chat, reads_images: bool, kinds: tuple[AttachmentKind, ...], expected: UnreadMedia
) -> None:
    if reads_images:
        h.reads_images()
    conversation_id = await chat.greeted()
    attachments = [
        voice(h, TranscribeFailure("error")) if kind == "audio" else Attachment(kind, "https://chatwoot.example/x")
        for kind in kinds
    ]
    assert await chat.customer(conversation_id, "", *attachments) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_for(expected)
    assert "ouvir áudios" not in chat.last_sent()


async def test_audios_of_one_turn_are_transcribed_together_and_named_in_order(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    await chat.receive(conversation_id, "", voice(h, "primeiro"))
    await chat.receive(conversation_id, "e mais", voice(h, "segundo"), voice(h, "terceiro"))
    h.llm.push(turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Qual?"))
    assert await chat.customer(conversation_id, "fim") == "ask_clarification"
    assert payload(h)["new_messages"] == [
        heard("primeiro"),
        f"{heard('segundo')} {heard('terceiro')} e mais",
        "fim",
    ]
    assert [n.text for n in h.chatwoot.notes] == [
        "Transcrição do áudio (bot): primeiro",
        "Transcrição do áudio (bot): segundo",
        "Transcrição do áudio (bot): terceiro",
    ]


async def test_keeps_a_transcription_on_one_line_and_up_to_3000_characters(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Qual?"))
    await chat.customer(conversation_id, "", voice(h, "linha um\n\nlinha  dois " + "a" * 4000))
    [_, [stored]] = await stored_attachments(h, conversation_id)
    assert stored.transcript is not None
    assert (len(stored.transcript), stored.transcript[:20]) == (3000, "linha um linha dois ")
    assert stored.transcript.endswith("…")


async def test_each_transcription_goes_to_the_team_as_a_private_note(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    await chat.customer(conversation_id, "", voice(h, "o painel não abre"))
    assert h.chatwoot.notes == [Sent(conversation_id, "Transcrição do áudio (bot): o painel não abre")]
    assert all("Transcrição" not in s.text for s in h.chatwoot.sent)


async def until(check: Callable[[], object]) -> None:
    for _ in range(500):
        if check():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("still waiting after 5 s")


async def queued_messages(h: Harness, conversation_id: int) -> list[str]:
    async with h.begin() as conn:
        query = select(outbox.c.payload).where(outbox.c.conversation_id == conversation_id, outbox.c.kind == "message")
        return list((await conn.execute(query)).scalars())


async def test_the_note_goes_out_while_the_llm_reads_the_turn_and_before_the_reply(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.chatwoot.hold_notes = asyncio.Event()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    await chat.receive(conversation_id, "", voice(h, "o painel não abre"))
    turn = asyncio.create_task(process_turn(h.deps, conversation_id))
    await until(lambda: h.llm.requests)
    await asyncio.sleep(0.05)
    assert (turn.done(), h.chatwoot.notes) == (False, [])
    assert "Qual erro?" not in await queued_messages(h, conversation_id)
    h.chatwoot.hold_notes.set()
    assert await turn == "ask_clarification"
    await h.settle()
    assert h.chatwoot.notes == [Sent(conversation_id, "Transcrição do áudio (bot): o painel não abre")]
    assert chat.last_sent() == "Qual erro?"


async def test_the_greeting_waits_for_the_note_of_a_first_audio(h: Harness, chat: Chat) -> None:
    conversation_id = 703
    h.chatwoot.hold_notes = asyncio.Event()
    await chat.receive(conversation_id, "", voice(h, "esqueci a senha do painel"))
    turn = asyncio.create_task(process_turn(h.deps, conversation_id))
    await until(lambda: h.transcriber.heard)
    await asyncio.sleep(0.05)
    assert (turn.done(), await queued_messages(h, conversation_id)) == (False, [])
    h.chatwoot.hold_notes.set()
    assert await turn == "greeting"
    assert len(h.chatwoot.notes) == 1


async def test_a_note_that_fails_does_not_stop_the_turn(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.chatwoot.fail_notes = True
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    assert await chat.customer(conversation_id, "", voice(h, "o painel não abre")) == "ask_clarification"
    assert chat.last_sent() == "Qual erro?"
    [line] = [e for e in h.logger.errors if e.msg == "transcript note failed"]
    assert line.obj["ticketId"] == (await chat.ticket_of(conversation_id)).id


async def test_logs_each_audio_by_type_size_and_duration_never_its_link_nor_what_was_said(
    h: Harness, chat: Chat
) -> None:
    conversation_id = await chat.greeted()
    audio = voice(h, "meu número é segredo", seconds=12.345)
    h.llm.push(turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Qual?"))
    await chat.customer(conversation_id, "", audio)
    ticket_id = (await chat.ticket_of(conversation_id)).id
    size = len(f"audio {audio.url}".encode())
    assert logs(h, "audio read") == [{"ticketId": ticket_id, "contentType": "audio/ogg", "size": size, "seconds": 12.3}]
    [transcribed] = logs(h, "audio transcribed")
    assert (transcribed["ticketId"], transcribed["seconds"], type(transcribed["ms"])) == (ticket_id, 12.3, int)
    everything = repr([h.logger.infos, h.logger.warnings, h.logger.errors])
    assert "segredo" not in everything
    assert str(audio.url) not in everything


async def test_logs_why_an_audio_was_not_transcribed(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    await chat.customer(conversation_id, "", voice(h, TranscribeFailure("status", 401)))
    await chat.customer(conversation_id, "", voice(h, "x", seconds=200))
    ticket_id = (await chat.ticket_of(conversation_id)).id
    failed, too_long = logs(h, "audio not transcribed")
    assert {k: failed[k] for k in ("ticketId", "reason", "status", "seconds")} == {
        "ticketId": ticket_id,
        "reason": "status",
        "status": 401,
        "seconds": 10.0,
    }
    assert too_long == {"ticketId": ticket_id, "reason": "too_long", "seconds": 200.0}


async def test_with_transcription_off_an_audio_is_neither_downloaded_nor_transcribed(h: Harness) -> None:
    chat = Chat(h)
    conversation_id = await chat.greeted()
    assert await chat.customer(conversation_id, "", voice(h, "o painel caiu")) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text
    assert (h.media.fetched, h.transcriber.heard, h.chatwoot.notes) == ([], [], [])
    [_, [stored]] = await stored_attachments(h, conversation_id)
    assert stored.outcome is None
