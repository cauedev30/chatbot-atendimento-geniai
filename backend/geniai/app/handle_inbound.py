from typing import Literal

from geniai.app.notify import safely
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
    """Spec §5.1 steps 1, 2 and 8. Runs under the conversation's KeyedQueue key.
    The customer turn itself is processed later by process_turn, after the burst window.
    Database writes commit in one transaction before any outbound Chatwoot call (spec §10).
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

        open_ticket = await find_open_ticket(conn, msg.conversation_id)
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
                outcome = "triage_ticket"

    conversation_id = msg.conversation_id
    if outcome == "unidentified_ticket":
        await safely(
            deps.log,
            "send unidentified ack",
            lambda: deps.chatwoot.send_message(conversation_id, TEXT.unidentified_ack),
        )
        await safely(deps.log, "open conversation", lambda: deps.chatwoot.set_status(conversation_id, "open"))
    elif outcome == "triage_ticket":
        # The bot must not depend on how Chatwoot reopens a resolved conversation: triage runs in "pending".
        if msg.conversation_status is not None and msg.conversation_status != "pending":
            await safely(
                deps.log, "set conversation pending", lambda: deps.chatwoot.set_status(conversation_id, "pending")
            )
        scheduler.schedule(conversation_id)
    elif outcome == "attached_to_triage":
        scheduler.schedule(conversation_id)
    return outcome
