import pytest

from geniai.domain.human_request import mentions_human_request


@pytest.mark.parametrize(
    "text",
    [
        "Quero falar com um ATENDENTE",
        "tem algum humano aí?",
        "preciso falar com alguém",
        "preciso falar com alguem",
        "me passa pra uma pessoa",
        "chama os atendentes",
    ],
)
def test_detects(text: str) -> None:
    assert mentions_human_request(text) is True


@pytest.mark.parametrize("text", ["meu número caiu", "o atendimento da unidade parou", "oi, tudo bem?", ""])
def test_ignores(text: str) -> None:
    assert mentions_human_request(text) is False


def test_word_boundaries_are_ascii() -> None:
    # `\b` only knows [A-Za-z0-9_]: a letter that NFD cannot strip (ø) ends the word, so
    # "atendenteø" still matches, while "atendente_x" does not.
    assert mentions_human_request("atendenteø") is True
    assert mentions_human_request("atendente_x") is False
