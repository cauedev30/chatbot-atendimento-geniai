import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, BaseModel, Field, ValidationError

from geniai.api.auth import AuthConfig
from geniai.chatwoot.http import ChatwootHttpConfig
from geniai.domain.rules import DEFAULT_RULES, TriageRules
from geniai.llm.openai_compatible import OpenAiCompatibleConfig


class ConfigError(Exception):
    pass


def _url(value: str) -> str:
    parts = urlsplit(value)
    if not parts.scheme or not parts.netloc:
        raise ValueError("not a URL")
    return value


Url = Annotated[str, AfterValidator(_url)]
NonEmpty = Annotated[str, Field(min_length=1)]


class _Env(BaseModel):
    DATABASE_URL: NonEmpty
    PORT: Annotated[int, Field(gt=0)] = 8000
    HOST: str = "0.0.0.0"
    WEBHOOK_TOKEN: Annotated[str, Field(min_length=16)]
    CHATWOOT_BASE_URL: Url
    CHATWOOT_ACCOUNT_ID: Annotated[int, Field(gt=0)]
    CHATWOOT_API_TOKEN: NonEmpty
    LLM_BASE_URL: Url
    LLM_API_KEY: NonEmpty
    LLM_MODEL: NonEmpty
    LLM_EXTRA_BODY_JSON: str | None = None
    BOARD_USER: NonEmpty
    BOARD_PASSWORD: Annotated[str, Field(min_length=8)]
    COOKIE_SECRET: Annotated[str, Field(min_length=32)]
    SECURE_COOKIE: Literal["true", "false"] = "true"
    BURST_WINDOW_MS: Annotated[int, Field(gt=0)] | None = None
    SILENCE_TIMEOUT_HOURS: Annotated[float, Field(gt=0)] | None = None
    ENABLE_API_DOCS: Literal["true", "false"] = "false"


@dataclass(frozen=True)
class AppConfig:
    database_url: str
    port: int
    host: str
    webhook_token: str
    chatwoot: ChatwootHttpConfig
    llm: OpenAiCompatibleConfig
    auth: AuthConfig
    rules: TriageRules
    enable_api_docs: bool = False
    """Serve /docs, /redoc and /openapi.json. Off by default: the schema is exported at build time."""


def _reject_non_finite(constant: str) -> object:
    """NaN and Infinity are not JSON; a provider would reject the request body."""
    raise ValueError(f"{constant} is not valid JSON")


def _invalid(names: list[str]) -> ConfigError:
    return ConfigError(f"Invalid or missing environment variables: {', '.join(names)}")


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Reads configuration from the environment. Errors name the variables, never their values."""
    source = os.environ if env is None else env
    present = {k: v for k, v in source.items() if k in _Env.model_fields and v != ""}
    try:
        e = _Env.model_validate(present)
    except ValidationError as err:
        names = list(dict.fromkeys(str(issue["loc"][0]) for issue in err.errors(include_input=False)))
        raise _invalid(names) from None
    extra_body: dict[str, object] | None = None
    if e.LLM_EXTRA_BODY_JSON is not None:
        try:
            parsed = json.loads(e.LLM_EXTRA_BODY_JSON, parse_constant=_reject_non_finite)
        except (json.JSONDecodeError, ValueError):
            raise _invalid(["LLM_EXTRA_BODY_JSON"]) from None
        if not isinstance(parsed, dict):
            raise _invalid(["LLM_EXTRA_BODY_JSON"])
        extra_body = parsed
    rules = DEFAULT_RULES
    if e.BURST_WINDOW_MS is not None:
        rules = replace(rules, burst_window_ms=e.BURST_WINDOW_MS)
    if e.SILENCE_TIMEOUT_HOURS is not None:
        rules = replace(rules, silence_timeout_ms=int(e.SILENCE_TIMEOUT_HOURS * 3_600_000))
    return AppConfig(
        database_url=e.DATABASE_URL,
        port=e.PORT,
        host=e.HOST,
        webhook_token=e.WEBHOOK_TOKEN,
        chatwoot=ChatwootHttpConfig(
            base_url=e.CHATWOOT_BASE_URL, account_id=e.CHATWOOT_ACCOUNT_ID, api_token=e.CHATWOOT_API_TOKEN
        ),
        llm=OpenAiCompatibleConfig(
            base_url=e.LLM_BASE_URL, api_key=e.LLM_API_KEY, model=e.LLM_MODEL, extra_body=extra_body
        ),
        auth=AuthConfig(
            user=e.BOARD_USER,
            password=e.BOARD_PASSWORD,
            cookie_secret=e.COOKIE_SECRET,
            secure_cookie=e.SECURE_COOKIE == "true",
        ),
        rules=rules,
        enable_api_docs=e.ENABLE_API_DOCS == "true",
    )
