"""HTTP client for members.erank.com with cookie + XSRF session auth."""

from __future__ import annotations

import json
import secrets
import string
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

import httpx

from erank_mcp.config import Settings, get_settings

BLOCKED_TELEMETRY_PATHS = {"/api/logs", "/api/intercom"}


class ErankError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: Any = None,
        hint: str | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.hint = hint

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "status_code": self.status_code,
            "body": self.body,
            "hint": self.hint,
        }


def _correlation_id(length: int = 43) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _load_cookies_from_file(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []

    # Netscape cookie file
    if text.startswith("# Netscape") or "\t" in text.splitlines()[0]:
        cookies: list[dict[str, Any]] = []
        for line in text.splitlines():
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            domain, _flag, cookie_path, secure, expires, name, value = parts[:7]
            cookies.append(
                {
                    "name": name,
                    "value": value,
                    "domain": domain.lstrip("."),
                    "path": cookie_path,
                    "secure": secure.upper() == "TRUE",
                    "expires": int(expires) if expires.isdigit() else None,
                }
            )
        return cookies

    data = json.loads(text)
    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ValueError(f"Unsupported cookie file format: {path}")
    return data


class ErankHttpClient:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.settings.erank_base_url.rstrip("/"),
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=True,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "X-User-Agent": "erank-app/3.0",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.0.0 Safari/537.36"
                ),
                "Origin": self.settings.erank_base_url.rstrip("/"),
            },
        )
        self._load_session_cookies()
        if self.settings.erank_warm_session:
            try:
                self.warm()
            except ErankError:
                # Warm is best-effort; tools will surface auth failures.
                pass

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> ErankHttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _load_session_cookies(self) -> None:
        if self.settings.erank_cookie_header:
            for part in self.settings.erank_cookie_header.split(";"):
                part = part.strip()
                if not part or "=" not in part:
                    continue
                name, value = part.split("=", 1)
                self._client.cookies.set(name.strip(), value.strip(), domain="members.erank.com")
            return

        if self.settings.erank_cookie_file:
            path = Path(self.settings.erank_cookie_file)
            if not path.is_absolute():
                from erank_mcp.config import PROJECT_ROOT

                path = (PROJECT_ROOT / path).resolve()
            if not path.exists():
                raise ErankError(
                    f"Cookie file not found: {path}",
                    hint="Put Cookie-Editor JSON export at project-root cookies.json (see cookies.example.json).",
                )
            for c in _load_cookies_from_file(path):
                name = c.get("name")
                value = c.get("value")
                if not name or value is None:
                    continue
                # Keep leading-dot domains as-is for subdomain cookies (.erank.com)
                raw_domain = c.get("domain") or "members.erank.com"
                domain = str(raw_domain)
                path_val = c.get("path") or "/"
                self._client.cookies.set(str(name), str(value), domain=domain, path=path_val)

    def _cookie_value(self, name: str, *, prefer_host: str = "members.erank.com") -> Optional[str]:
        """Read a cookie without CookieConflict when the same name exists on multiple domains."""
        matches = [c for c in self._client.cookies.jar if c.name == name]
        if not matches:
            return None
        for c in matches:
            if prefer_host in (c.domain or "") or (c.domain or "").lstrip(".") in prefer_host:
                return c.value
        # Prefer most specific / longest domain match for members.erank.com
        matches.sort(key=lambda c: (0 if "members.erank.com" in (c.domain or "") else 1, -len(c.domain or "")))
        return matches[0].value

    def _xsrf_header(self) -> Optional[str]:
        token = self._cookie_value("XSRF-TOKEN")
        if not token:
            return None
        return unquote(token)

    def _apply_auth_headers(self, headers: dict[str, str], referer: str | None) -> None:
        xsrf = self._xsrf_header()
        if xsrf:
            headers["X-XSRF-TOKEN"] = xsrf
        headers["X-Correlation-Id"] = _correlation_id()
        if referer:
            if referer.startswith("http"):
                headers["Referer"] = referer
            else:
                base = self.settings.erank_base_url.rstrip("/")
                headers["Referer"] = f"{base}/{referer.lstrip('/')}"
        else:
            headers["Referer"] = f"{self.settings.erank_base_url.rstrip('/')}/dashboard"

    def warm(self) -> dict[str, Any]:
        """Hit dashboard HTML then shop-profile to refresh cookies/XSRF."""
        self._client.get("/dashboard", headers={"Accept": "text/html"})
        return self.request("GET", "/api/dashboard/shop-profile", referer="/dashboard")

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        referer: str | None = None,
        allow_telemetry: bool | None = None,
    ) -> Any:
        if not path.startswith("/"):
            path = "/" + path

        telemetry_ok = (
            self.settings.erank_allow_telemetry if allow_telemetry is None else allow_telemetry
        )
        if path.rstrip("/") in BLOCKED_TELEMETRY_PATHS or path.startswith("/api/logs"):
            if not telemetry_ok:
                raise ErankError(
                    f"Blocked telemetry path: {path}",
                    hint="Set ERANK_ALLOW_TELEMETRY=1 to allow.",
                )

        headers: dict[str, str] = {}
        self._apply_auth_headers(headers, referer)

        try:
            resp = self._client.request(
                method.upper(),
                path,
                params=params,
                json=json_body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ErankError(f"Network error: {exc}") from exc

        # Refresh XSRF from Set-Cookie automatically via httpx jar
        return self._parse_response(resp)

    def get(self, path: str, **kwargs: Any) -> Any:
        return self.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs: Any) -> Any:
        return self.request("POST", path, **kwargs)

    def _parse_response(self, resp: httpx.Response) -> Any:
        status = resp.status_code
        body: Any
        ctype = resp.headers.get("content-type", "")
        if "application/json" in ctype:
            try:
                body = resp.json()
            except json.JSONDecodeError:
                body = resp.text
        else:
            body = resp.text[:2000] if resp.text else None

        if status in (401, 403, 419):
            raise ErankError(
                "Authentication failed — session cookie expired or XSRF mismatch",
                status_code=status,
                body=body,
                hint="Re-export cookies from a logged-in browser tab into ERANK_COOKIE_FILE.",
            )
        if status == 429:
            raise ErankError(
                "Rate limited / quota exceeded",
                status_code=status,
                body=body,
                hint="Check erank_quota and wait before retrying.",
            )
        if status >= 400:
            raise ErankError(
                f"eRank API error HTTP {status}",
                status_code=status,
                body=body,
            )
        return body

    def cookie_names(self) -> list[str]:
        names = sorted({c.name for c in self._client.cookies.jar})
        return names

    def has_session(self) -> bool:
        names = set(self.cookie_names())
        session_markers = {"sid_er", "er_sess_x", "erank_session", "XSRF-TOKEN"}
        return bool(names & session_markers) or any("sess" in n.lower() for n in names)


_client: ErankHttpClient | None = None


def get_client() -> ErankHttpClient:
    global _client
    if _client is None:
        _client = ErankHttpClient()
    return _client


def reset_client() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
    try:
        from erank_mcp.context import reset_context

        reset_context()
    except Exception:  # noqa: BLE001
        pass
