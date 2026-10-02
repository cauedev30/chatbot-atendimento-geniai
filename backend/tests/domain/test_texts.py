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
    assert TEXT.greeting_with_content("N", "U") == (
        "Olá! Aqui é o suporte da GeniAI. Falo com N, da unidade U? "
        "Se for isso mesmo, é só confirmar que eu já vejo o que você mandou."
    )
    assert TEXT.unidentified_ack == "Recebemos sua mensagem! A equipe de suporte vai te responder por aqui."
    assert TEXT.handoff == "Certo! Passei sua conversa para a nossa equipe, que vai te responder por aqui."
    assert TEXT.faq_follow_up == "Isso resolveu o seu problema? Responda sim ou não."
    assert TEXT.reask_feedback == "Só pra eu confirmar: as instruções resolveram o problema? Responda sim ou não."
    assert TEXT.resolved_thanks == "Que bom que resolveu! Se precisar, é só chamar."
    assert TEXT.ask_for_text == (
        "Ainda não consigo ouvir áudios nem abrir imagens ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    assert TEXT.clarify_fallback == "Pode me contar um pouco mais sobre o problema?"
    assert TEXT.ask_for_text_image == "Não consegui abrir a imagem. Pode escrever o problema em texto, por favor?"
    assert TEXT.ask_for_text_other == (
        "Ainda não consigo ouvir áudios nem abrir vídeos ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    assert TEXT.ask_for_text_audio_too_long == (
        "Seu áudio passou de 2 minutos e não consegui ouvir. Pode mandar um mais curto ou escrever o problema?"
    )
    assert (
        TEXT.ask_for_text_audio_failed == "Não consegui ouvir seu áudio. Pode escrever o problema em texto, por favor?"
    )
    assert TEXT.ask_for_text_image_or_file == (
        "Ainda não consigo abrir imagens ou arquivos. Pode escrever o problema em texto, por favor?"
    )
    assert TEXT.ask_for_text_video_or_file == (
        "Ainda não consigo abrir vídeos ou arquivos. Pode escrever o problema em texto, por favor?"
    )


def test_the_fixed_handoff_texts_promise_no_speed() -> None:
    for text in (TEXT.handoff, TEXT.unidentified_ack):
        assert "já fala" not in text
        assert "logo" not in text
        assert "em instantes" not in text


def test_the_request_for_text_names_what_the_bot_could_not_read() -> None:
    assert TEXT.ask_for_text_for("media") == TEXT.ask_for_text
    assert TEXT.ask_for_text_for("image") == TEXT.ask_for_text_image
    assert TEXT.ask_for_text_for("other") == TEXT.ask_for_text_other
    assert TEXT.ask_for_text_for("audio_too_long") == TEXT.ask_for_text_audio_too_long
    assert TEXT.ask_for_text_for("audio_failed") == TEXT.ask_for_text_audio_failed
    assert TEXT.ask_for_text_for("image_or_file") == TEXT.ask_for_text_image_or_file
    assert TEXT.ask_for_text_for("video_or_file") == TEXT.ask_for_text_video_or_file


def test_the_requests_for_text_used_with_transcription_on_never_say_the_bot_cannot_hear_audio() -> None:
    for unread in ("image", "image_or_file", "video_or_file", "audio_too_long", "audio_failed"):
        assert "ouvir áudios" not in TEXT.ask_for_text_for(unread)
