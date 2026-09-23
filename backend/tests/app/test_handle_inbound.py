import itertools
from typing import Any

import pytest
from sqlalchemy import select

from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.tickets_repo import TicketRow, move_ticket
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.db.schema import ticket, triage_message
from geniai.domain.texts import MEDIA_PLACEHOLDER, TEXT
from tests.conftest import Harness
from tests.support.fakes import Sent, StatusSet

_message_ids = itertools.count(1000)


@pytest.fixture
def scheduler() -> RecordingScheduler:
    return RecordingScheduler()


def inbound(h: Harness, **overrides: Any) -> IncomingMessage:
    fields: dict[str, Any] = {
        "message_id": next(_message_ids),
        "conversation_id": 50,
        "phone": h.seed.attendants["ana"].phone,
        "text": "oi",
        "has_media": False,
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
    outcome = await handle_inbound_message(h.deps, scheduler, inbound(h, phone="+5511900000099", text="socorro"))
    assert outcome == "unidentified_ticket"
    [t] = await tickets_of(h, 50)
    assert t.column == "awaiting_human"
    assert t.handoff_reason == "unidentified"
    assert t.category_id == h.seed.categories["unidentified"]
    assert t.attendant_id is None
    assert t.phone_e164 == "+5511900000099"
    assert t.summary == "socorro"
    assert t.handed_off_at == h.now
    assert h.chatwoot.sent == [Sent(50, TEXT.unidentified_ack)]
    assert h.chatwoot.statuses == [StatusSet(50, "open")]
    assert scheduler.scheduled == []


async def test_treats_a_missing_or_non_brazilian_sender_id_as_unknown(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, phone=None)) == "unidentified_ticket"
    msg = inbound(h, conversation_id=51, phone="123456789012345")
    assert await handle_inbound_message(h.deps, scheduler, msg) == "unidentified_ticket"


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
    assert h.chatwoot.statuses == [StatusSet(50, "pending")]
    assert h.chatwoot.sent == []


async def test_leaves_a_pending_or_unknown_conversation_status_alone(h: Harness, scheduler: RecordingScheduler) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_status="pending"))
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id=51, conversation_status=None))
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_id=52))
    assert h.chatwoot.statuses == []


async def test_does_not_touch_the_status_of_a_conversation_already_with_a_human(
    h: Harness, scheduler: RecordingScheduler
) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, phone=None))
    await handle_inbound_message(h.deps, scheduler, inbound(h, conversation_status="open"))
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


async def test_stores_media_without_text_as_a_media_message(h: Harness, scheduler: RecordingScheduler) -> None:
    await handle_inbound_message(h.deps, scheduler, inbound(h, text="", has_media=True))
    async with h.begin() as conn:
        [m] = (await conn.execute(select(triage_message))).all()
    assert (m.is_media, m.text) == (True, MEDIA_PLACEHOLDER)


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
    assert await handle_inbound_message(h.deps, scheduler, inbound(h, phone=None)) == "unidentified_ticket"
    assert len(await tickets_of(h, 50)) == 1
    assert len(h.logger.errors) > 0


async def test_writes_the_ticket_before_any_outbound_message(h: Harness, scheduler: RecordingScheduler) -> None:
    """Spec §10: when Chatwoot is called, the ticket is already committed and visible to others."""
    seen: list[int] = []
    send = h.chatwoot.send_message

    async def send_after_checking(conversation_id: int, text: str) -> None:
        seen.append(len(await tickets_of(h, conversation_id)))
        await send(conversation_id, text)

    h.chatwoot.send_message = send_after_checking  # type: ignore[method-assign]
    await handle_inbound_message(h.deps, scheduler, inbound(h, phone=None))
    assert seen == [1]
