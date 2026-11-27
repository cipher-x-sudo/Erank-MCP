"""Resolve shop / member / list context from env or live eRank APIs."""

from __future__ import annotations

from typing import Any, Optional

from erank_mcp.client import ErankHttpClient, ErankError
from erank_mcp.config import Settings, get_settings


class AccountContext:
    def __init__(
        self,
        *,
        shop: Optional[str] = None,
        shop_id: Optional[int] = None,
        member_id: Optional[int] = None,
        keyword_list_id: Optional[int] = None,
        country: str = "GLO",
        marketplace: str = "etsy",
        raw_profile: Any = None,
    ):
        self.shop = shop
        self.shop_id = shop_id
        self.member_id = member_id
        self.keyword_list_id = keyword_list_id
        self.country = country
        self.marketplace = marketplace
        self.raw_profile = raw_profile

    def require_shop(self) -> str:
        if not self.shop:
            raise ErankError(
                "No shop in session context",
                hint="Set ERANK_DEFAULT_SHOP or ensure shop-profile returns a shop.",
            )
        return self.shop

    def require_shop_id(self) -> int:
        if self.shop_id is None:
            raise ErankError(
                "No shop_id in session context",
                hint="Set ERANK_DEFAULT_SHOP_ID or reconnect so shop-profile can be read.",
            )
        return int(self.shop_id)

    def require_member_id(self) -> int:
        if self.member_id is None:
            raise ErankError(
                "No member_id in session context",
                hint="Set ERANK_DEFAULT_MEMBER_ID or reconnect so shop-profile can be read.",
            )
        return int(self.member_id)


_cached: AccountContext | None = None


def reset_context() -> None:
    global _cached
    _cached = None


def _dig_int(obj: Any, *keys: str) -> Optional[int]:
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    return None


def _dig_str(obj: Any, *keys: str) -> Optional[str]:
    if not isinstance(obj, dict):
        return None
    for k in keys:
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _from_profile(profile: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(profile, dict):
        return out
    data = profile.get("data") if isinstance(profile.get("data"), dict) else profile
    shop_obj = data.get("shop") if isinstance(data.get("shop"), dict) else {}
    details = data.get("shop_details") if isinstance(data.get("shop_details"), dict) else {}
    member_obj = data.get("member") if isinstance(data.get("member"), dict) else {}

    out["shop"] = (
        _dig_str(details, "name", "shop_name", "shopName")
        or _dig_str(data, "shop_name", "shopName", "name")
        or _dig_str(shop_obj, "shop_name", "shopName", "name", "login_name")
    )
    out["shop_id"] = (
        _dig_int(data, "shop_id", "shopId")
        or _dig_int(shop_obj, "shop_id", "shopId", "id")
        or _dig_int(details, "shop_id", "id")
    )
    # Prefer not to treat global_rank-like ids as shop_id
    out["member_id"] = (
        _dig_int(data, "member_id", "memberId", "user_id")
        or _dig_int(member_obj, "member_id", "memberId", "id")
    )
    return out


def _from_member_shops(payload: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        items = payload.get("data") or payload.get("shops") or payload.get("items") or []
        if isinstance(items, dict):
            items = items.get("data") or items.get("shops") or []
    else:
        items = []
    if not isinstance(items, list) or not items:
        return out
    first = items[0]
    if not isinstance(first, dict):
        return out
    out["shop"] = _dig_str(first, "name", "shop_name", "shopName", "login_name")
    out["shop_id"] = _dig_int(first, "id", "shop_id", "shopId")
    out["member_id"] = _dig_int(first, "member_id", "memberId")
    return out


def _from_account_identity(payload: Any) -> dict[str, Any]:
    """Parse /api/intercom identity payload (used only for ids — never expose email/hash)."""
    out: dict[str, Any] = {}
    if not isinstance(payload, dict):
        return out
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    out["member_id"] = _dig_int(data, "member_id", "memberId")
    out["shop"] = _dig_str(data, "shop", "shop_name", "shopName")
    out["shop_id"] = _dig_int(data, "shop_id", "shopId")
    return out


def _from_keywordlist_names(payload: Any) -> Optional[int]:
    if not isinstance(payload, dict):
        items = payload if isinstance(payload, list) else []
    else:
        items = payload.get("data") or payload.get("lists") or payload.get("names") or []
        if isinstance(items, dict):
            items = items.get("data") or []
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if isinstance(first, dict):
        return _dig_int(first, "id", "list_id", "keyword_list_id")
    return None


def resolve_context(
    client: ErankHttpClient,
    settings: Settings | None = None,
    *,
    force_refresh: bool = False,
) -> AccountContext:
    """Merge env overrides with live discovery. Cached for the process lifetime."""
    global _cached
    settings = settings or get_settings()
    if _cached is not None and not force_refresh:
        return _cached

    shop = settings.erank_default_shop
    shop_id = settings.erank_default_shop_id
    member_id = settings.erank_default_member_id
    list_id = settings.erank_keyword_list_id
    raw_profile = None

    need_api = shop is None or shop_id is None or member_id is None
    if need_api:
        try:
            raw_profile = client.get("/api/dashboard/shop-profile", referer="/dashboard")
            discovered = _from_profile(raw_profile)
            shop = shop or discovered.get("shop")
            shop_id = shop_id if shop_id is not None else discovered.get("shop_id")
            member_id = member_id if member_id is not None else discovered.get("member_id")
        except ErankError:
            pass

    if shop is None or shop_id is None or member_id is None:
        try:
            shops = client.get("/api/member-shops", referer="/dashboard")
            discovered = _from_member_shops(shops)
            shop = shop or discovered.get("shop")
            shop_id = shop_id if shop_id is not None else discovered.get("shop_id")
            member_id = member_id if member_id is not None else discovered.get("member_id")
        except ErankError:
            pass

    if member_id is None or shop is None:
        # /api/intercom returns account identity (member_id/shop). Not forwarded to tools as-is.
        try:
            identity = client.request(
                "GET",
                "/api/intercom",
                referer="/dashboard",
                allow_telemetry=True,
            )
            discovered = _from_account_identity(identity)
            shop = shop or discovered.get("shop")
            shop_id = shop_id if shop_id is not None else discovered.get("shop_id")
            member_id = member_id if member_id is not None else discovered.get("member_id")
        except ErankError:
            pass

    if list_id is None:
        try:
            names = client.get("/api/keywordlist/names", referer="/dashboard")
            list_id = _from_keywordlist_names(names)
        except ErankError:
            pass

    _cached = AccountContext(
        shop=shop,
        shop_id=shop_id,
        member_id=member_id,
        keyword_list_id=list_id,
        country=settings.erank_default_country,
        marketplace=settings.erank_default_marketplace,
        raw_profile=raw_profile,
    )
    return _cached
