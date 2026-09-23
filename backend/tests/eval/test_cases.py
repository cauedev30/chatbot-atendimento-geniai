from geniai.eval.cases import CASES, build_catalog, context_for


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


def test_builds_a_context_that_starts_with_the_greeting() -> None:
    ctx = context_for(CASES[0], build_catalog())
    assert ctx.messages[0].author == "bot"
    assert ctx.messages[-1].text == CASES[0].customer[0]


def test_the_catalog_has_stable_ids() -> None:
    catalog = build_catalog()
    assert [c.id for c in catalog.categories] == [1, 2, 3, 4, 5, 100]
    assert catalog.categories[-1].label == "Geral / Outros"
    assert [(f.id, f.category_id) for f in catalog.faq_items] == [(1, 1), (2, 2), (3, 4)]
