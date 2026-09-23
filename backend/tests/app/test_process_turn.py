import itertools

import pytest
from sqlalchemy import select

from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.process_turn import TurnOutcome, pending_customer_messages, process_turn
from geniai.app.tickets_repo import MessageRow, TicketRow
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.db.fixtures import FICTITIOUS
from geniai.db.schema import ticket
from geniai.domain.texts import TEXT
from geniai.domain.types import MessageAuthor
from tests.conftest import START, Harness
from tests.support.fakes import StatusSet, texts, turn_json

_message_ids = itertools.count(1)
_conversations = itertools.count(100)


class Chat:
    """The customer side of the conversation: receive a message, run a turn, get greeted."""

    def __init__(self, h: Harness) -> None:
        self.h = h
        self.scheduler = RecordingScheduler()

    async def receive(self, conversation_id: int, text: str, has_media: bool = False) -> None:
        msg = IncomingMessage(
            message_id=next(_message_ids),
            conversation_id=conversation_id,
            phone=self.h.seed.attendants["ana"].phone,
            text=text,
            has_media=has_media,
            conversation_status=None,
        )
        await handle_inbound_message(self.h.deps, self.scheduler, msg)

    async def customer(self, conversation_id: int, text: str, has_media: bool = False) -> TurnOutcome | None:
        await self.receive(conversation_id, text, has_media)
        return await process_turn(self.h.deps, conversation_id)

    async def greeted(self) -> int:
        conversation_id = next(_conversations)
        assert await self.customer(conversation_id, "oi") == "greeting"
        return conversation_id

    async def faq_sent(self) -> int:
        conversation_id = await self.greeted()
        self.h.llm.push(turn_json(category_id=self.h.seed.categories["login"], faq_item_id=self.h.seed.faq["password"]))
        assert await self.customer(conversation_id, "esqueci a senha") == "send_faq"
        return conversation_id

    async def ticket_of(self, conversation_id: int) -> TicketRow:
        async with self.h.begin() as conn:
            query = (
                select(ticket)
                .where(ticket.c.chatwoot_conversation_id == conversation_id)
                .order_by(ticket.c.id.desc())
                .limit(1)
            )
            return TicketRow(**(await conn.execute(query)).one()._mapping)

    def last_sent(self) -> str:
        return self.h.chatwoot.sent[-1].text if self.h.chatwoot.sent else ""


@pytest.fixture
def chat(h: Harness) -> Chat:
    return Chat(h)


async def test_greets_with_the_registered_name_and_unit_without_calling_the_llm(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    assert h.llm.requests == []
    assert "Ana Exemplo" in chat.last_sent()
    assert "Unidade Exemplo Centro" in chat.last_sent()
    assert (await chat.ticket_of(conversation_id)).column == "in_triage"


async def test_hands_over_at_once_when_the_first_message_asks_for_a_human_then_fills_the_summary(
    h: Harness, chat: Chat
) -> None:
    conversation_id = next(_conversations)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], summary="Pede atendente; painel não abre."))
    assert await chat.customer(conversation_id, "quero falar com um atendente") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert t.column == "awaiting_human"
    assert t.handoff_reason == "human_requested"
    assert t.summary == "Pede atendente; painel não abre."
    assert t.category_id == h.seed.categories["login"]
    assert t.bot_category_id == h.seed.categories["login"]
    assert texts(h.chatwoot.sent) == [TEXT.handoff]
    assert h.chatwoot.statuses == [StatusSet(conversation_id, "open")]


async def test_hands_over_on_a_human_request_even_when_the_llm_is_down(h: Harness, chat: Chat) -> None:
    conversation_id = next(_conversations)
    h.llm.push(RuntimeError("down"), RuntimeError("down"))
    assert await chat.customer(conversation_id, "quero falar com um atendente") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert t.column == "awaiting_human"
    assert t.handoff_reason == "human_requested"
    assert t.summary == "quero falar com um atendente"
    assert t.category_id == h.seed.categories["other"]
    assert t.bot_category_id is None
    assert chat.last_sent() == TEXT.handoff


async def test_sends_the_faq_entry_verbatim_with_the_llm_framing_and_asks_if_it_worked(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(
        turn_json(
            category_id=h.seed.categories["login"],
            faq_item_id=h.seed.faq["password"],
            reply="Isso costuma resolver:",
        )
    )
    assert await chat.customer(conversation_id, "sim, esqueci a senha do painel") == "send_faq"
    assert "Isso costuma resolver:" in chat.last_sent()
    assert FICTITIOUS["faq"]["password"]["answer_text"] in chat.last_sent()
    assert TEXT.faq_follow_up in chat.last_sent()
    assert chat.last_sent() == "\n\n".join(
        ["Isso costuma resolver:", FICTITIOUS["faq"]["password"]["answer_text"], TEXT.faq_follow_up]
    )
    t = await chat.ticket_of(conversation_id)
    assert t.faq_attempted is True
    assert t.faq_item_id == h.seed.faq["password"]
    assert t.category_id == h.seed.categories["login"]
    assert t.bot_category_id == h.seed.categories["login"]
    assert t.summary == "Resumo de teste"


async def test_closes_as_resolved_by_bot_when_the_customer_confirms(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="resolved"))
    assert await chat.customer(conversation_id, "sim, resolveu") == "resolved_by_bot"
    t = await chat.ticket_of(conversation_id)
    assert t.column == "resolved_by_bot"
    assert t.closed_at == h.now
    assert chat.last_sent() == TEXT.resolved_thanks
    assert h.chatwoot.statuses[-1] == StatusSet(conversation_id, "resolved")


async def test_hands_over_when_the_faq_did_not_help(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="not_resolved"))
    assert await chat.customer(conversation_id, "não resolveu") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.column, t.handoff_reason) == ("awaiting_human", "faq_not_resolved")


async def test_asks_again_once_on_an_unclear_answer_then_hands_over(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    h.llm.push(
        turn_json(category_id=h.seed.categories["login"], faq_feedback="unclear"),
        turn_json(category_id=h.seed.categories["login"], faq_feedback="unclear"),
    )
    assert await chat.customer(conversation_id, "hmm") == "reask_feedback"
    assert chat.last_sent() == TEXT.reask_feedback
    assert await chat.customer(conversation_id, "sei lá") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.unclear_feedback_reasks) == ("faq_not_resolved", 1)


async def test_asks_at_most_two_clarifying_questions_then_hands_over(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    for _ in range(3):
        h.llm.push(
            turn_json(category_id=h.seed.categories["other"], needs_clarification=True, reply="Em qual sistema?")
        )
    assert await chat.customer(conversation_id, "deu problema") == "ask_clarification"
    assert chat.last_sent() == "Em qual sistema?"
    assert await chat.customer(conversation_id, "no sistema") == "ask_clarification"
    assert await chat.customer(conversation_id, "aquele lá") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.clarifications_asked) == ("no_faq_match", 2)


async def test_honors_a_human_request_keyword_without_letting_the_llm_decide(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"]))
    assert await chat.customer(conversation_id, "me passa pra um atendente") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.faq_attempted) == ("human_requested", False)
    assert len(h.llm.requests) == 1


async def test_hands_over_with_llm_failure_when_the_llm_fails_twice(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(TimeoutError("timeout"), "not json")
    assert await chat.customer(conversation_id, "o painel não abre") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.category_id) == ("llm_failure", h.seed.categories["other"])
    assert "o painel não abre" in t.summary
    assert chat.last_sent() == TEXT.handoff
    assert len(h.logger.warnings) == 1


async def test_asks_for_text_on_media_then_hands_over_on_media_again(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    assert await chat.customer(conversation_id, "", True) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text
    assert h.llm.requests == []
    # The handoff then asks the LLM for a summary; with nothing scripted it falls back to the messages.
    assert await chat.customer(conversation_id, "", True) == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.media_prompts) == ("media", 1)


async def test_hands_over_on_a_registration_mismatch(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], registration_mismatch=True))
    assert await chat.customer(conversation_id, "não sou a Ana, sou de outra unidade") == "handoff"
    assert (await chat.ticket_of(conversation_id)).handoff_reason == "registration_mismatch"


async def test_processes_a_burst_as_one_turn(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    await chat.receive(conversation_id, "meu painel")
    await chat.receive(conversation_id, "não entra")
    h.llm.push(
        turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Aparece alguma mensagem?")
    )
    assert await process_turn(h.deps, conversation_id) == "ask_clarification"
    assert len(h.llm.requests) == 1
    assert "meu painel" in h.llm.requests[0].user
    assert "não entra" in h.llm.requests[0].user


async def test_does_nothing_without_pending_messages_or_outside_triage(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    assert await process_turn(h.deps, conversation_id) is None
    h.llm.push(turn_json(category_id=h.seed.categories["other"]))
    assert await chat.customer(conversation_id, "é outra coisa") == "handoff"
    await chat.receive(conversation_id, "alô?")
    assert await process_turn(h.deps, conversation_id) is None


async def test_keeps_the_ticket_state_when_chatwoot_is_down(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.chatwoot.fail_sends = True
    h.llm.push(turn_json(category_id=h.seed.categories["other"]))
    assert await chat.customer(conversation_id, "é outra coisa") == "handoff"
    assert (await chat.ticket_of(conversation_id)).column == "awaiting_human"
    assert len(h.logger.errors) > 0


def test_pending_customer_messages_are_the_ones_after_the_last_bot_message() -> None:
    def m(i: int, author: MessageAuthor) -> MessageRow:
        return MessageRow(
            id=i, ticket_id=1, author=author, text=str(i), is_media=False, at=START, chatwoot_message_id=None
        )

    messages = [m(1, "customer"), m(2, "bot"), m(3, "customer"), m(4, "customer")]
    assert [x.id for x in pending_customer_messages(messages)] == [3, 4]
    assert [x.id for x in pending_customer_messages([m(1, "customer")])] == [1]
    assert pending_customer_messages([m(1, "customer"), m(2, "bot")]) == []
