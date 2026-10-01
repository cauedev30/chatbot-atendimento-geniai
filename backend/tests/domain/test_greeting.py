import pytest

from geniai.domain.greeting import is_bare_greeting


@pytest.mark.parametrize(
    "texts",
    [
        ["oi"],
        ["Bom dia!"],
        ["oi 😊"],
        ["e aí, tudo bem?"],
        ["Olá", "boa tarde, pessoal"],
        ["Opa, blz? suporte GeniAI"],
        [""],
        [],
    ],
)
def test_a_greeting_alone_is_only_a_greeting(texts: list[str]) -> None:
    assert is_bare_greeting(texts, has_media=False) is True


@pytest.mark.parametrize(
    "texts",
    [
        ["oi, não consigo entrar"],
        ["Não tá funcionando aqui"],
        ["oi", "meu número caiu"],
        ["bom dia 2"],
    ],
)
def test_a_message_with_anything_else_has_content(texts: list[str]) -> None:
    assert is_bare_greeting(texts, has_media=False) is False


def test_a_photo_an_audio_or_a_file_is_content_even_with_a_greeting_caption() -> None:
    assert is_bare_greeting([], has_media=True) is False
    assert is_bare_greeting([""], has_media=True) is False
    assert is_bare_greeting(["oi"], has_media=True) is False
