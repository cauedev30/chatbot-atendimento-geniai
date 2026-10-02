from ipaddress import ip_network

import pytest

from geniai.config import ConfigError, load_config
from geniai.domain.rules import DEFAULT_RULES
from geniai.transcription.openai_compatible import TranscriberConfig

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
    "BOARD_PASSWORD": "senha-longa-de-teste",
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
    assert config.trusted_proxies == (ip_network("127.0.0.1/32"), ip_network("::1/128"))
    assert config.bot_only_phones == frozenset()
    assert config.llm_reads_images is False
    assert config.transcription is None


TRANSCRIBE = {
    "TRANSCRIBE_BASE_URL": "https://stt.example/v1",
    "TRANSCRIBE_API_KEY": "stt-key",
    "TRANSCRIBE_MODEL": "stt-model",
}


def test_reads_the_transcription_settings_apart_from_the_llm() -> None:
    config = load_config(VALID | TRANSCRIBE)
    assert config.transcription == TranscriberConfig(
        base_url="https://stt.example/v1", api_key="stt-key", model="stt-model"
    )
    assert config.llm.base_url == VALID["LLM_BASE_URL"]


@pytest.mark.parametrize("missing", list(TRANSCRIBE))
def test_a_partial_transcription_setting_names_what_is_missing_and_never_a_value(missing: str) -> None:
    given = {k: v for k, v in TRANSCRIBE.items() if k != missing}
    with pytest.raises(ConfigError) as err:
        load_config(VALID | given | {missing: ""})
    assert missing in str(err.value)
    assert all(value not in str(err.value) for value in given.values())


def test_reads_the_test_mode_phones_normalized_like_the_contact_phone() -> None:
    config = load_config(VALID | {"BOT_ONLY_PHONES": "+55 (11) 90000-0001, 5511900000002,,11 90000003 "})
    assert config.bot_only_phones == frozenset({"+5511900000001", "+5511900000002", "+5511990000003"})


@pytest.mark.parametrize("value", ["+5511900000001, sem-numero", "123", "+1 555 0100"])
def test_rejects_a_test_mode_entry_that_is_not_a_phone_without_echoing_it(value: str) -> None:
    with pytest.raises(ConfigError) as err:
        load_config(VALID | {"BOT_ONLY_PHONES": value})
    assert "BOT_ONLY_PHONES" in str(err.value)
    assert value not in str(err.value)


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
            "TRUSTED_PROXY_IPS": "10.0.0.5, 172.17.0.0/16",
            "LLM_READS_IMAGES": "true",
        }
    )
    assert config.port == 8080
    assert config.auth.secure_cookie is False
    assert config.rules.burst_window_ms == 3000
    assert config.rules.silence_timeout_ms == 12 * 3_600_000
    assert config.llm.extra_body == {"thinking": {"type": "disabled"}}
    assert config.enable_api_docs is True
    assert config.trusted_proxies == (ip_network("10.0.0.5/32"), ip_network("172.17.0.0/16"))
    assert config.llm_reads_images is True


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
        ("BOARD_PASSWORD", "quinze-letrasxx"),
        ("WEBHOOK_TOKEN", "curto"),
        ("CHATWOOT_BASE_URL", "not a url"),
        ("CHATWOOT_ACCOUNT_ID", "0"),
        ("PORT", "abc"),
        ("SECURE_COOKIE", "yes"),
        ("BURST_WINDOW_MS", "-5"),
        ("LLM_EXTRA_BODY_JSON", "[1, 2]"),
        ("LLM_EXTRA_BODY_JSON", "{not json"),
        ("LLM_EXTRA_BODY_JSON", '{"temperature": NaN}'),
        ("LLM_EXTRA_BODY_JSON", '{"max_tokens": Infinity}'),
        ("LLM_EXTRA_BODY_JSON", '{"x": {"y": -Infinity}}'),
        ("TRUSTED_PROXY_IPS", "10.0.0.300"),
        ("TRUSTED_PROXY_IPS", "proxy.local"),
        ("LLM_READS_IMAGES", "yes"),
        ("TRANSCRIBE_BASE_URL", "not a url"),
    ],
)
def test_names_an_invalid_variable_and_never_its_value(name: str, value: str) -> None:
    with pytest.raises(ConfigError) as err:
        load_config(VALID | TRANSCRIBE | {name: value})
    assert name in str(err.value)
    assert value not in str(err.value)


def test_the_burst_window_is_the_owner_s_four_seconds() -> None:
    assert DEFAULT_RULES.burst_window_ms == 4_000


def test_image_reading_limits_are_the_owner_unconfirmed_defaults() -> None:
    assert (DEFAULT_RULES.max_images_per_turn, DEFAULT_RULES.max_image_bytes) == (4, 5 * 1024 * 1024)
    assert DEFAULT_RULES.image_download_timeout_ms == 15_000


def test_the_card_summary_deadline_is_the_owner_unconfirmed_default() -> None:
    assert DEFAULT_RULES.summary_deadline_ms == 30_000


def test_audio_limits_are_the_owner_s_two_minutes_and_the_image_s_size_and_time() -> None:
    assert DEFAULT_RULES.max_audio_seconds == 120
    assert (DEFAULT_RULES.max_audio_bytes, DEFAULT_RULES.audio_download_timeout_ms) == (5 * 1024 * 1024, 15_000)
    assert DEFAULT_RULES.max_untimed_audio_bytes == 2 * 1024 * 1024
    assert DEFAULT_RULES.transcribe_timeout_ms == 15_000
