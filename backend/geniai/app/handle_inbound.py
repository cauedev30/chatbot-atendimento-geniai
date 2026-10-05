from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.app.notify import enqueue_message, enqueue_status
from geniai.app.outbox import outbox_row_for_message, status_pending
from geniai.app.ports import Deps
from geniai.app.team_presence import team_wrote_since
from geniai.app.tickets_repo import (
    NewMessage,
    NewTicket,
    add_message,
    create_ticket,
    find_attendant_by_phone,
    find_open_ticket,
    get_category_id_by_key,
    has_bot_message,
    last_closed_at,
    message_exists,
    update_ticket,
)
from geniai.app.turn_scheduler import TurnScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.domain.audience import NotServedReason, not_served_reason
from geniai.domain.phone import normalize_br_phone
from geniai.domain.texts import MEDIA_PLACEHOLDER, TEXT, truncate

InboundOutcome = Literal[
    "duplicate",
    "unidentified_ticket",
    "triage_ticket",
    "attached_to_triage",
    "attached_to_human",
    "not_served",
    "team_talking",
]


@dataclass(frozen=True)
class OpenedTicket:
    ticket_id: int
    identified: bool


async def open_ticket_for(
    conn: AsyncConnection, conversation_id: int, phone: str | None, first_text: str, now: datetime
) -> OpenedTicket:
    """Identification (spec §5.1 step 2): a known phone opens a ticket in triage, anything else a ticket
    waiting for a person. The caller stores the customer messages, then acknowledges an unidentified one."""
    who = None if phone is None else await find_attendant_by_phone(conn, phone)
    if who is None:
        created = await create_ticket(
            conn,
            NewTicket(
                column="awaiting_human",
                conversation_id=conversation_id,
                phone_e164=phone,
                attendant_id=None,
                unit_id=None,
                category_id=await get_category_id_by_key(conn, "unidentified"),
                handoff_reason="unidentified",
                summary=truncate(first_text, 280),
            ),
            now,
        )
        return OpenedTicket(created.id, identified=False)
    created = await create_ticket(
        conn,
        NewTicket(
            column="in_triage",
            conversation_id=conversation_id,
            phone_e164=phone,
            attendant_id=who.id,
            unit_id=who.unit_id,
        ),
        now,
    )
    return OpenedTicket(created.id, identified=True)


async def acknowledge_unidentified(conn: AsyncConnection, conversation_id: int, ticket_id: int, now: datetime) -> None:
    """Unknown number: straight to a human, fixed acknowledgement only, never the FAQ."""
    await add_message(conn, NewMessage(ticket_id=ticket_id, author="bot", text=TEXT.unidentified_ack, at=now))
    await enqueue_message(conn, conversation_id, TEXT.unidentified_ack)
    await enqueue_status(conn, conversation_id, "open")


async def handle_inbound_message(deps: Deps, scheduler: TurnScheduler, msg: IncomingMessage) -> InboundOutcome:
    """Spec §5.1 steps 1, 2 and 8. Runs under the conversation's KeyedQueue key, never behind a turn.
    The customer turn itself is processed later by process_turn: after the burst window until the bot's
    first reply in the ticket, at once after it (see turn_scheduler.py).
    Database writes and the Chatwoot calls they cause (outbox rows) commit in one transaction; the
    outbox worker sends them afterwards, in the background (spec §10).
    A message with no open ticket in its conversation is first checked against domain/audience.py: a
    conversation the bot does not serve (a group, no usable phone, or a phone outside the test mode list)
    is opened for the team, with no reply, no ticket and no turn. So is one where the team wrote since it
    was last closed (app/team_presence.py), which is asked of Chatwoot before the transaction. An open ticket
    keeps its flow.
    """
    now = deps.now()
    # A caption is the message's text; a message with attachments and no text keeps the "[mídia]" text.
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
            attachments=msg.attachments,
        )

    reason = not_served_reason(msg.phone, msg.contact_identifier, deps.bot_only_phones)
    team_talking = False
    if reason is None:
        async with deps.engine.connect() as conn:
            check = not await message_exists(conn, msg.message_id) and not await outbox_row_for_message(
                conn, msg.message_id
            )
            check = check and await find_open_ticket(conn, msg.conversation_id) is None
            since = await last_closed_at(conn, msg.conversation_id) if check else None
            await conn.rollback()
        team_talking = check and await team_wrote_since(deps, msg.conversation_id, since)

    outcome: InboundOutcome
    handed_to_team: NotServedReason | None = None
    bot_replied = False
    async with deps.engine.begin() as conn:
        if await message_exists(conn, msg.message_id) or await outbox_row_for_message(conn, msg.message_id):
            return "duplicate"

        # Locked, so a turn closing this ticket meanwhile either waits or makes a new ticket open here.
        open_ticket = await find_open_ticket(conn, msg.conversation_id, lock=True)
        if open_ticket is None:
            # A turn that closed the ticket while this statement waited for its lock may have opened a new
            # one for the messages that arrived during it; this statement could not see it, a new one can.
            open_ticket = await find_open_ticket(conn, msg.conversation_id, lock=True)
        if open_ticket is not None:
            await add_message(conn, customer_message(open_ticket.id))
            await update_ticket(conn, open_ticket.id, {"last_customer_message_at": now})
            outcome = "attached_to_triage" if open_ticket.column == "in_triage" else "attached_to_human"
            if outcome == "attached_to_triage":
                bot_replied = await has_bot_message(conn, open_ticket.id)
        elif reason is not None or team_talking:
            # Not the bot's: straight to the team, silently. With an Agent Bot on the inbox Chatwoot keeps a
            # new conversation "pending", out of the team's view, until it is opened.
            if msg.conversation_status != "open" and not await status_pending(conn, msg.conversation_id, "open"):
                await enqueue_status(conn, msg.conversation_id, "open", chatwoot_message_id=msg.message_id)
                handed_to_team = reason
            outcome = "not_served" if reason is not None else "team_talking"
        else:
            phone = None if msg.phone is None else normalize_br_phone(msg.phone)
            opened = await open_ticket_for(conn, msg.conversation_id, phone, text, now)
            await add_message(conn, customer_message(opened.ticket_id))
            if opened.identified:
                # The bot must not depend on how Chatwoot reopens a resolved conversation: triage runs in
                # "pending".
                if msg.conversation_status is not None and msg.conversation_status != "pending":
                    await enqueue_status(conn, msg.conversation_id, "pending")
                outcome = "triage_ticket"
            else:
                await acknowledge_unidentified(conn, msg.conversation_id, opened.ticket_id, now)
                outcome = "unidentified_ticket"

    if outcome == "team_talking":
        deps.log.info({"conversationId": msg.conversation_id}, "team is talking")
    if handed_to_team is not None:
        deps.log.info(
            {"conversationId": msg.conversation_id, "reason": handed_to_team}, "conversation handed to the team"
        )
    deps.outbox.wake()
    if outcome in ("triage_ticket", "attached_to_triage"):
        scheduler.schedule(msg.conversation_id, bot_replied=bot_replied)
    return outcome
