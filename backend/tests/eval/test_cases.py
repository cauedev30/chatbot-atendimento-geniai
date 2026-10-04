from geniai.db.fixtures import FICTITIOUS
from geniai.eval.cases import (
    CASES,
    FAQ_FEEDBACK_CASES,
    FAQ_QUESTION_CASES,
    IMAGE_CASES,
    build_catalog,
    context_for,
    feedback_context_for,
    image_context_for,
    load_image,
    question_context_for,
)


def test_has_34_cases_with_unique_ids_and_at_least_10_human_requests() -> None:
    assert len(CASES) == 34
    assert len({c.id for c in CASES}) == 34
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


def test_has_four_image_cases_on_invented_pngs_one_unrelated_to_support() -> None:
    catalog = build_catalog()
    assert len({c.id for c in IMAGE_CASES}) == len(IMAGE_CASES) == 4
    assert {c.expected.category for c in IMAGE_CASES} <= {c.label for c in catalog.categories}
    assert [c.expected.faq is None for c in IMAGE_CASES].count(True) == 1
    for c in IMAGE_CASES:
        image = load_image(c)
        assert image.content_type == "image/png"
        assert image.data.startswith(b"\x89PNG\r\n\x1a\n")
        assert len(image.data) < 100_000, c.image


def test_builds_an_image_context_with_the_image_alone_as_the_customer_answer() -> None:
    case = IMAGE_CASES[0]
    ctx = image_context_for(case, build_catalog())
    assert [m.author for m in ctx.messages] == ["bot"]
    assert [m.text for m in ctx.new_messages] == ["[imagem 1]"]
    assert ctx.images == (load_image(case),)


def test_only_vague_messages_expect_a_clarifying_question() -> None:
    by_id = {c.id: c for c in CASES}
    assert [c.id for c in CASES if c.expected.clarifies] == ["33", "34"]
    for case_id in ("31", "32", "33", "34"):
        expected = by_id[case_id].expected
        assert (expected.human_requested, expected.category, expected.faq) == (False, "Geral / Outros", None)
    # A clear problem with no FAQ entry goes straight to the support team.
    assert all(not by_id[i].expected.clarifies for i in ("07", "08", "09", "10", "22", "26", "27", "28", "30"))


def test_has_faq_feedback_cases_where_thats_not_it_is_not_resolved() -> None:
    assert len({c.id for c in FAQ_FEEDBACK_CASES}) == len(FAQ_FEEDBACK_CASES) == 4
    assert all(c.faq in FICTITIOUS["faq"] for c in FAQ_FEEDBACK_CASES)
    assert [c.feedback for c in FAQ_FEEDBACK_CASES] == ["not_resolved", "not_resolved", "not_resolved", "resolved"]


def test_builds_a_feedback_context_like_a_question_context() -> None:
    catalog = build_catalog()
    case = FAQ_FEEDBACK_CASES[0]
    question_case = FAQ_QUESTION_CASES[0]
    assert question_case.faq == case.faq
    ctx = feedback_context_for(case, catalog)
    question = question_context_for(question_case, catalog)
    assert ctx.messages == question.messages
    assert (ctx.state, ctx.sent_faq) == (question.state, question.sent_faq)
    assert [m.text for m in ctx.new_messages] == [case.answer]
