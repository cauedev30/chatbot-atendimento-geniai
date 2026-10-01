import asyncio
import time
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.app.attachments import (
    TurnImages,
    is_legible,
    may_be_legible,
    message_text,
    read_images,
    unread_media,
    with_outcomes,
)
from geniai.app.handle_inbound import acknowledge_unidentified, open_ticket_for
from geniai.app.keyed_queue import KeyedQueue, turn_key
from geniai.app.notify import enqueue_message, enqueue_status, enqueue_status_after_move
from geniai.app.ports import Deps
from geniai.app.tickets_repo import (
    MessageRow,
    NewMessage,
    TicketRow,
    add_message,
    find_open_ticket,
    get_attendant_with_unit,
    get_category_id_by_key,
    get_faq_item,
    get_ticket,
    list_active_categories,
    list_active_faq_items,
    list_messages,
    move_messages,
    move_ticket,
    set_message_attachments,
    update_ticket,
)
from geniai.app.turn_scheduler import TurnScheduler
from geniai.domain.greeting import is_bare_greeting
from geniai.domain.human_request import mentions_human_request
from geniai.domain.texts import TEXT, truncate, with_unanswered_question
from geniai.domain.triage import PreLlmSignals, decide_turn, handoff_text, pre_llm_decision
from geniai.domain.types import (
    AnswerFaqQuestion,
    AskClarification,
    AskForText,
    Column,
    Decision,
    DecisionKind,
    Handoff,
    HandoffReason,
    InterpretedTurn,
    ReaskFeedback,
    ResolvedByBot,
    SendFaq,
    TriageState,
)
from geniai.llm.interpret import InterpretResult, interpret_turn
from geniai.llm.prompt import PromptCategory, PromptFaqItem, PromptMessage, PromptSentFaq, TurnContext

TurnOutcome = Literal["greeting"] | DecisionKind


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@dataclass
class _Timing:
    """How long the steps of a turn took, logged in one line once its reply is in the outbox: never the
    content nor the phone. The Chatwoot send has its own line (app/outbox.py)."""

    started: float = field(default_factory=time.perf_counter)
    wait_ms: int = 0
    """From the last customer message to the start of the turn: the burst window and any queue."""
    images_ms: int | None = None
    """Downloading the turn's images, when there was any download."""
    llm: InterpretResult | None = None

    def log(self, deps: Deps, ticket_id: int, outcome: TurnOutcome) -> None:
        line: dict[str, object] = {"ticketId": ticket_id, "outcome": outcome, "waitMs": self.wait_ms}
        if self.images_ms is not None:
            line["imagesMs"] = self.images_ms
        if self.llm is not None:
            line["llmMs"] = list(self.llm.attempts_ms)
            line["llmOutcomes"] = list(self.llm.outcomes)
            line["llmRetried"] = len(self.llm.outcomes) > 1
        line["toOutboxMs"] = _ms_since(self.started)
        deps.log.info(line, "turn timing")


def pending_customer_messages(messages: list[MessageRow], consumed_id: int | None) -> list[MessageRow]:
    """Customer messages no turn has read yet. One stored while a turn was running stays pending even
    though that turn's reply is stored after it."""
    return [m for m in messages if m.author == "customer" and m.id > (consumed_id or 0)]


def _state_of(t: TicketRow) -> TriageState:
    return TriageState(
        faq_attempted=t.faq_attempted,
        clarifications_asked=t.clarifications_asked,
        unclear_feedback_reasks=t.unclear_feedback_reasks,
        media_prompts=t.media_prompts,
        faq_questions_answered=t.faq_questions_answered,
    )


async def build_turn_context(
    deps: Deps, conn: AsyncConnection, t: TicketRow, messages: list[MessageRow], images: TurnImages
) -> TurnContext:
    if t.attendant_id is None:
        raise ValueError(f"ticket {t.id} has no attendant")
    who = await get_attendant_with_unit(conn, t.attendant_id)
    categories = [c for c in await list_active_categories(conn) if c.key != "unidentified"]
    faq_items = await list_active_faq_items(conn)
    new = pending_customer_messages(messages, t.last_consumed_message_id)
    new_ids = {m.id for m in new}
    sent_faq: PromptSentFaq | None = None
    if t.faq_attempted and t.faq_item_id is not None:
        # Only the entry sent: questions about it are answered from its own knowledge base.
        sent = await get_faq_item(conn, t.faq_item_id)
        if sent is not None:
            sent_faq = PromptSentFaq(
                id=sent.id, title=sent.title, answer_text=sent.answer_text, knowledge_base=sent.knowledge_base
            )
    return TurnContext(
        attendant_name=who.name,
        unit_name=who.unit_name,
        categories=[PromptCategory(id=c.id, system=c.system, name=c.name) for c in categories],
        faq_items=[
            PromptFaqItem(id=f.id, category_id=f.category_id, title=f.title, applies_when=f.applies_when)
            for f in faq_items
        ],
        messages=[
            PromptMessage(author=m.author, text=message_text(m, images)) for m in messages if m.id not in new_ids
        ],
        new_messages=[PromptMessage(author=m.author, text=message_text(m, images)) for m in new],
        state=_state_of(t),
        max_clarifications=deps.rules.max_clarifications,
        sent_faq=sent_faq,
        max_faq_questions=deps.rules.max_faq_questions,
        images=images.images,
    )


async def run_turn(
    queue: KeyedQueue, deps: Deps, conversation_id: int, scheduler: TurnScheduler | None = None
) -> TurnOutcome | None:
    """How the scheduler runs a turn: one at a time per conversation, apart from its webhooks. A turn that
    closed the ticket may have opened a new one for messages that arrived during it: its turn is due."""
    outcome = await queue.run(turn_key(conversation_id), lambda: process_turn(deps, conversation_id))
    if outcome == "resolved_by_bot" and scheduler is not None:
        scheduler.schedule(conversation_id)
    return outcome


async def _claim(conn: AsyncConnection, t: TicketRow, consumed_id: int) -> bool:
    """Locks the ticket and checks the turn still applies, then marks its messages as read. It does not
    when a person moved the ticket out of triage meanwhile: the turn then sends nothing."""
    current = await get_ticket(conn, t.id, lock=True)
    if current is None or current.column != "in_triage":
        return False
    if current.last_consumed_message_id != t.last_consumed_message_id:
        return False
    await update_ticket(conn, t.id, {"last_consumed_message_id": consumed_id})
    return True


async def _carry_late_messages(deps: Deps, conn: AsyncConnection, t: TicketRow, consumed_id: int) -> None:
    """The ticket was just closed. Customer messages that arrived while the turn was running may be another
    problem, so they open a new ticket, identified like any first message (spec §5.1 step 8)."""
    late = pending_customer_messages(await list_messages(conn, t.id), consumed_id)
    if not late:
        return
    now = deps.now()
    first_text = next((m.text for m in late if not m.is_media), message_text(late[0]))
    opened = await open_ticket_for(conn, t.chatwoot_conversation_id, t.phone_e164, first_text, now)
    await move_messages(conn, [m.id for m in late], opened.ticket_id)
    if opened.identified:
        # The close just queued "resolved"; triage runs in "pending".
        await enqueue_status(conn, t.chatwoot_conversation_id, "pending")
    else:
        await acknowledge_unidentified(conn, t.chatwoot_conversation_id, opened.ticket_id, now)


async def process_turn(deps: Deps, conversation_id: int) -> TurnOutcome | None:
    """Processes the pending customer messages of a conversation as one turn (spec §5.1 steps 3-10).
    Reads, then decides (the LLM runs outside any open transaction), then writes the state with the
    bot message stored first, then sends (spec §10). Returns None when there was nothing to do or the
    decision no longer applied (see _claim). Images are downloaded outside any transaction too, and only
    when the LLM may be called (see app/attachments.py).
    """
    decision: Decision | None = None
    greeting: str | None = None
    timing = _Timing()
    async with deps.engine.connect() as conn:
        t = await find_open_ticket(conn, conversation_id)
        if t is None or t.column != "in_triage":
            return None
        messages = await list_messages(conn, t.id)
        pending = pending_customer_messages(messages, t.last_consumed_message_id)
        if not pending:
            return None
        consumed_id = pending[-1].id
        timing.wait_ms = max(0, round((deps.now() - pending[-1].at).total_seconds() * 1000))

        text = "\n".join(m.text for m in pending if not m.is_media)
        keyword_human_request = mentions_human_request(text)

        if not any(m.author == "bot" for m in messages):
            if keyword_human_request:
                decision = Handoff("human_requested")
            else:
                if t.attendant_id is None:
                    raise ValueError(f"ticket {t.id} has no attendant")
                who = await get_attendant_with_unit(conn, t.attendant_id)
                # A first message that already says something is kept for the next turn: the greeting
                # then only asks the customer to confirm who they are.
                bare = is_bare_greeting(
                    [m.text for m in pending if not m.is_media],
                    has_media=any(m.is_media or m.attachments for m in pending),
                )
                greet = TEXT.greeting if bare else TEXT.greeting_with_content
                greeting = greet(who.name, who.unit_name)
        elif keyword_human_request:
            # Before any download: a request for a person needs nothing from the images.
            decision = pre_llm_decision(_state_of(t), PreLlmSignals(True, nothing_legible=False), deps.rules)
        await conn.rollback()

    if greeting is not None:
        async with deps.engine.begin() as conn:
            if not await _claim(conn, t, consumed_id):
                return None
            await add_message(conn, NewMessage(ticket_id=t.id, author="bot", text=greeting, at=deps.now()))
            await enqueue_message(conn, conversation_id, greeting)
        deps.outbox.wake()
        timing.log(deps, t.id, "greeting")
        return "greeting"

    if decision is not None:
        return await _apply(deps, t, messages, consumed_id, decision, None, timing)

    images = TurnImages()
    if may_be_legible(pending):
        downloads = time.perf_counter()
        images = await read_images(deps, t.id, messages)
        if deps.media is not None and (images.images or images.failed):
            timing.images_ms = _ms_since(downloads)
    if not is_legible(pending, images):
        signals = PreLlmSignals(False, nothing_legible=True, unread=unread_media(pending, deps.media is not None))
        decision = pre_llm_decision(_state_of(t), signals, deps.rules)
        assert decision is not None
        return await _apply(deps, t, messages, consumed_id, decision, None, timing)

    async with deps.engine.connect() as conn:
        ctx = await build_turn_context(deps, conn, t, messages, images)
        await conn.rollback()
    result = await interpret_turn(deps.llm, ctx, deps.rules)
    timing.llm = result
    if not result.ok or result.turn is None:
        deps.log.warn({"ticketId": t.id, "error": result.error}, "LLM failed; handing over")
        return await _apply(deps, t, messages, consumed_id, Handoff("llm_failure"), None, timing)
    turn = result.turn
    decision = decide_turn(_state_of(t), turn, deps.rules)
    return await _apply(deps, t, messages, consumed_id, decision, turn, timing, images)


@dataclass(frozen=True)
class _Written:
    kind: DecisionKind
    reply: str
    move: tuple[Column, Column] | None
    handoff_reason: HandoffReason | None


async def _write_decision(
    deps: Deps, conn: AsyncConnection, t: TicketRow, decision: Decision, turn: InterpretedTurn | None
) -> _Written:
    """Writes the ticket state of a decision and returns the bot reply (stored by the caller)."""
    now = deps.now()
    match decision:
        case Handoff(reason=reason):
            moved = await move_ticket(conn, t.id, "awaiting_human", "bot", now, {"handoff_reason": reason})
            # The code decided the handoff; the LLM, when it read the turn as one, words it.
            reply = handoff_text(turn, TEXT.handoff)
            return _Written("handoff", reply, (moved.from_, "awaiting_human"), reason)
        case SendFaq(faq_item_id=faq_item_id):
            faq = await get_faq_item(conn, faq_item_id)
            if faq is None:
                return await _write_decision(deps, conn, t, Handoff("no_faq_match"), turn)
            await update_ticket(conn, t.id, {"faq_attempted": True, "faq_item_id": faq.id})
            # The procedure is always the team's verbatim text; the LLM only frames it.
            parts = [turn.reply if turn else "", faq.answer_text, TEXT.faq_follow_up]
            reply = "\n\n".join(p.strip() for p in parts if p.strip())
            return _Written("send_faq", reply, None, None)
        case AskClarification():
            await update_ticket(conn, t.id, {"clarifications_asked": t.clarifications_asked + 1})
            reply = (turn.reply.strip() if turn else "") or TEXT.clarify_fallback
            return _Written("ask_clarification", reply, None, None)
        case ReaskFeedback():
            await update_ticket(conn, t.id, {"unclear_feedback_reasks": t.unclear_feedback_reasks + 1})
            return _Written("reask_feedback", TEXT.reask_feedback, None, None)
        case AskForText(unread=unread):
            await update_ticket(conn, t.id, {"media_prompts": t.media_prompts + 1})
            return _Written("ask_for_text", TEXT.ask_for_text_for(unread), None, None)
        case ResolvedByBot():
            moved = await move_ticket(conn, t.id, "resolved_by_bot", "bot", now)
            return _Written("resolved_by_bot", TEXT.resolved_thanks, (moved.from_, "resolved_by_bot"), None)
        case AnswerFaqQuestion():
            await update_ticket(conn, t.id, {"faq_questions_answered": t.faq_questions_answered + 1})
            # The ticket stays in triage, awaiting the feedback on the FAQ entry.
            parts = [turn.reply if turn else "", TEXT.faq_follow_up]
            reply = "\n\n".join(p.strip() for p in parts if p.strip())
            return _Written("answer_faq_question", reply, None, None)


async def _apply(
    deps: Deps,
    t: TicketRow,
    messages: list[MessageRow],
    consumed_id: int,
    decision: Decision,
    turn: InterpretedTurn | None,
    timing: _Timing,
    images: TurnImages | None = None,
) -> TurnOutcome | None:
    """With the LLM's turn, records what it saw of the turn's images."""
    async with deps.engine.begin() as conn:
        if not await _claim(conn, t, consumed_id):
            return None
        if turn is not None:
            read = {m.id: m for m in with_outcomes(messages, images, turn.image_descriptions)} if images else {}
            for m in read.values():
                await set_message_attachments(conn, m.id, m.attachments)
            summary = turn.summary
            if turn.faq_feedback == "question" and isinstance(decision, Handoff):
                # The team gets the question the bot did not answer, in the customer's words; an image by
                # what the LLM saw in it.
                pending = pending_customer_messages(messages, t.last_consumed_message_id)
                question = " / ".join(message_text(read.get(m.id, m)) for m in pending)
                summary = with_unanswered_question(summary, question)
            patch: dict[str, object] = {
                "summary": summary,
                "category_id": turn.category_id,
                "bot_category_id": turn.category_id,
            }
            await update_ticket(conn, t.id, patch)
        written = await _write_decision(deps, conn, t, decision, turn)
        await add_message(conn, NewMessage(ticket_id=t.id, author="bot", text=written.reply, at=deps.now()))
        await enqueue_message(conn, t.chatwoot_conversation_id, written.reply)
        if written.move is not None:
            await enqueue_status_after_move(conn, t.chatwoot_conversation_id, *written.move)
        if written.kind == "resolved_by_bot":
            await _carry_late_messages(deps, conn, t, consumed_id)
    deps.outbox.wake()
    timing.log(deps, t.id, written.kind)
    summary = turn.summary if turn is not None else t.summary
    if written.handoff_reason is not None and summary == "":
        # Its own task: the turn ends here, and the summary waits for the LLM to be free.
        deps.summaries.start(_fill_missing_summary(deps, t, messages, written.handoff_reason))
    return written.kind


async def _fill_missing_summary(deps: Deps, t: TicketRow, messages: list[MessageRow], reason: HandoffReason) -> None:
    """A handoff before any LLM result leaves the card without a summary. After the customer was
    answered, and apart from the turn, it asks the LLM once more, once the LLM is free (see
    app/card_summaries.py), within summary_deadline_ms counting that wait. Past the deadline, or when the
    LLM fails, the card gets the customer's own words under "other". Logs `card summary` without the
    content nor the phone.
    """
    started = time.perf_counter()
    try:
        wait_started: float | None = None
        waited_ms: int | None = None
        result: InterpretResult | None = None
        if reason != "llm_failure":
            try:
                async with asyncio.timeout(deps.rules.summary_deadline_ms / 1000):
                    images = await read_images(deps, t.id, messages)
                    async with deps.engine.connect() as conn:
                        ctx = await build_turn_context(deps, conn, t, messages, images)
                        await conn.rollback()
                    wait_started = time.perf_counter()
                    async with deps.summaries.llm_turn():
                        waited_ms = _ms_since(wait_started)
                        result = await interpret_turn(deps.llm, ctx, deps.rules)
            except TimeoutError:
                if waited_ms is None and wait_started is not None:
                    waited_ms = _ms_since(wait_started)
        found = result.turn if result is not None and result.ok else None
        async with deps.engine.begin() as conn:
            if found is not None:
                patch: dict[str, object] = {
                    "summary": found.summary,
                    "category_id": found.category_id,
                    "bot_category_id": found.category_id,
                }
            else:
                words = " / ".join(message_text(m) for m in messages if m.author == "customer")
                other = await get_category_id_by_key(conn, "other")
                patch = {"summary": truncate(words, 280), "category_id": other}
            await update_ticket(conn, t.id, patch)
        line: dict[str, object] = {
            "ticketId": t.id,
            "waitedMs": waited_ms or 0,
            "llmMs": list(result.attempts_ms) if result is not None else [],
            "llmOutcomes": list(result.outcomes) if result is not None else [],
            "fallback": found is None,
        }
        deps.log.info(line, "card summary")
    except Exception as err:  # reported, never raised into the event loop
        deps.log.error({"err": err, "ticketId": t.id, "ms": _ms_since(started)}, "card summary failed")
