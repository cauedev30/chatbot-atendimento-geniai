import asyncio
import itertools
from typing import Any

import pytest
from sqlalchemy import select

from geniai.app.handle_inbound import handle_inbound_message, open_ticket_for
from geniai.app.process_turn import process_turn
from geniai.app.tickets_repo import TicketRow, get_ticket, list_messages, move_ticket
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.db.schema import ticket, triage_message
from geniai.domain.texts import MEDIA_PLACEHOLDER, TEXT
from geniai.domain.types import Attachment
from tests.conftest import Harness
from tests.support.fakes import Sent, StatusSet

_message_ids = itertools.count(1000)
UNKNOWN = "+5511900000099"
"""A Brazilian phone that is not in the fictitious attendant base."""
GROUP = "120363000000000001@g.us"


@pytest.fixture
def scheduler() -> RecordingScheduler:
    return RecordingScheduler()


def inbound(h: Harness, **overrides: Any) -> IncomingMessage:
    fields: dict[str, Any] = {
        "message_id": next(_message_ids),
        "conversation_id": 50,
        "phone": h.seed.attendants["ana"].phone,
        "text": "oi",
        "conversation_status": None,
    }
    return IncomingMessage(**(fields | overrides))


async def tickets_of(h: Harness, conversation_id: int) -> list[TicketRow]:
    async with h.begin() as conn:
        rows = await conn.execute(
            select(ticket).where(ticket.c.chatwoot_conversation_id == conversation_id).order_by(ticket.c.id)
        )
        return [TicketRow(**r._mapping) for r in rows]


async def test_sends_an_unknown_number_straight_to_a_human_with_no_faq(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    outcome = await handle_inbound_message(h.deps, scheduler, inbound(h, phone=UNKNOWN, text="socorro"))
    assert outcome == "unidentified_ticket"
    [t] = await tickets_of(h, 50)
    assert t.column == "awaiting_human"
    assert t.handoff_reason == "unidentified"
    assert t.category_id == h.seed.categories["unidentified"]
    assert t.attendant_id is None
    assert t.phone_e164 == "+5511900000099"
    assert t.summary == "socorro"
    assert t.handed_off_at == h.now
    await h.settle()
    assert h.chatwoot.sent == [Sent(50, TEXT.unidentified_ack)]
    assert h.chatwoot.statuses == [StatusSet(50, "open")]
    assert scheduler.scheduled == []


async def test_hands_a_missing_or_non_brazilian_sender_id_to_the_team_without_a_ticket(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    msg = inbound(h, phone=None, conversation_status="pending")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "not_served"
    msg = inbound(h, conversation_id=51, phone="123456789012345", conversation_status="pending")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "not_served"
    await h.settle()
    assert await tickets_of(h, 50) == []
    assert await tickets_of(h, 51) == []
    assert h.chatwoot.statuses == [StatusSet(50, "open"), StatusSet(51, "open")]
    assert h.chatwoot.sent == []


async def test_treats_an_inactive_attendant_as_unknown(h: Harness, scheduler: RecordingScheduler) -> None:
    msg = inbound(h, phone=h.seed.attendants["inactive"].phone)
    assert await handle_inbound_message(h.deps, scheduler, msg) == "unidentified_ticket"


async def test_opens_a_triage_ticket_for_a_known_number_with_a_unit_snapshot_and_schedules_the_turn(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, phone="11 900000001")) == "triage_ticket"
    [t] = await tickets_of(h, 50)
    assert t.column == "in_triage"
    assert t.attendant_id == h.seed.attendants["ana"].id
    assert t.unit_id == h.seed.units["centro"]
    assert t.phone_e164 == "+5511900000001"
    assert scheduler.scheduled == [50]
    assert h.chatwoot.sent == []


async def test_puts_the_conversation_back_to_pending_when_a_triage_ticket_opens_on_another_status(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    msg = inbound(h, conversation_status="resolved")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "triage_ticket"
    await h.settle()
    assert h.chatwoot.statuses == [StatusSet(50, "pending")]
    assert h.chatwoot.sent == []


async def test_leaves_a_pending_or_unknown_conversation_status_alone(h: Harness, scheduler: RecordingScheduler) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_status="pending"))
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id=51, conversation_status=None))
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id=52))
    await h.settle()
    assert h.chatwoot.statuses == []


async def test_does_not_touch_the_status_of_a_conversation_already_with_a_human(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, phone=UNKNOWN))
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_status="open"))
    await h.settle()
    assert h.chatwoot.statuses == [StatusSet(50, "open")]


async def test_ignores_duplicate_deliveries(h: Harness, scheduler: RecordingScheduler) -> None:
    msg = inbound(h)
    await handle_inbound_message(h.deps, scheduler, msg)
    assert await handle_inbound_message(h.deps, scheduler, msg) == "duplicate"
    async with h.begin() as conn:
        assert len((await conn.execute(select(triage_message))).all()) == 1


async def test_attaches_follow_up_messages_to_the_triage_ticket_and_restarts_the_window(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h))
    h.advance(2_000)
    outcome = await handle_inbound_message(h.deps, scheduler, inbound(h, text="meu número caiu"))
    assert outcome == "attached_to_triage"
    [t] = await tickets_of(h, 50)
    assert t.last_customer_message_at == h.now
    assert scheduler.scheduled == [50, 50]


async def test_waits_for_the_burst_window_only_until_the_bot_first_replied(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h))
    await handle_inbound_message(h.deps, scheduler, inbound(h, text="bom dia"))
    assert await process_turn(h.deps, 50) == "greeting"
    await handle_inbound_message(h.deps, scheduler, inbound(h, text="meu número caiu"))
    assert scheduler.scheduled == [50, 50, 50]
    assert scheduler.bot_replied == [False, False, True]


async def test_stores_media_without_text_as_a_media_message(h: Harness, scheduler: RecordingScheduler) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, text="", attachments=(Attachment("audio"),)))
    async with h.begin() as conn:
        [m] = (await conn.execute(select(triage_message))).all()
    assert (m.is_media, m.text, m.attachments) == (True, MEDIA_PLACEHOLDER, [{"kind": "audio"}])


async def test_stores_a_photo_with_a_caption_as_the_caption_and_its_attachment(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    photo = Attachment("image", "https://chatwoot.example/rails/active_storage/blobs/redirect/abc123/foto.jpg")
    await handle_inbound_message(h.deps, scheduler, inbound(h, text="deu esse erro", attachments=(photo,)))
    [t] = await tickets_of(h, 50)
    async with h.begin() as conn:
        [m] = await list_messages(conn, t.id)
    assert (m.text, m.is_media, m.attachments) == ("deu esse erro", False, (photo,))


async def test_stays_silent_on_a_ticket_that_is_with_a_human(h: Harness, scheduler: RecordingScheduler) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h))
    [t] = await tickets_of(h, 50)
    async with h.begin() as conn:
        await move_ticket(conn, t.id, "awaiting_human", "bot", h.now, {"handoff_reason": "no_faq_match"})
    outcome = await handle_inbound_message(h.deps, scheduler, inbound(h, text="alguém aí?"))
    assert outcome == "attached_to_human"
    assert scheduler.scheduled == [50]
    assert h.chatwoot.sent == []


async def test_opens_a_new_ticket_after_the_previous_one_closed(h: Harness, scheduler: RecordingScheduler) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h))
    [t] = await tickets_of(h, 50)
    async with h.begin() as conn:
        await move_ticket(conn, t.id, "resolved_by_bot", "bot", h.now)
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, text="outro problema")) == "triage_ticket"
    assert len(await tickets_of(h, 50)) == 2


async def test_keeps_the_ticket_when_chatwoot_is_down(h: Harness, scheduler: RecordingScheduler) -> None:
    h.chatwoot.fail_sends = True
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, phone=UNKNOWN)) == "unidentified_ticket"
    assert len(await tickets_of(h, 50)) == 1
    await h.settle()
    assert len(h.logger.errors) > 0


async def test_writes_the_ticket_before_any_outbound_message(h: Harness, scheduler: RecordingScheduler) -> None:
    """Spec §10: when Chatwoot is called, the ticket is already committed and visible to others."""
    seen: list[int] = []
    send = h.chatwoot.send_message

    async def send_after_checking(conversation_id: int, text: str) -> None:
        seen.append(len(await tickets_of(h, conversation_id)))
        await send(conversation_id, text)

    h.chatwoot.send_message = send_after_checking  # type: ignore[method-assign]
    await handle_inbound_message(h.deps, scheduler, inbound(h, phone=UNKNOWN))
    await h.settle()
    assert seen == [1]


async def test_attaches_to_the_ticket_a_closing_turn_opened_while_this_message_waited_for_the_lock(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id=58))
    [first] = await tickets_of(h, 58)
    async with h.begin() as conn:
        # A turn holds the ticket, closes it and opens the next one, like process_turn with late messages.
        await get_ticket(conn, first.id, lock=True)
        await move_ticket(conn, first.id, "resolved_by_bot", "bot", h.now)
        opened = await open_ticket_for(conn, 58, first.phone_e164, "ah, outra coisa", h.now)
        waiting = asyncio.create_task(
            handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id=58, text="mais uma"))
        )
        await asyncio.sleep(0.1)
        assert not waiting.done()
    assert await waiting == "attached_to_triage"
    tickets = await tickets_of(h, 58)
    assert [t.id for t in tickets] == [first.id, opened.ticket_id]
    async with h.begin() as conn:
        assert [m.text for m in await list_messages(conn, opened.ticket_id)] == ["mais uma"]


async def all_rows(h: Harness) -> tuple[int, int]:
    async with h.begin() as conn:
        tickets = len((await conn.execute(select(ticket))).all())
        messages = len((await conn.execute(select(triage_message))).all())
    return tickets, messages


def handed_to_team(h: Harness) -> list[object]:
    return [e.obj["reason"] for e in h.logger.infos if e.msg == "conversation handed to the team"]


async def test_test_mode_serves_a_listed_phone(h: Harness, scheduler: RecordingScheduler) -> None:
    h.deps.bot_only_phones = frozenset({h.seed.attendants["ana"].phone})
    msg = inbound(h, phone="11 90000-0001", conversation_status="pending")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "triage_ticket"
    assert scheduler.scheduled == [50]


async def test_test_mode_hands_any_other_phone_to_the_team_silently(h: Harness, scheduler: RecordingScheduler) -> None:
    h.deps.bot_only_phones = frozenset({UNKNOWN})
    msg = inbound(h, conversation_status="pending")  # a known attendant, but not in the list
    assert await handle_inbound_message(h.deps, scheduler, msg) == "not_served"
    await h.settle()
    assert h.chatwoot.statuses == [StatusSet(50, "open")]
    assert h.chatwoot.sent == []
    assert await all_rows(h) == (0, 0)
    assert scheduler.scheduled == []
    assert h.llm.requests == []
    [line] = [e for e in h.logger.infos if e.msg == "conversation handed to the team"]
    assert line.obj == {"conversationId": 50, "reason": "not_in_test_list"}


async def test_an_empty_test_list_serves_everyone(h: Harness, scheduler: RecordingScheduler) -> None:
    assert h.deps.bot_only_phones == frozenset()
    assert await handle_inbound_message(h.deps, scheduler, inbound(h)) == "triage_ticket"
    msg = inbound(h, conversation_id=51, phone=UNKNOWN)
    assert await handle_inbound_message(h.deps, scheduler, msg) == "unidentified_ticket"


@pytest.mark.parametrize("only", [frozenset(), frozenset({"+5511900000001"})])
async def test_never_serves_a_group_even_with_its_phone_listed(
    h: Harness, scheduler: RecordingScheduler, only: frozenset[str]
) -> None:
    h.deps.bot_only_phones = only
    msg = inbound(h, contact_identifier=GROUP, conversation_status="pending")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "not_served"
    await h.settle()
    assert h.chatwoot.statuses == [StatusSet(50, "open")]
    assert h.chatwoot.sent == []
    assert await all_rows(h) == (0, 0)
    assert scheduler.scheduled == []
    assert h.llm.requests == []
    assert handed_to_team(h) == ["group"]


async def test_hands_a_conversation_to_the_team_once(h: Harness, scheduler: RecordingScheduler) -> None:
    msg = inbound(h, contact_identifier=GROUP, conversation_status="pending")
    await handle_inbound_message(h.deps, scheduler, msg)
    # A later message while the first change still waits in the outbox: nothing new.
    later = inbound(h, contact_identifier=GROUP, conversation_status="pending")
    assert await handle_inbound_message(h.deps, scheduler, later) == "not_served"
    await h.settle()
    # The same delivery again, after the change was sent: its body still says "pending"; a duplicate.
    assert await handle_inbound_message(h.deps, scheduler, msg) == "duplicate"
    # The conversation is open now: nothing to do.
    opened = inbound(h, contact_identifier=GROUP, conversation_status="open")
    assert await handle_inbound_message(h.deps, scheduler, opened) == "not_served"
    await h.settle()
    assert h.chatwoot.statuses == [StatusSet(50, "open")]
    assert handed_to_team(h) == ["group"]


async def test_opens_again_a_conversation_back_in_pending(h: Harness, scheduler: RecordingScheduler) -> None:
    """The team resolved it and the customer wrote again: Chatwoot gives it to the bot once more."""
    for _ in range(2):
        msg = inbound(h, contact_identifier=GROUP, conversation_status="pending")
        await handle_inbound_message(h.deps, scheduler, msg)
        await h.settle()
    assert h.chatwoot.statuses == [StatusSet(50, "open"), StatusSet(50, "open")]


async def test_a_ticket_already_open_keeps_its_flow_when_its_phone_leaves_the_test_list(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    assert await handle_inbound_message(h.deps, scheduler, inbound(h)) == "triage_ticket"
    h.deps.bot_only_phones = frozenset({UNKNOWN})
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, text="e agora?")) == "attached_to_triage"
    assert scheduler.scheduled == [50, 50]
