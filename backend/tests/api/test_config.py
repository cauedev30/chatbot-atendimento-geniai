import pytest

from geniai.config import ConfigError, load_config
from geniai.domain.rules import DEFAULT_RULES

VALID = {
    "DATABASE_URL": "postgresql://user:pass@127.0.0.1:5432/geniai_test",
    "WEBHOOK_TOKEN": "token-de-teste-123456",
    "CHATWOOT_BASE_URL": "https://chatwoot.example",
    "CHATWOOT_ACCOUNT_ID": "1",
    "CHATWOOT_API_TOKEN": "tok",
    "LLM_BASE_URL": "https://llm.example/v1",
    "LLM_API_KEY": "key",
    "LLM_MODEL": "model-x",
    "BOARD_USER": "suporte",
    "BOARD_PASSWORD": "senha-longa",
    "COOKIE_SECRET": "c" * 32,
}


def test_loads_a_valid_environment_with_defaults() -> None:
    config = load_config(VALID)
    assert (config.database_url, config.port, config.host) == (VALID["DATABASE_URL"], 8000, "0.0.0.0")
    assert (config.chatwoot.account_id, config.chatwoot.api_token) == (1, "tok")
    assert config.auth.secure_cookie is True
    assert config.rules == DEFAULT_RULES
    assert config.llm.extra_body is None
    assert config.enable_api_docs is False


def test_applies_overrides() -> None:
    config = load_config(
        VALID
        | {
            "PORT": "8080",
            "SECURE_COOKIE": "false",
            "BURST_WINDOW_MS": "3000",
            "SILENCE_TIMEOUT_HOURS": "12",
            "LLM_EXTRA_BODY_JSON": '{"thinking":{"type":"disabled"}}',
            "ENABLE_API_DOCS": "true",
        }
    )
    assert config.port == 8080
    assert config.auth.secure_cookie is False
    assert config.rules.burst_window_ms == 3000
    assert config.rules.silence_timeout_ms == 12 * 3_600_000
    assert config.llm.extra_body == {"thinking": {"type": "disabled"}}
    assert config.enable_api_docs is True


def test_treats_empty_strings_as_missing_and_names_missing_variables_without_their_values() -> None:
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        load_config(VALID | {"LLM_API_KEY": ""})
    with pytest.raises(ConfigError) as err:
        load_config({})
    assert "DATABASE_URL" in str(err.value)
    assert "COOKIE_SECRET" in str(err.value)


def test_rejects_a_short_cookie_secret() -> None:
    with pytest.raises(ConfigError, match="COOKIE_SECRET"):
        load_config(VALID | {"COOKIE_SECRET": "short"})


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("BOARD_PASSWORD", "curta"),
        ("WEBHOOK_TOKEN", "curto"),
        ("CHATWOOT_BASE_URL", "not a url"),
        ("CHATWOOT_ACCOUNT_ID", "0"),
        ("PORT", "abc"),
        ("SECURE_COOKIE", "yes"),
        ("BURST_WINDOW_MS", "-5"),
        ("LLM_EXTRA_BODY_JSON", "[1, 2]"),
        ("LLM_EXTRA_BODY_JSON", "{not json"),
    ],
)
def test_names_an_invalid_variable_and_never_its_value(name: str, value: str) -> None:
    with pytest.raises(ConfigError) as err:
        load_config(VALID | {name: value})
    assert name in str(err.value)
    assert value not in str(err.value)
