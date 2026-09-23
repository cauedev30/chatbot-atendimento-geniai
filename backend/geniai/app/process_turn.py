from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncConnection

from geniai.app.notify import safely, sync_chatwoot_status
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
    list_active_categories,
    list_active_faq_items,
    list_messages,
    move_ticket,
    update_ticket,
)
from geniai.domain.human_request import mentions_human_request
from geniai.domain.texts import TEXT, truncate
from geniai.domain.triage import PreLlmSignals, decide_turn, pre_llm_decision
from geniai.domain.types import (
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
from geniai.llm.interpret import interpret_turn
from geniai.llm.prompt import PromptCategory, PromptFaqItem, PromptMessage, TurnContext

TurnOutcome = Literal["greeting"] | DecisionKind


def pending_customer_messages(messages: list[MessageRow]) -> list[MessageRow]:
    last_bot = max((i for i, m in enumerate(messages) if m.author == "bot"), default=-1)
    return [m for m in messages[last_bot + 1 :] if m.author == "customer"]


def _state_of(t: TicketRow) -> TriageState:
    return TriageState(
        faq_attempted=t.faq_attempted,
        clarifications_asked=t.clarifications_asked,
        unclear_feedback_reasks=t.unclear_feedback_reasks,
        media_prompts=t.media_prompts,
    )


async def build_turn_context(
    deps: Deps, conn: AsyncConnection, t: TicketRow, messages: list[MessageRow]
) -> TurnContext:
    if t.attendant_id is None:
        raise ValueError(f"ticket {t.id} has no attendant")
    who = await get_attendant_with_unit(conn, t.attendant_id)
    categories = [c for c in await list_active_categories(conn) if c.key != "unidentified"]
    faq_items = await list_active_faq_items(conn)
    return TurnContext(
        attendant_name=who.name,
        unit_name=who.unit_name,
        categories=[PromptCategory(id=c.id, system=c.system, name=c.name) for c in categories],
        faq_items=[
            PromptFaqItem(id=f.id, category_id=f.category_id, title=f.title, applies_when=f.applies_when)
            for f in faq_items
        ],
        messages=[PromptMessage(author=m.author, text=m.text) for m in messages],
        state=_state_of(t),
        max_clarifications=deps.rules.max_clarifications,
    )


async def _send(deps: Deps, t: TicketRow, text: str) -> None:
    await safely(deps.log, "send message", lambda: deps.chatwoot.send_message(t.chatwoot_conversation_id, text))


async def process_turn(deps: Deps, conversation_id: int) -> TurnOutcome | None:
    """Processes the pending customer messages of a conversation as one turn (spec §5.1 steps 3-10).
    Reads, then decides (the LLM runs outside any open transaction), then writes the state with the
    bot message stored first, then sends (spec §10).
    """
    ctx: TurnContext | None = None
    decision: Decision | None = None
    async with deps.engine.connect() as conn:
        t = await find_open_ticket(conn, conversation_id)
        if t is None or t.column != "in_triage":
            return None
        messages = await list_messages(conn, t.id)
        pending = pending_customer_messages(messages)
        if not pending:
            return None

        text = "\n".join(m.text for m in pending if not m.is_media)
        keyword_human_request = mentions_human_request(text)

        if not any(m.author == "bot" for m in messages):
            if keyword_human_request:
                decision = Handoff("human_requested")
            else:
                if t.attendant_id is None:
                    raise ValueError(f"ticket {t.id} has no attendant")
                who = await get_attendant_with_unit(conn, t.attendant_id)
                greeting = TEXT.greeting(who.name, who.unit_name)
        else:
            state = _state_of(t)
            only_media = all(m.is_media for m in pending)
            decision = pre_llm_decision(state, PreLlmSignals(keyword_human_request, only_media), deps.rules)
            if decision is None:
                ctx = await build_turn_context(deps, conn, t, messages)
        await conn.rollback()

    if decision is None and ctx is None:
        async with deps.engine.begin() as conn:
            await add_message(conn, NewMessage(ticket_id=t.id, author="bot", text=greeting, at=deps.now()))
        await _send(deps, t, greeting)
        return "greeting"

    if decision is not None:
        return await _apply(deps, t, messages, decision, None)

    assert ctx is not None
    result = await interpret_turn(deps.llm, ctx, deps.rules)
    if not result.ok or result.turn is None:
        deps.log.warn({"ticketId": t.id, "error": result.error}, "LLM failed; handing over")
        return await _apply(deps, t, messages, Handoff("llm_failure"), None)
    turn = result.turn
    return await _apply(deps, t, messages, decide_turn(_state_of(t), turn, deps.rules), turn)


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
            return _Written("handoff", TEXT.handoff, (moved.from_, "awaiting_human"), reason)
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
        case AskForText():
            await update_ticket(conn, t.id, {"media_prompts": t.media_prompts + 1})
            return _Written("ask_for_text", TEXT.ask_for_text, None, None)
        case ResolvedByBot():
            moved = await move_ticket(conn, t.id, "resolved_by_bot", "bot", now)
            return _Written("resolved_by_bot", TEXT.resolved_thanks, (moved.from_, "resolved_by_bot"), None)


async def _apply(
    deps: Deps, t: TicketRow, messages: list[MessageRow], decision: Decision, turn: InterpretedTurn | None
) -> TurnOutcome:
    async with deps.engine.begin() as conn:
        if turn is not None:
            patch: dict[str, object] = {
                "summary": turn.summary,
                "category_id": turn.category_id,
                "bot_category_id": turn.category_id,
            }
            await update_ticket(conn, t.id, patch)
        written = await _write_decision(deps, conn, t, decision, turn)
        await add_message(conn, NewMessage(ticket_id=t.id, author="bot", text=written.reply, at=deps.now()))

    await _send(deps, t, written.reply)
    if written.move is not None:
        await sync_chatwoot_status(deps, t.chatwoot_conversation_id, *written.move)
    summary = turn.summary if turn is not None else t.summary
    if written.handoff_reason is not None and summary == "":
        await _fill_missing_summary(deps, t, messages, written.handoff_reason)
    return written.kind


async def _fill_missing_summary(deps: Deps, t: TicketRow, messages: list[MessageRow], reason: HandoffReason) -> None:
    """A handoff before any LLM result leaves the card without a summary. Try the LLM once more for it,
    after the customer was already answered; on failure fall back to the customer's own words.
    """
    if reason != "llm_failure":
        async with deps.engine.connect() as conn:
            ctx = await build_turn_context(deps, conn, t, messages)
            await conn.rollback()
        result = await interpret_turn(deps.llm, ctx, deps.rules)
        if result.ok and result.turn is not None:
            async with deps.engine.begin() as conn:
                patch: dict[str, object] = {
                    "summary": result.turn.summary,
                    "category_id": result.turn.category_id,
                    "bot_category_id": result.turn.category_id,
                }
                await update_ticket(conn, t.id, patch)
            return
    words = " / ".join(m.text for m in messages if m.author == "customer")
    async with deps.engine.begin() as conn:
        other = await get_category_id_by_key(conn, "other")
        await update_ticket(conn, t.id, {"summary": truncate(words, 280), "category_id": other})
