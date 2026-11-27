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


def _file_client(tmp_path: Path, handler) -> tuple[ErankHttpClient, Path]:
    path = tmp_path / "cookies.json"
    path.write_text(
        json.dumps(
            [
                {"name": "sid_er", "value": "old", "domain": ".erank.com", "path": "/", "expirationDate": 1},
                {"name": "_ga", "value": "keep", "domain": ".erank.com", "path": "/"},
            ]
        ),
        encoding="utf-8",
    )
    client = ErankHttpClient(Settings(erank_cookie_file=str(path), erank_warm_session=False))
    client._client = httpx.Client(
        base_url="https://members.erank.com",
        transport=httpx.MockTransport(handler),
        cookies=client._client.cookies,
        headers=client._client.headers,
    )
    return client, path


def test_rotated_cookies_saved(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"ok": True},
            headers={"set-cookie": "sid_er=new; Domain=.erank.com; Path=/; Max-Age=3600"},
        )

    client, path = _file_client(tmp_path, handler)
    client.get("/api/quota/daily")
    saved = {c["name"]: c for c in json.loads(path.read_text(encoding="utf-8"))}
    assert saved["sid_er"]["value"] == "new"
    assert saved["sid_er"]["expirationDate"] > 1
    assert saved["_ga"]["value"] == "keep"
    client.close()


def test_cookies_not_saved_on_auth_failure(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            401,
            json={"message": "Unauthenticated"},
            headers={"set-cookie": "sid_er=guest; Domain=.erank.com; Path=/"},
        )

    client, path = _file_client(tmp_path, handler)
    with pytest.raises(ErankError):
        client.get("/api/quota/daily")
    assert json.loads(path.read_text(encoding="utf-8"))[0]["value"] == "old"
    client.close()
