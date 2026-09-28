from geniai.db.fixtures import FICTITIOUS
from geniai.eval.cases import CASES, FAQ_QUESTION_CASES, build_catalog, context_for, question_context_for


def test_has_30_cases_with_unique_ids_and_at_least_10_human_requests() -> None:
    assert len(CASES) == 30
    assert len({c.id for c in CASES}) == 30
    assert len([c for c in CASES if c.expected.human_requested]) >= 10


def test_only_uses_labels_that_exist_in_the_catalog() -> None:
    catalog = build_catalog()
    categories = {c.label for c in catalog.categories}
    faqs = {f.title for f in catalog.faq_items}
    for c in CASES:
        assert c.expected.category in categories, c.id
        if c.expected.faq is not None:
            assert c.expected.faq in faqs, c.id


def test_builds_a_context_with_the_greeting_answered_and_the_customer_message_new() -> None:
    ctx = context_for(CASES[0], build_catalog())
    assert [m.author for m in ctx.messages] == ["bot"]
    assert [m.text for m in ctx.new_messages] == list(CASES[0].customer)


def test_the_catalog_has_stable_ids() -> None:
    catalog = build_catalog()
    assert [c.id for c in catalog.categories] == [1, 2, 3, 4, 5, 100]
    assert catalog.categories[-1].label == "Geral / Outros"
    assert [(f.id, f.category_id) for f in catalog.faq_items] == [(1, 1), (2, 2), (3, 4)]


def test_has_faq_questions_answered_by_the_knowledge_base_and_questions_it_does_not_answer() -> None:
    assert len({c.id for c in FAQ_QUESTION_CASES}) == len(FAQ_QUESTION_CASES)
    assert {c.answer_found for c in FAQ_QUESTION_CASES} == {True, False}
    assert all(c.faq in FICTITIOUS["faq"] for c in FAQ_QUESTION_CASES)
    # An entry with an empty knowledge base never has an answer found.
    assert all(not c.answer_found for c in FAQ_QUESTION_CASES if FICTITIOUS["faq"][c.faq]["knowledge_base"] == "")


def test_builds_a_question_context_after_the_faq_entry_was_sent() -> None:
    catalog = build_catalog()
    case = FAQ_QUESTION_CASES[0]
    entry = FICTITIOUS["faq"][case.faq]
    ctx = question_context_for(case, catalog)
    assert ctx.state.faq_attempted is True
    assert ctx.sent_faq is not None
    assert (ctx.sent_faq.title, ctx.sent_faq.answer_text, ctx.sent_faq.knowledge_base) == (
        entry["title"],
        entry["answer_text"],
        entry["knowledge_base"],
    )
    assert entry["answer_text"] in ctx.messages[-1].text
    assert [m.text for m in ctx.new_messages] == [case.question]
