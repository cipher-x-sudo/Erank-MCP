"""Unit tests with mocked HTTP (no live eRank session required)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from erank_mcp.client import ErankError, ErankHttpClient, _load_cookies_from_file
from erank_mcp.config import Settings


def test_load_cookies_json(tmp_path: Path) -> None:
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {
                    "name": "XSRF-TOKEN",
                    "value": "abc%3D",
                    "domain": ".erank.com",
                    "path": "/",
                },
                {
                    "name": "erank_session",
                    "value": "sess",
                    "domain": "members.erank.com",
                    "path": "/",
                },
            ]
        ),
        encoding="utf-8",
    )
    cookies = _load_cookies_from_file(path)
    assert len(cookies) == 2
    assert cookies[0]["name"] == "XSRF-TOKEN"


def test_telemetry_blocked() -> None:
    settings = Settings(
        erank_cookie_header="XSRF-TOKEN=tok; erank_session=s",
        erank_warm_session=False,
        erank_allow_telemetry=False,
    )
    with patch.object(httpx.Client, "request") as mocked:
        client = ErankHttpClient(settings)
        with pytest.raises(ErankError) as ei:
            client.get("/api/logs")
        assert "telemetry" in str(ei.value).lower() or "Blocked" in str(ei.value)
        mocked.assert_not_called()
        client.close()


def test_xsrf_header_applied() -> None:
    settings = Settings(
        erank_cookie_header="XSRF-TOKEN=hello%3Dworld; erank_session=s",
        erank_warm_session=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-XSRF-TOKEN") == "hello=world"
        assert request.headers.get("X-User-Agent") == "erank-app/3.0"
        assert request.headers.get("X-Requested-With") == "XMLHttpRequest"
        assert "X-Correlation-Id" in request.headers
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = ErankHttpClient(settings)
    client._client = httpx.Client(
        base_url="https://members.erank.com",
        transport=transport,
        cookies=client._client.cookies,
        headers=client._client.headers,
    )
    assert client.get("/api/quota/daily") == {"ok": True}
    client.close()


def test_auth_error_hint() -> None:
    settings = Settings(
        erank_cookie_header="XSRF-TOKEN=t; erank_session=s",
        erank_warm_session=False,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "Unauthenticated"})

    client = ErankHttpClient(settings)
    client._client = httpx.Client(
        base_url="https://members.erank.com",
        transport=httpx.MockTransport(handler),
        cookies=client._client.cookies,
        headers=client._client.headers,
    )
    with pytest.raises(ErankError) as ei:
        client.get("/api/dashboard/shop-profile")
    assert ei.value.status_code == 401
    assert ei.value.hint
    client.close()
