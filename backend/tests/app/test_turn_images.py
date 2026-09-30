"""Turns with attachments: images read by the LLM, what the bot cannot open, and image reading off."""

import itertools
import json
from typing import Any

import pytest
from sqlalchemy import insert

from geniai.app.ports import FetchFailure, ImageData
from geniai.app.process_turn import process_turn
from geniai.app.tickets_repo import list_messages
from geniai.db.schema import triage_message
from geniai.domain.texts import TEXT
from geniai.domain.types import Attachment, AttachmentKind
from tests.app.test_process_turn import Chat
from tests.conftest import Harness
from tests.support.fakes import turn_json

_links = itertools.count(1)


@pytest.fixture
def chat(h: Harness) -> Chat:
    return Chat(h)


def photo(h: Harness, opens: bool = True, content_type: str = "image/png") -> Attachment:
    """An image on the fictitious Chatwoot; FakeMedia serves it when it opens."""
    url = f"https://chatwoot.example/rails/active_storage/blobs/redirect/{next(_links)}/foto.png"
    h.media.images[url] = ImageData(f"bytes of {url}".encode(), content_type) if opens else FetchFailure("status")
    return Attachment("image", url)


def served(h: Harness, image: Attachment) -> ImageData:
    data = h.media.images[image.url or ""]
    assert isinstance(data, ImageData)
    return data


def payload(h: Harness, n: int = -1) -> dict[str, Any]:
    result: dict[str, Any] = json.loads(h.llm.requests[n].user)
    return result


def history(h: Harness) -> list[str]:
    return [m["text"] for m in payload(h)["conversation"]]


async def stored_attachments(h: Harness, conversation_id: int) -> list[tuple[Attachment, ...]]:
    t = await Chat(h).ticket_of(conversation_id)
    async with h.begin() as conn:
        return [m.attachments for m in await list_messages(conn, t.id) if m.author == "customer"]


async def test_an_image_alone_counts_as_the_customer_message_and_its_description_replaces_it_later(
    h: Harness, chat: Chat
) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    image = photo(h)
    h.llm.push(
        turn_json(
            category_id=h.seed.categories["login"],
            faq_item_id=h.seed.faq["password"],
            summary="Print do painel com erro de senha.",
            image_descriptions=["Tela de login do painel com o erro senha incorreta."],
        )
    )
    assert await chat.customer(conversation_id, "", image) == "send_faq"
    assert h.llm.requests[-1].images == (served(h, image),)
    assert (payload(h)["new_messages"], payload(h)["images_attached"]) == (["[imagem 1]"], 1)
    t = await chat.ticket_of(conversation_id)
    assert (t.summary, t.media_prompts) == ("Print do painel com erro de senha.", 0)
    [_, stored] = await stored_attachments(h, conversation_id)
    assert stored == (Attachment("image", image.url, "seen", "Tela de login do painel com o erro senha incorreta."),)

    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="resolved"))
    assert await chat.customer(conversation_id, "resolveu") == "resolved_by_bot"
    assert h.llm.requests[-1].images == ()
    assert "[imagem: Tela de login do painel com o erro senha incorreta.]" in history(h)
    assert "images_attached" not in payload(h)
    assert h.media.fetched == [image.url]


async def test_an_image_with_a_caption_goes_to_the_llm_with_its_caption(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual painel?"))
    assert await chat.customer(conversation_id, "deu esse erro", photo(h)) == "ask_clarification"
    assert payload(h)["new_messages"] == ["[imagem 1] deu esse erro"]
    assert len(h.llm.requests[-1].images) == 1


async def test_reads_the_four_most_recent_images_and_names_the_older_ones(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    images = [photo(h) for _ in range(5)]
    for image in images:
        await chat.receive(conversation_id, "", image)
    h.llm.push(turn_json(category_id=h.seed.categories["other"], image_descriptions=["a", "b", "c", "d"]))
    assert await process_turn(h.deps, conversation_id) == "handoff"
    assert payload(h, 0)["new_messages"] == [
        "[imagem — além do limite, não vista]",
        "[imagem 1]",
        "[imagem 2]",
        "[imagem 3]",
        "[imagem 4]",
    ]
    assert h.llm.requests[0].images == tuple(served(h, i) for i in images[1:])
    assert h.media.fetched == [i.url for i in images[1:]]
    stored = await stored_attachments(h, conversation_id)
    assert [a.outcome for [a] in stored[1:]] == ["over_limit", "seen", "seen", "seen", "seen"]
    assert [a.description for [a] in stored[2:]] == ["a", "b", "c", "d"]


async def test_an_image_that_did_not_open_asks_for_text_once_without_saying_it_did_not_arrive(
    h: Harness, chat: Chat
) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    failed = photo(h, opens=False)
    assert await chat.customer(conversation_id, "", failed) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_image
    assert h.llm.requests == []
    [line] = [e for e in h.logger.infos if e.msg == "image not read"]
    ticket_id = (await chat.ticket_of(conversation_id)).id
    assert line.obj == {"ticketId": ticket_id, "reason": "status", "contentType": None, "size": None}
    assert failed.url is not None
    assert failed.url not in repr(h.logger.infos)
    assert await chat.customer(conversation_id, "", photo(h, opens=False)) == "handoff"
    assert (await chat.ticket_of(conversation_id)).handoff_reason == "media"


async def test_an_image_that_did_not_open_next_to_text_is_named_for_the_llm(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    assert await chat.customer(conversation_id, "olha isso", photo(h, opens=False)) == "ask_clarification"
    assert payload(h)["new_messages"] == ["[imagem — não foi possível abrir] olha isso"]
    assert h.llm.requests[-1].images == ()
    [_, [stored]] = await stored_attachments(h, conversation_id)
    assert stored.outcome == "failed"


@pytest.mark.parametrize(
    ("kind", "label"),
    [
        ("audio", "[áudio — o bot não ouve]"),
        ("video", "[vídeo — o bot não abre]"),
        ("file", "[arquivo — o bot não abre]"),
    ],
)
async def test_audio_video_or_a_file_alone_asks_for_text_and_next_to_text_is_named(
    h: Harness, chat: Chat, kind: AttachmentKind, label: str
) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    assert await chat.customer(conversation_id, "", Attachment(kind, "https://chatwoot.example/x")) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_other
    assert h.llm.requests == []
    h.llm.push(turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Pode escrever?"))
    assert await chat.customer(conversation_id, "é sobre o painel", Attachment(kind)) == "ask_clarification"
    assert payload(h)["new_messages"] == [f"{label} é sobre o painel"]
    assert h.media.fetched == []


async def test_an_image_that_did_not_open_with_audio_asks_about_the_audio(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    await chat.receive(conversation_id, "", photo(h, opens=False))
    assert await chat.customer(conversation_id, "", Attachment("audio")) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text_other


async def test_with_image_reading_off_nothing_is_downloaded_and_the_reply_is_the_usual_one(
    h: Harness, chat: Chat
) -> None:
    conversation_id = await chat.greeted()
    assert await chat.customer(conversation_id, "", photo(h)) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    assert await chat.customer(conversation_id, "o painel deu isso", photo(h)) == "ask_clarification"
    assert payload(h)["new_messages"] == ["[imagem — não foi possível abrir] o painel deu isso"]
    assert history(h)[-2:] == ["[imagem — não foi possível abrir]", TEXT.ask_for_text]
    assert h.llm.requests[-1].images == ()
    assert h.media.fetched == []


async def test_a_missing_description_is_stored_as_an_image_the_bot_saw(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    assert await chat.customer(conversation_id, "", photo(h)) == "ask_clarification"
    [_, [stored]] = await stored_attachments(h, conversation_id)
    assert (stored.outcome, stored.description) == ("seen", "[imagem vista pelo bot]")
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="E agora?"))
    await chat.customer(conversation_id, "é no painel")
    assert "[imagem vista pelo bot]" in history(h)


async def test_an_image_sent_before_the_greeting_is_read_in_the_next_turn(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = 900
    image = photo(h)
    assert await chat.customer(conversation_id, "", image) == "greeting"
    assert h.media.fetched == []
    h.llm.push(turn_json(category_id=h.seed.categories["login"], image_descriptions=["Erro de senha."]))
    assert await chat.customer(conversation_id, "sim, sou eu") == "handoff"
    assert history(h)[0] == "[imagem 1]"
    assert payload(h)["new_messages"] == ["sim, sou eu"]
    assert h.llm.requests[-1].images == (served(h, image),)
    [[stored], _] = await stored_attachments(h, conversation_id)
    assert (stored.outcome, stored.description) == ("seen", "Erro de senha.")


async def test_a_question_sent_as_an_image_reaches_the_summary_by_its_description(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.faq_sent()
    h.llm.push(
        turn_json(
            category_id=h.seed.categories["login"],
            faq_feedback="question",
            faq_answer_found=False,
            summary="Senha.",
            image_descriptions=["Print perguntando se o link expira."],
        )
    )
    assert await chat.customer(conversation_id, "", photo(h)) == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert t.summary == "Senha. Dúvida sem resposta: [imagem: Print perguntando se o link expira.]"


async def test_a_media_message_stored_before_attachments_were_kept_is_a_file_the_bot_cannot_open(
    h: Harness, chat: Chat
) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    t = await chat.ticket_of(conversation_id)
    async with h.begin() as conn:
        await conn.execute(
            insert(triage_message).values(ticket_id=t.id, author="customer", text="[mídia]", is_media=True, at=h.now)
        )
    assert await process_turn(h.deps, conversation_id) == "ask_for_text"
    await h.settle()
    assert chat.last_sent() == TEXT.ask_for_text_other
    h.llm.push(turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Qual?"))
    await chat.customer(conversation_id, "é o painel")
    assert "[arquivo — o bot não abre]" in history(h)


async def test_an_image_the_turn_read_is_logged_by_type_and_size_only(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    image = photo(h, content_type="image/jpeg")
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    await chat.customer(conversation_id, "", image)
    [line] = [e for e in h.logger.infos if e.msg == "image read"]
    ticket_id = (await chat.ticket_of(conversation_id)).id
    assert line.obj == {"ticketId": ticket_id, "contentType": "image/jpeg", "size": len(served(h, image).data)}


async def test_a_handoff_before_the_llm_gets_its_summary_with_the_images(h: Harness, chat: Chat) -> None:
    h.reads_images()
    conversation_id = await chat.greeted()
    image = photo(h)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], summary="Pede atendente; print de erro de senha."))
    assert await chat.customer(conversation_id, "quero falar com um atendente", image) == "handoff"
    assert h.llm.requests[-1].images == (served(h, image),)
    assert (await chat.ticket_of(conversation_id)).summary == "Pede atendente; print de erro de senha."
