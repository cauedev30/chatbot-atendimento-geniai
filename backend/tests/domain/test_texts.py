from geniai.domain.texts import TEXT, category_label, truncate


def test_greets_with_the_registered_name_and_unit_and_asks_for_the_problem() -> None:
    greeting = TEXT.greeting("Ana Exemplo", "Unidade Exemplo Centro")
    assert "Ana Exemplo" in greeting
    assert "Unidade Exemplo Centro" in greeting
    assert "problema" in greeting


def test_labels_categories_as_system_slash_problem() -> None:
    assert category_label("Painel", "Não consegue entrar") == "Painel / Não consegue entrar"


def test_truncates_with_an_ellipsis() -> None:
    assert truncate("abcdef", 4) == "abc…"
    assert truncate("abc", 4) == "abc"


def test_customer_texts_are_exactly_the_approved_wording() -> None:
    assert TEXT.greeting("N", "U") == (
        "Olá! Aqui é o suporte da GeniAI. Falo com N, da unidade U? Se for isso mesmo, me conta qual é o problema."
    )
    assert TEXT.unidentified_ack == "Recebemos sua mensagem! A equipe de suporte já fala com você."
    assert TEXT.handoff == "Certo! Vou passar sua conversa para a nossa equipe, que já fala com você por aqui."
    assert TEXT.faq_follow_up == "Isso resolveu o seu problema? Responda sim ou não."
    assert TEXT.reask_feedback == "Só pra eu confirmar: as instruções resolveram o problema? Responda sim ou não."
    assert TEXT.resolved_thanks == "Que bom que resolveu! Se precisar, é só chamar."
    assert TEXT.ask_for_text == (
        "Ainda não consigo ouvir áudios nem abrir imagens ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    assert TEXT.clarify_fallback == "Pode me contar um pouco mais sobre o problema?"
