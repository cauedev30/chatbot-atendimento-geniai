from typing import Literal

from geniai.app.notify import enqueue_message, enqueue_status
from geniai.app.ports import Deps
from geniai.app.tickets_repo import (
    NewMessage,
    NewTicket,
    add_message,
    create_ticket,
    find_attendant_by_phone,
    find_open_ticket,
    get_category_id_by_key,
    message_exists,
    update_ticket,
)
from geniai.app.turn_scheduler import TurnScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.domain.phone import normalize_br_phone
from geniai.domain.texts import MEDIA_PLACEHOLDER, TEXT, truncate

InboundOutcome = Literal[
    "duplicate",
    "unidentified_ticket",
    "triage_ticket",
    "attached_to_triage",
    "attached_to_human",
]


async def handle_inbound_message(deps: Deps, scheduler: TurnScheduler, msg: IncomingMessage) -> InboundOutcome:
    """Spec §5.1 steps 1, 2 and 8. Runs under the conversation's KeyedQueue key, never behind a turn.
    The customer turn itself is processed later by process_turn, after the burst window.
    Database writes and the Chatwoot calls they cause (outbox rows) commit in one transaction; the
    outbox worker sends them afterwards, in the background (spec §10).
    """
    now = deps.now()
    is_media = msg.has_media and msg.text.strip() == ""
    text = MEDIA_PLACEHOLDER if is_media else msg.text.strip()

    def customer_message(ticket_id: int) -> NewMessage:
        return NewMessage(
            ticket_id=ticket_id,
            author="customer",
            text=text,
            is_media=is_media,
            chatwoot_message_id=msg.message_id,
            at=now,
        )

    outcome: InboundOutcome
    async with deps.engine.begin() as conn:
        if await message_exists(conn, msg.message_id):
            return "duplicate"

        # Locked, so a turn closing this ticket meanwhile either waits or makes a new ticket open here.
        open_ticket = await find_open_ticket(conn, msg.conversation_id, lock=True)
        if open_ticket is not None:
            await add_message(conn, customer_message(open_ticket.id))
            await update_ticket(conn, open_ticket.id, {"last_customer_message_at": now})
            outcome = "attached_to_triage" if open_ticket.column == "in_triage" else "attached_to_human"
        else:
            phone = None if msg.phone is None else normalize_br_phone(msg.phone)
            who = None if phone is None else await find_attendant_by_phone(conn, phone)
            if who is None:
                # Unknown number: straight to a human, fixed acknowledgement only, never the FAQ.
                created = await create_ticket(
                    conn,
                    NewTicket(
                        column="awaiting_human",
                        conversation_id=msg.conversation_id,
                        phone_e164=phone,
                        attendant_id=None,
                        unit_id=None,
                        category_id=await get_category_id_by_key(conn, "unidentified"),
                        handoff_reason="unidentified",
                        summary=truncate(text, 280),
                    ),
                    now,
                )
                await add_message(conn, customer_message(created.id))
                await add_message(
                    conn, NewMessage(ticket_id=created.id, author="bot", text=TEXT.unidentified_ack, at=now)
                )
                await enqueue_message(conn, msg.conversation_id, TEXT.unidentified_ack)
                await enqueue_status(conn, msg.conversation_id, "open")
                outcome = "unidentified_ticket"
            else:
                created = await create_ticket(
                    conn,
                    NewTicket(
                        column="in_triage",
                        conversation_id=msg.conversation_id,
                        phone_e164=phone,
                        attendant_id=who.id,
                        unit_id=who.unit_id,
                    ),
                    now,
                )
                await add_message(conn, customer_message(created.id))
                # The bot must not depend on how Chatwoot reopens a resolved conversation: triage runs in
                # "pending".
                if msg.conversation_status is not None and msg.conversation_status != "pending":
                    await enqueue_status(conn, msg.conversation_id, "pending")
                outcome = "triage_ticket"

    deps.outbox.wake()
    if outcome in ("triage_ticket", "attached_to_triage"):
        scheduler.schedule(msg.conversation_id)
    return outcome
