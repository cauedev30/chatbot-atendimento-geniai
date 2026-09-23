"""`python -m geniai.export_openapi` writes backend/openapi.json, the schema the frontend types come from."""

import json
from pathlib import Path

from geniai.api.auth import AuthConfig
from geniai.chatwoot.http import ChatwootHttpConfig
from geniai.config import AppConfig
from geniai.domain.rules import DEFAULT_RULES
from geniai.llm.openai_compatible import OpenAiCompatibleConfig
from geniai.main import create_app

OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"

# Placeholders only: building the schema touches no database, Chatwoot or LLM.
_DUMMY = AppConfig(
    database_url="postgresql://unused",
    port=8000,
    host="127.0.0.1",
    webhook_token="x" * 16,
    chatwoot=ChatwootHttpConfig(base_url="https://chatwoot.example", account_id=1, api_token="x"),
    llm=OpenAiCompatibleConfig(base_url="https://llm.example/v1", api_key="x", model="x"),
    auth=AuthConfig(user="x", password="x" * 8, cookie_secret="x" * 32, secure_cookie=True),
    rules=DEFAULT_RULES,
)


def openapi_json() -> str:
    return json.dumps(create_app(_DUMMY).openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    OUTPUT.write_text(openapi_json(), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
