from typing import Any

import pytest

import geniai.__main__ as entrypoint
from tests.api.test_config import VALID


def test_runs_on_host_and_port_from_the_config_with_its_own_access_log(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(entrypoint.uvicorn, "run", lambda _app, **kwargs: calls.append(kwargs))
    for name, value in (VALID | {"HOST": "127.0.0.1", "PORT": "8123"}).items():
        monkeypatch.setenv(name, value)
    entrypoint.main()
    # uvicorn's access log would print the webhook token; the app logs requests itself, masked.
    assert calls == [{"host": "127.0.0.1", "port": 8123, "access_log": False}]
