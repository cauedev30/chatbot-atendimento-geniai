import asyncio
import itertools
import json

import pytest
from sqlalchemy import select, update

from geniai.app.board import take_card
from geniai.app.handle_inbound import handle_inbound_message
from geniai.app.keyed_queue import KeyedQueue
from geniai.app.ports import LlmRequest
from geniai.app.process_turn import TurnOutcome, pending_customer_messages, process_turn, run_turn
from geniai.app.silence_sweeper import sweep_silent_tickets
from geniai.app.tickets_repo import MessageRow, TicketRow, list_messages
from geniai.app.turn_scheduler import RecordingScheduler
from geniai.chatwoot.webhook import IncomingMessage
from geniai.db.fixtures import FICTITIOUS
from geniai.db.schema import attendant, ticket
from geniai.domain.texts import TEXT
from geniai.domain.types import Attachment, MessageAuthor
from tests.conftest import START, Harness
from tests.support.fakes import StatusSet, texts, turn_json

_message_ids = itertools.count(1)
_conversations = itertools.count(100)
PHRASE = "Para um atendimento mais preciso, vou te encaminhar para a equipe de suporte."


class Chat:
    """The customer side of the conversation: receive a message, run a turn, get greeted."""

    def __init__(self, h: Harness) -> None:
        self.h = h
        self.scheduler = RecordingScheduler()

    async def receive(self, conversation_id: int, text: str, *attachments: Attachment) -> None:
        msg = IncomingMessage(
            message_id=next(_message_ids),
            conversation_id=conversation_id,
            phone=self.h.seed.attendants["ana"].phone,
            text=text,
            conversation_status=None,
            attachments=attachments,
        )
        await handle_inbound_message(self.h.deps, self.scheduler, msg)
        await self.h.settle()

    async def customer(self, conversation_id: int, text: str, *attachments: Attachment) -> TurnOutcome | None:
        await self.receive(conversation_id, text, *attachments)
        outcome = await process_turn(self.h.deps, conversation_id)
        await self.h.settle()
        return outcome

    async def greeted(self) -> int:
        conversation_id = next(_conversations)
        assert await self.customer(conversation_id, "oi") == "greeting"
        return conversation_id

    async def faq_sent(self, faq: str = "password", category: str = "login") -> int:
        conversation_id = await self.greeted()
        self.h.llm.push(turn_json(category_id=self.h.seed.categories[category], faq_item_id=self.h.seed.faq[faq]))
        assert await self.customer(conversation_id, "esqueci a senha") == "send_faq"
        return conversation_id

    async def asks(
        self,
        conversation_id: int,
        text: str,
        reply: str = "",
        found: bool = True,
        summary: str = "Resumo de teste",
        handoff_reply: str = "",
    ) -> TurnOutcome | None:
        """The customer asks a question about the FAQ entry sent; the LLM answers it from the knowledge base or not."""
        self.h.llm.push(
            turn_json(
                category_id=self.h.seed.categories["login"],
                faq_feedback="question",
                faq_answer_found=found,
                reply=reply,
                summary=summary,
                handoff_reply=handoff_reply,
            )
        )
        return await self.customer(conversation_id, text)

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
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="not_resolved", handoff_reply=PHRASE))
    assert await chat.customer(conversation_id, "não resolveu") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.column, t.handoff_reason) == ("awaiting_human", "faq_not_resolved")
    assert chat.last_sent() == PHRASE


async def test_asks_again_once_on_an_unclear_answer_then_hands_over(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    h.llm.push(
        turn_json(category_id=h.seed.categories["login"], faq_feedback="unclear", handoff_reply=PHRASE),
        turn_json(category_id=h.seed.categories["login"], faq_feedback="unclear", handoff_reply=PHRASE),
    )
    assert await chat.customer(conversation_id, "hmm") == "reask_feedback"
    assert chat.last_sent() == TEXT.reask_feedback
    assert await chat.customer(conversation_id, "sei lá") == "handoff"
    assert chat.last_sent() == PHRASE
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.unclear_feedback_reasks) == ("faq_not_resolved", 1)


async def test_asks_at_most_two_clarifying_questions_then_hands_over(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    for _ in range(3):
        h.llm.push(
            turn_json(
                category_id=h.seed.categories["other"],
                needs_clarification=True,
                reply="Em qual sistema?",
                handoff_reply=PHRASE,
            )
        )
    assert await chat.customer(conversation_id, "deu problema") == "ask_clarification"
    assert chat.last_sent() == "Em qual sistema?"
    assert await chat.customer(conversation_id, "no sistema") == "ask_clarification"
    assert await chat.customer(conversation_id, "aquele lá") == "handoff"
    # A limit only the code knows: the LLM's reading asked for a clarification, so the fixed text goes.
    assert chat.last_sent() == TEXT.handoff
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.clarifications_asked) == ("no_faq_match", 2)


async def test_honors_a_human_request_keyword_without_letting_the_llm_decide(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(
        turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"], handoff_reply=PHRASE)
    )
    assert await chat.customer(conversation_id, "me passa pra um atendente") == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.faq_attempted) == ("human_requested", False)
    assert len(h.llm.requests) == 1
    # The handoff came before any LLM reading (its only call is for the card summary): the fixed text goes.
    assert texts(h.chatwoot.sent)[-1] == TEXT.handoff


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
    assert await chat.customer(conversation_id, "", Attachment("audio")) == "ask_for_text"
    assert chat.last_sent() == TEXT.ask_for_text
    assert h.llm.requests == []
    # The handoff then asks the LLM for a summary; with nothing scripted it falls back to the messages.
    assert await chat.customer(conversation_id, "", Attachment("audio")) == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.handoff_reason, t.media_prompts) == ("media", 1)


async def test_hands_over_on_a_registration_mismatch(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["login"], registration_mismatch=True, handoff_reply=PHRASE))
    assert await chat.customer(conversation_id, "não sou a Ana, sou de outra unidade") == "handoff"
    assert (await chat.ticket_of(conversation_id)).handoff_reason == "registration_mismatch"
    assert chat.last_sent() == PHRASE


async def test_a_handoff_when_no_faq_entry_fits_sends_the_llm_sentence(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["other"], handoff_reply=f"  {PHRASE}  "))
    assert await chat.customer(conversation_id, "preciso mudar o plano") == "handoff"
    assert (await chat.ticket_of(conversation_id)).handoff_reason == "no_faq_match"
    assert chat.last_sent() == PHRASE


async def test_a_handoff_the_llm_wrote_no_sentence_for_sends_the_fixed_text(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(turn_json(category_id=h.seed.categories["other"], handoff_reply="   "))
    assert await chat.customer(conversation_id, "é outra coisa") == "handoff"
    assert (await chat.ticket_of(conversation_id)).handoff_reason == "no_faq_match"
    assert chat.last_sent() == TEXT.handoff


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


def test_pending_customer_messages_are_the_ones_after_the_last_consumed_one() -> None:
    def m(i: int, author: MessageAuthor) -> MessageRow:
        return MessageRow(
            id=i, ticket_id=1, author=author, text=str(i), is_media=False, at=START, chatwoot_message_id=None
        )

    # A message stored while a turn was running lands before that turn's reply, and is still pending.
    messages = [m(1, "customer"), m(2, "customer"), m(3, "bot"), m(4, "customer")]
    assert [x.id for x in pending_customer_messages(messages, 1)] == [2, 4]
    assert [x.id for x in pending_customer_messages(messages, None)] == [1, 2, 4]
    assert pending_customer_messages(messages, 4) == []


class SlowLlm:
    """Holds every LLM call until released, to act while a turn is in progress."""

    def __init__(self, h: Harness) -> None:
        self.release = asyncio.Event()
        complete = h.llm.complete

        async def slow(request: LlmRequest) -> str:
            await self.release.wait()
            return await complete(request)

        h.llm.complete = slow  # type: ignore[method-assign]


async def close_while_a_message_arrives(h: Harness, chat: Chat, late: str) -> int:
    """The customer confirms the FAQ worked; while the LLM reads that, another message arrives."""
    conversation_id = await chat.faq_sent()
    await chat.receive(conversation_id, "sim, resolveu")
    llm = SlowLlm(h)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="resolved"))
    turn = asyncio.create_task(run_turn(KeyedQueue(), h.deps, conversation_id, chat.scheduler))
    await asyncio.sleep(0.05)
    await chat.receive(conversation_id, late)
    llm.release.set()
    assert await turn == "resolved_by_bot"
    await h.settle()
    return conversation_id


async def test_closes_the_ticket_and_opens_a_new_one_for_a_message_that_arrived_during_the_turn(
    h: Harness, chat: Chat
) -> None:
    conversation_id = await close_while_a_message_arrives(h, chat, "ah, e a impressora também parou")
    async with h.begin() as conn:
        rows = (
            await conn.execute(
                select(ticket.c.id, ticket.c.column)
                .where(ticket.c.chatwoot_conversation_id == conversation_id)
                .order_by(ticket.c.id)
            )
        ).all()
    assert [r.column for r in rows] == ["resolved_by_bot", "in_triage"]
    closed, new = rows[0].id, rows[1].id
    async with h.begin() as conn:
        assert [m.text for m in await list_messages(conn, new)] == ["ah, e a impressora também parou"]
        assert "ah, e a impressora também parou" not in [m.text for m in await list_messages(conn, closed)]
    assert chat.last_sent() == TEXT.resolved_thanks
    assert h.chatwoot.statuses[-2:] == [StatusSet(conversation_id, "resolved"), StatusSet(conversation_id, "pending")]
    # The new ticket's turn is due: it is greeted like any first message.
    assert chat.scheduler.scheduled[-1] == conversation_id
    assert await process_turn(h.deps, conversation_id) == "greeting"


async def test_a_late_message_from_a_number_no_longer_registered_goes_to_a_person(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    await chat.receive(conversation_id, "sim, resolveu")
    llm = SlowLlm(h)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="resolved"))
    turn = asyncio.create_task(process_turn(h.deps, conversation_id))
    await asyncio.sleep(0.05)
    await chat.receive(conversation_id, "outra coisa")
    async with h.begin() as conn:
        await conn.execute(update(attendant).where(attendant.c.id == h.seed.attendants["ana"].id).values(active=False))
    llm.release.set()
    assert await turn == "resolved_by_bot"
    await h.settle()
    new = await chat.ticket_of(conversation_id)
    assert (new.column, new.handoff_reason, new.summary) == ("awaiting_human", "unidentified", "outra coisa")
    assert texts(h.chatwoot.sent)[-2:] == [TEXT.resolved_thanks, TEXT.unidentified_ack]
    assert h.chatwoot.statuses[-1] == StatusSet(conversation_id, "open")


async def test_a_message_that_arrived_during_a_turn_reaches_the_llm_as_new_in_the_next_turn(
    h: Harness, chat: Chat
) -> None:
    conversation_id = await chat.greeted()
    await chat.receive(conversation_id, "demora, o painel ficou vago")
    llm = SlowLlm(h)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="O que demora?"))
    turn = asyncio.create_task(process_turn(h.deps, conversation_id))
    await asyncio.sleep(0.05)
    await chat.receive(conversation_id, "e mais uma coisa: esqueci a senha")
    llm.release.set()
    assert await turn == "ask_clarification"
    await h.settle()
    assert chat.last_sent() == "O que demora?"

    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"]))
    assert await process_turn(h.deps, conversation_id) == "send_faq"
    payload = json.loads(h.llm.requests[-1].user)
    # Stored before the bot's question, but still what the customer is waiting an answer to.
    assert payload["new_messages"] == ["e mais uma coisa: esqueci a senha"]
    assert [m["text"] for m in payload["conversation"]][-2:] == ["demora, o painel ficou vago", "O que demora?"]


async def test_a_turn_drops_its_answer_when_a_person_took_the_ticket_meanwhile(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    await chat.receive(conversation_id, "o painel não abre")
    llm = SlowLlm(h)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], needs_clarification=True, reply="Qual erro?"))
    turn = asyncio.create_task(process_turn(h.deps, conversation_id))
    await asyncio.sleep(0.05)
    t = await chat.ticket_of(conversation_id)
    await take_card(h.deps, t.id, h.seed.team["first"])
    llm.release.set()
    assert await turn is None
    assert chat.last_sent() != "Qual erro?"
    assert (await chat.ticket_of(conversation_id)).column == "in_progress"


# Questions about the FAQ entry sent (spec §5.1 step 5)


async def test_answers_a_question_about_the_faq_entry_and_asks_again_if_it_worked(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    outcome = await chat.asks(conversation_id, "o link vale por quanto tempo?", reply="O link vale por 1 hora.")
    assert outcome == "answer_faq_question"
    assert chat.last_sent() == "\n\n".join(["O link vale por 1 hora.", TEXT.faq_follow_up])
    t = await chat.ticket_of(conversation_id)
    assert (t.column, t.faq_questions_answered, t.unclear_feedback_reasks) == ("in_triage", 1, 0)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_feedback="resolved"))
    assert await chat.customer(conversation_id, "sim, resolveu") == "resolved_by_bot"
    assert (await chat.ticket_of(conversation_id)).column == "resolved_by_bot"


async def test_answers_three_questions_and_hands_the_fourth_over(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    for n in range(3):
        assert await chat.asks(conversation_id, f"dúvida {n}", reply=f"Resposta {n}.") == "answer_faq_question"
    outcome = await chat.asks(
        conversation_id, "e o e-mail muda?", reply="Não muda.", summary="Esqueceu a senha.", handoff_reply=PHRASE
    )
    assert outcome == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.column, t.handoff_reason, t.faq_questions_answered) == ("awaiting_human", "faq_not_resolved", 3)
    assert chat.last_sent() == TEXT.handoff
    assert t.summary == "Esqueceu a senha. Dúvida sem resposta: e o e-mail muda?"


async def test_hands_over_a_question_the_knowledge_base_does_not_answer_keeping_it_in_the_summary(
    h: Harness, chat: Chat
) -> None:
    conversation_id = await chat.faq_sent()
    outcome = await chat.asks(
        conversation_id, "dá pra trocar o e-mail do login?", found=False, summary="Senha.", handoff_reply=PHRASE
    )
    assert outcome == "handoff"
    t = await chat.ticket_of(conversation_id)
    assert (t.column, t.handoff_reason) == ("awaiting_human", "faq_not_resolved")
    assert texts(h.chatwoot.sent)[-1] == PHRASE
    assert "dá pra trocar o e-mail do login?" in t.summary
    assert t.summary.startswith("Senha.")


async def test_hands_over_a_question_about_an_entry_with_an_empty_knowledge_base(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent("reconnect", "whatsappDisconnected")
    assert await chat.asks(conversation_id, "e se o QR Code não aparecer?", found=False) == "handoff"
    assert json.loads(h.llm.requests[-1].user)["sent_faq"]["knowledge_base"] == ""
    t = await chat.ticket_of(conversation_id)
    assert (t.column, t.handoff_reason) == ("awaiting_human", "faq_not_resolved")
    assert chat.last_sent() == TEXT.handoff


async def test_the_llm_sees_the_entry_sent_and_its_knowledge_base_only_after_sending_it(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    before = json.loads(h.llm.requests[-1].user)
    assert "sent_faq" not in before
    assert "answer_text" not in h.llm.requests[-1].user
    assert "knowledge_base" not in h.llm.requests[-1].user
    await chat.asks(conversation_id, "o link vale por quanto tempo?", reply="Vale por 1 hora.")
    after = json.loads(h.llm.requests[-1].user)
    password = FICTITIOUS["faq"]["password"]
    assert after["sent_faq"] == {
        "id": h.seed.faq["password"],
        "title": password["title"],
        "answer_text": password["answer_text"],
        "knowledge_base": password["knowledge_base"],
    }
    assert FICTITIOUS["faq"]["report"]["knowledge_base"] not in h.llm.requests[-1].user
    assert FICTITIOUS["faq"]["report"]["answer_text"] not in h.llm.requests[-1].user
    assert (after["state"]["faq_questions_answered"], after["state"]["max_faq_questions"]) == (0, 3)


async def test_a_ticket_silent_after_an_answered_question_goes_to_no_response(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.faq_sent()
    await chat.asks(conversation_id, "o link vale por quanto tempo?", reply="Vale por 1 hora.")
    t = await chat.ticket_of(conversation_id)
    h.advance(24 * 3_600_000)
    assert await sweep_silent_tickets(h.deps) == [t.id]
    assert (await chat.ticket_of(conversation_id)).column == "no_response"


def timing_lines(h: Harness) -> list[dict[str, object]]:
    return [e.obj for e in h.logger.infos if e.msg == "turn timing"]


async def test_logs_how_long_each_step_of_a_turn_took_without_its_content(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    [greeting] = timing_lines(h)
    assert (greeting["outcome"], "llmMs" in greeting) == ("greeting", False)
    h.llm.push(turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"]))
    await chat.receive(conversation_id, "esqueci a senha")
    h.advance(4_200)
    assert await process_turn(h.deps, conversation_id) == "send_faq"
    [_, line] = timing_lines(h)
    t = await chat.ticket_of(conversation_id)
    assert {k: v for k, v in line.items() if k not in ("llmMs", "toOutboxMs")} == {
        "ticketId": t.id,
        "outcome": "send_faq",
        "waitMs": 4_200,
        "llmOutcomes": ["ok"],
        "llmRetried": False,
    }
    llm_ms, to_outbox_ms = line["llmMs"], line["toOutboxMs"]
    assert isinstance(llm_ms, list) and len(llm_ms) == 1
    assert isinstance(to_outbox_ms, int) and to_outbox_ms >= llm_ms[0]
    assert "senha" not in repr(line)
    assert h.seed.attendants["ana"].phone not in repr(line)


async def test_the_timing_line_says_when_the_llm_was_tried_again(h: Harness, chat: Chat) -> None:
    conversation_id = await chat.greeted()
    h.llm.push(TimeoutError(), turn_json(category_id=h.seed.categories["login"], faq_item_id=h.seed.faq["password"]))
    await chat.customer(conversation_id, "esqueci a senha")
    line = timing_lines(h)[-1]
    assert (line["llmOutcomes"], line["llmRetried"]) == (["timeout", "ok"], True)
