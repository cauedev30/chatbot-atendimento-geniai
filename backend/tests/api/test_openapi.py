from geniai.export_openapi import OUTPUT, openapi_json


def test_the_committed_openapi_json_is_up_to_date() -> None:
    assert OUTPUT.read_text(encoding="utf-8") == openapi_json(), "run: python -m geniai.export_openapi"


def test_the_schema_uses_camel_case_and_lists_the_api_routes() -> None:
    text = openapi_json()
    for path in [
        "/api/health",
        "/api/auth/login",
        "/api/board",
        "/api/board/tickets/{ticket_id}/move",
        "/api/indicators",
    ]:
        assert f'"{path}"' in text
    assert '"generatedAt"' in text
    assert '"requireResponsible"' in text
    assert '"/webhooks/chatwoot/{token}"' not in text
