import pytest
from sqlalchemy import select

from geniai.app.tickets_repo import (
    AttendantWithUnit,
    InvalidMoveError,
    NewMessage,
    NewTicket,
    TicketRow,
    add_message,
    create_ticket,
    find_attendant_by_phone,
    find_open_ticket,
    get_category_id_by_key,
    get_faq_item,
    list_active_categories,
    list_messages,
    message_exists,
    move_ticket,
    set_message_attachments,
    update_ticket,
)
from geniai.db.fixtures import FICTITIOUS
from geniai.db.schema import ticket_move, triage_message
from geniai.domain.types import Attachment
from tests.conftest import Harness


async def new_triage_ticket(h: Harness, conversation_id: int = 10) -> TicketRow:
    ana = h.seed.attendants["ana"]
    async with h.begin() as conn:
        return await create_ticket(
            conn,
            NewTicket(
                column="in_triage",
                conversation_id=conversation_id,
                phone_e164=ana.phone,
                attendant_id=ana.id,
                unit_id=ana.unit_id,
            ),
            h.now,
        )


async def test_finds_active_attendants_by_phone_with_their_unit(h: Harness) -> None:
    async with h.begin() as conn:
        found = await find_attendant_by_phone(conn, h.seed.attendants["ana"].phone)
        assert found == AttendantWithUnit(
            id=h.seed.attendants["ana"].id,
            name="Ana Exemplo",
            unit_id=h.seed.units["centro"],
            unit_name="Unidade Exemplo Centro",
        )
        assert await find_attendant_by_phone(conn, h.seed.attendants["inactive"].phone) is None
        assert await find_attendant_by_phone(conn, "+5511900000098") is None


async def test_creates_a_ticket_with_its_first_move(h: Harness) -> None:
    t = await new_triage_ticket(h)
    assert t.column == "in_triage"
    async with h.begin() as conn:
        moves = (await conn.execute(select(ticket_move).where(ticket_move.c.ticket_id == t.id))).all()
    assert [(m.from_column, m.to_column, m.actor) for m in moves] == [(None, "in_triage", "bot")]


async def test_stamps_handed_off_at_when_created_awaiting_a_human(h: Harness) -> None:
    async with h.begin() as conn:
        t = await create_ticket(
            conn,
            NewTicket(
                column="awaiting_human",
                conversation_id=11,
                phone_e164=None,
                attendant_id=None,
                unit_id=None,
                category_id=await get_category_id_by_key(conn, "unidentified"),
                handoff_reason="unidentified",
            ),
            h.now,
        )
    assert t.handed_off_at == h.now


async def test_ignores_duplicate_chatwoot_message_ids(h: Harness) -> None:
    t = await new_triage_ticket(h)
    message = NewMessage(ticket_id=t.id, author="customer", text="oi", chatwoot_message_id=500, at=h.now)
    async with h.begin() as conn:
        assert await add_message(conn, message) is True
        assert await add_message(conn, message) is False
        assert await message_exists(conn, 500) is True
        assert len(await list_messages(conn, t.id)) == 1


PHOTO = "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/foto.jpg"


async def test_stores_a_caption_with_its_attachments_and_records_what_the_llm_saw(h: Harness) -> None:
    t = await new_triage_ticket(h)
    sent = (Attachment("image", PHOTO), Attachment("audio"))
    message = NewMessage(ticket_id=t.id, author="customer", text="deu isso", at=h.now, attachments=sent)
    async with h.begin() as conn:
        await add_message(conn, message)
        [stored] = await list_messages(conn, t.id)
        assert (stored.text, stored.is_media, stored.attachments) == ("deu isso", False, sent)
        seen = (Attachment("image", PHOTO, "seen", "Tela de login com erro de senha."), Attachment("audio"))
        await set_message_attachments(conn, stored.id, seen)
        [stored] = await list_messages(conn, t.id)
    assert stored.attachments == seen


async def test_reads_a_message_without_attachments_and_tolerates_odd_stored_ones(h: Harness) -> None:
    t = await new_triage_ticket(h)
    async with h.begin() as conn:
        await add_message(conn, NewMessage(ticket_id=t.id, author="customer", text="oi", at=h.now))
        await add_message(conn, NewMessage(ticket_id=t.id, author="customer", text="[mídia]", at=h.now))
        odd = [{"kind": "sticker"}, {"kind": "image", "url": 3, "outcome": "odd", "description": 5}, "x"]
        await conn.execute(triage_message.update().where(triage_message.c.text == "[mídia]").values(attachments=odd))
        plain, stored = await list_messages(conn, t.id)
    assert plain.attachments == ()
    assert stored.attachments == (Attachment("file"), Attachment("image"))


async def test_records_an_audio_s_transcription_and_reads_each_outcome_only_for_its_kind(h: Harness) -> None:
    t = await new_triage_ticket(h)
    async with h.begin() as conn:
        await add_message(conn, NewMessage(ticket_id=t.id, author="customer", text="[mídia]", at=h.now))
        [stored] = await list_messages(conn, t.id)
        heard = (
            Attachment("audio", PHOTO, "transcribed", transcript="o painel não abre"),
            Attachment("audio", None, "too_long"),
            Attachment("audio", None, "failed"),
        )
        await set_message_attachments(conn, stored.id, heard)
        [stored] = await list_messages(conn, t.id)
        assert stored.attachments == heard
        odd = [
            {"kind": "audio", "outcome": "seen", "transcript": 5},
            {"kind": "image", "outcome": "transcribed", "transcript": "x"},
        ]
        await conn.execute(triage_message.update().where(triage_message.c.id == stored.id).values(attachments=odd))
        [stored] = await list_messages(conn, t.id)
    assert stored.attachments == (Attachment("audio"), Attachment("image"))


async def test_finds_only_open_tickets_of_a_conversation(h: Harness) -> None:
    t = await new_triage_ticket(h, 12)
    async with h.begin() as conn:
        found = await find_open_ticket(conn, 12)
        assert found is not None
        assert found.id == t.id
        await move_ticket(conn, t.id, "resolved_by_bot", "bot", h.now)
        assert await find_open_ticket(conn, 12) is None


async def test_moves_with_timestamps_and_history_and_rejects_moves_the_actor_may_not_make(h: Harness) -> None:
    t = await new_triage_ticket(h)
    h.advance(60_000)
    async with h.begin() as conn:
        result = await move_ticket(conn, t.id, "awaiting_human", "bot", h.now, {"handoff_reason": "no_faq_match"})
    assert result.from_ == "in_triage"
    assert result.ticket.column == "awaiting_human"
    assert result.ticket.handoff_reason == "no_faq_match"
    assert result.ticket.handed_off_at == h.now
    assert result.ticket.last_moved_at == h.now
    with pytest.raises(InvalidMoveError):
        async with h.begin() as conn:
            await move_ticket(conn, t.id, "in_progress", "bot", h.now)
    async with h.begin() as conn:
        moves = (await conn.execute(select(ticket_move).where(ticket_move.c.ticket_id == t.id))).all()
    assert len(moves) == 2


async def test_lists_active_categories_including_their_keys(h: Harness) -> None:
    async with h.begin() as conn:
        categories = await list_active_categories(conn)
    assert "other" in [c.key for c in categories]
    login = next(c for c in categories if c.id == h.seed.categories["login"])
    assert (login.system, login.key) == ("Painel", None)


async def test_rejects_a_patch_that_is_not_a_ticket_column_or_touches_id_or_column(h: Harness) -> None:
    t = await new_triage_ticket(h)
    async with h.begin() as conn:
        patches: list[dict[str, object]] = [{"column": "in_progress"}, {"id": 99}, {"nope": 1}]
        for patch in patches:
            with pytest.raises(ValueError):
                await update_ticket(conn, t.id, patch)


async def test_reads_an_faq_item_with_its_knowledge_base_and_a_new_ticket_with_no_question_answered(
    h: Harness,
) -> None:
    async with h.begin() as conn:
        item = await get_faq_item(conn, h.seed.faq["password"])
    assert item is not None
    assert item.knowledge_base == FICTITIOUS["faq"]["password"]["knowledge_base"]
    assert (await new_triage_ticket(h)).faq_questions_answered == 0
