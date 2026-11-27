"""MCP server: semantic eRank tools + raw/replay escape hatches."""

from __future__ import annotations

import json
from typing import Any, Optional

from mcp.server.mcpserver import MCPServer

from erank_mcp.catalog import load_catalog
from erank_mcp.client import ErankError, get_client
from erank_mcp.config import get_settings
from erank_mcp.context import reset_context, resolve_context
from erank_mcp.summarize import compact, keyword_table, wrap_result
from erank_mcp import workflows

mcp = MCPServer(
    "erank",
    instructions=(
        "eRank members API MCP. Authenticate via browser cookies (ERANK_COOKIE_FILE). "
        "Prefer semantic tools (keyword research, rank check, dashboard) over raw_request. "
        "Mutating tools require ERANK_ALLOW_WRITES=1. Telemetry /api/logs is blocked by default."
    ),
)


def _err(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ErankError):
        return exc.to_dict()
    return {"error": str(exc)}


def _require_writes() -> None:
    settings = get_settings()
    if not settings.erank_allow_writes:
        raise ErankError(
            "Writes disabled",
            hint="Set ERANK_ALLOW_WRITES=1 to enable mutating tools.",
        )


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


@mcp.tool()
def erank_session_status() -> dict[str, Any]:
    """Check eRank session health (shop profile, quota, oauth). Never returns cookies."""
    settings = get_settings()
    client = get_client()
    reset_context()
    out: dict[str, Any] = {
        "has_cookie_names": client.cookie_names(),
        "has_session": client.has_session(),
        "catalog_endpoints": load_catalog().endpoint_count,
    }
    try:
        ctx = resolve_context(client, settings, force_refresh=True)
        out["context"] = {
            "shop": ctx.shop,
            "shop_id": ctx.shop_id,
            "member_id": ctx.member_id,
            "keyword_list_id": ctx.keyword_list_id,
            "country": ctx.country,
            "marketplace": ctx.marketplace,
        }
        out["shop_profile"] = compact(ctx.raw_profile, max_list=10) if ctx.raw_profile else None
    except Exception as exc:  # noqa: BLE001
        out["shop_profile"] = _err(exc)
        return out

    try:
        out["quota"] = compact(client.get("/api/quota/daily", referer="/dashboard"))
    except Exception as exc:  # noqa: BLE001
        out["quota"] = _err(exc)

    if ctx.shop_id is not None and ctx.member_id is not None:
        try:
            out["oauth"] = compact(
                client.get(
                    "/api/oauth/check-token-validity",
                    params={"shop_id": ctx.shop_id, "member_id": ctx.member_id},
                    referer="/dashboard",
                )
            )
        except Exception as exc:  # noqa: BLE001
            out["oauth"] = _err(exc)

    out["ok"] = bool(ctx.shop or ctx.shop_id or ctx.member_id)
    return out


# ---------------------------------------------------------------------------
# Quota / dashboard / keyword
# ---------------------------------------------------------------------------


@mcp.tool()
def erank_quota(kind: str = "daily") -> dict[str, Any]:
    """Read quota. kind: daily | none-daily."""
    client = get_client()
    path = "/api/quota/daily" if kind != "none-daily" else "/api/quota/none-daily"
    try:
        return {"quota": client.get(path, referer="/dashboard")}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_dashboard_snapshot(
    sections: Optional[list[str]] = None,
    include_full: bool = False,
) -> dict[str, Any]:
    """
    Dashboard snapshot. sections optional subset of:
    profile, shops, scorecards, competitors, health, news, quota, history.
    Default: profile, shops, scorecards, competitors, quota.
    """
    settings = get_settings()
    client = get_client()
    ctx = resolve_context(client, settings)
    wanted = set(
        sections
        or ["profile", "shops", "scorecards", "competitors", "quota"]
    )
    shop = ctx.shop
    shop_id = ctx.shop_id
    ref = "/dashboard"
    raw: dict[str, Any] = {}
    summary: dict[str, Any] = {}

    try:
        if "profile" in wanted:
            raw["shop_profile"] = client.get("/api/dashboard/shop-profile", referer=ref)
            summary["shop_profile"] = compact(raw["shop_profile"], max_list=8)
        if "shops" in wanted:
            raw["member_shops"] = client.get("/api/member-shops", referer=ref)
            summary["member_shops"] = compact(raw["member_shops"], max_list=8)
        if "scorecards" in wanted:
            raw["soe"] = client.get("/api/dashboard/soe-score-card", referer=ref)
            raw["sales_rank"] = client.get("/api/dashboard/sales-rank-scorecard", referer=ref)
            if shop and shop_id is not None:
                raw["inventory"] = client.get(
                    f"/api/dashboard/inventory-value/{shop_id}/{shop}", referer=ref
                )
            else:
                raw["inventory"] = {"_skipped": "shop/shop_id unknown"}
            summary["scorecards"] = {
                "soe": compact(raw["soe"]),
                "sales_rank": compact(raw["sales_rank"]),
                "inventory": compact(raw["inventory"]),
            }
        if "competitors" in wanted:
            raw["competitors"] = client.get("/api/dashboard/competitors", referer=ref)
            raw["graph"] = client.get("/api/competitor/graph", referer=ref)
            summary["competitors"] = compact(raw["competitors"], max_list=15)
        if "health" in wanted:
            raw["health"] = client.get("/api/health-check/dashboard", referer=ref)
            raw["listings_health"] = client.get(
                "/api/listings/health-check",
                params={
                    "order_direction": "desc",
                    "order_field": "total_issues",
                    "page": 1,
                    "per_page": 5,
                },
                referer=ref,
            )
            summary["health"] = compact(raw["health"])
        if "news" in wanted:
            raw["news"] = client.get("/api/dashboard/news", referer=ref)
            raw["whats_new"] = client.get(
                "/api/dashboard/whats-new", params={"lang": "en"}, referer=ref
            )
            summary["news"] = compact(raw["news"], max_list=5)
        if "quota" in wanted:
            raw["quota"] = client.get("/api/quota/daily", referer=ref)
            summary["quota"] = compact(raw["quota"])
        if "history" in wanted:
            raw["search_history"] = client.get("/api/search-history", referer=ref)
            summary["search_history"] = compact(raw["search_history"], max_list=10)
        return wrap_result(summary, raw if include_full else summary, include_full=include_full)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_keyword_research(
    keyword: str,
    country: Optional[str] = None,
    marketplace: Optional[str] = None,
    include_serp: bool = False,
    include_marketplace_stats: bool = False,
    related_per_page: int = 100,
    include_full: bool = False,
) -> dict[str, Any]:
    """
    Full keyword-tool research flow from the HAR (stats, related, tags, competition,
    google-data, difficulty). Set include_serp / include_marketplace_stats for heavier calls.
    """
    settings = get_settings()
    client = get_client()
    ctx = resolve_context(client, settings)
    country = country or ctx.country
    marketplace = marketplace or ctx.marketplace
    try:
        # Quota check first
        quota = client.get("/api/quota/daily", referer="/keyword-tool")
        raw = workflows.flow_keyword_tool(
            client,
            settings,
            keyword,
            country=country,
            marketplace=marketplace,
            include_serp=include_serp,
            related_per_page=related_per_page,
        )
        raw["quota_before"] = quota

        if include_marketplace_stats:
            markets = client.get(
                "/api/keyword-tool/stats/available-marketplaces",
                referer=f"/keyword-tool?keyword={keyword}&country={country}&source={marketplace}",
            )
            raw["available_marketplaces"] = markets
            mp_stats = {}
            names = []
            if isinstance(markets, dict):
                names = markets.get("data") or markets.get("marketplaces") or []
            if isinstance(names, list):
                for m in names[:10]:
                    mname = m if isinstance(m, str) else (m.get("id") or m.get("name"))
                    if not mname:
                        continue
                    mp_stats[str(mname)] = client.get(
                        "/api/keyword-tool/stats/marketplace",
                        params={
                            "keyword": keyword,
                            "country": country,
                            "marketplace": mname,
                            "source": marketplace,
                        },
                        referer=f"/keyword-tool?keyword={keyword}",
                    )
            raw["marketplace_stats"] = mp_stats

        table = keyword_table(raw)
        summary = {
            "keyword": keyword,
            "country": country,
            "marketplace": marketplace,
            "table": table,
            "quota": compact(quota),
        }
        return wrap_result(summary, raw, include_full=include_full)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_keyword_list(
    action: str = "names",
    list_id: Optional[int] = None,
    marketplace: str = "etsy",
    country: str = "USA",
    flag: int = 0,
    page: int = 1,
    per_page: int = 10,
    sort_by: str = "keyword",
    sort_dir: str = "asc",
    include_stats: bool = True,
    include_google: bool = True,
    include_competition: bool = True,
) -> dict[str, Any]:
    """
    Keyword list operations.
    action: names | terms | terms_kl | quota_names | quota_terms
    """
    settings = get_settings()
    client = get_client()
    ctx = resolve_context(client, settings)
    lid = list_id if list_id is not None else ctx.keyword_list_id
    ref = "/keyword-lists"
    try:
        if action == "names":
            return {"data": client.get("/api/keywordlist/names", referer=ref)}
        if action == "terms":
            return {"data": client.get("/api/keywordlist/terms", referer=ref)}
        if action == "terms_kl":
            if lid is None:
                return {
                    "error": "list_id required",
                    "hint": "Pass list_id or set ERANK_KEYWORD_LIST_ID / discover via action=names",
                }
            path = f"/api/keywordlist/terms-kl/{lid}/{marketplace}/{country}/{flag}"
            return {
                "data": client.get(
                    path,
                    params={
                        "page": page,
                        "per_page": per_page,
                        "sort_by": sort_by,
                        "sort_dir": sort_dir,
                        "include_stats": 1 if include_stats else 0,
                        "include_google": 1 if include_google else 0,
                        "include_competition": 1 if include_competition else 0,
                    },
                    referer=ref,
                )
            }
        if action == "quota_names":
            return {"data": client.get("/api/keywordlist/quota/names", referer=ref)}
        if action == "quota_terms":
            if lid is None:
                return {"error": "list_id required for quota_terms"}
            return {"data": client.get(f"/api/keywordlist/quota/terms/{lid}", referer=ref)}
        return {"error": f"Unknown action: {action}"}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_save_keyword(
    keyword: str,
    list_id: Optional[int] = None,
    marketplace: Optional[str] = None,
    country: Optional[str] = None,
) -> dict[str, Any]:
    """Save a keyword into a keyword list (mutating; requires ERANK_ALLOW_WRITES=1)."""
    try:
        _require_writes()
        settings = get_settings()
        client = get_client()
        ctx = resolve_context(client, settings)
        lid = list_id if list_id is not None else ctx.keyword_list_id
        if lid is None:
            return {
                "error": "list_id required",
                "hint": "Pass list_id or discover via erank_keyword_list(action='names')",
            }
        body = {
            "keyword": keyword,
            "list_id": lid,
            "marketplace": marketplace or ctx.marketplace,
            "country": country or "USA",
        }
        return {
            "data": client.post(
                "/api/keywordlist/save-keyword",
                json_body=body,
                referer="/keyword-tool",
            )
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Rank / competitor / shop / top sellers / trending / health / settings
# ---------------------------------------------------------------------------


@mcp.tool()
def erank_rank_check(
    keyword: str,
    shop: Optional[str] = None,
    country: Optional[str] = None,
    marketplace: Optional[str] = None,
    max_offset: int = 100,
    include_serp: bool = True,
    include_full: bool = False,
) -> dict[str, Any]:
    """Rank checker for a keyword against a shop (paginated single-term + optional SERP)."""
    settings = get_settings()
    client = get_client()
    ctx = resolve_context(client, settings)
    shop = shop or ctx.require_shop()
    country = country or ctx.country
    marketplace = marketplace or ctx.marketplace
    try:
        raw = workflows.flow_rank_checker(
            client,
            settings,
            keyword,
            shop=shop,
            country=country,
            marketplace=marketplace,
            max_offset=max_offset,
        )
        if not include_serp:
            raw.pop("serp", None)
        summary = {
            "keyword": keyword,
            "shop": shop,
            "pages": len(raw.get("single_term_pages") or []),
            "keyword_stats": compact(raw.get("keyword_stats")),
            "history": compact(raw.get("history"), max_list=10),
        }
        return wrap_result(summary, raw, include_full=include_full)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_competitor_intel(
    shop_name: Optional[str] = None,
    shop_id: Optional[int] = None,
    track: bool = False,
    include_full: bool = False,
) -> dict[str, Any]:
    """Competitor sales intel. Set track=true (and ERANK_ALLOW_WRITES=1) to track a shop."""
    settings = get_settings()
    client = get_client()
    ctx = resolve_context(client, settings)
    shop_name = shop_name or ctx.require_shop()
    try:
        raw = workflows.flow_competitor(
            client, settings, shop_name=shop_name, shop_id=shop_id
        )
        if track:
            _require_writes()
            body: dict[str, Any] = {"shop_name": shop_name}
            if shop_id:
                body["shop_id"] = shop_id
            raw["track"] = client.post(
                "/api/competitor/competitors/track",
                json_body=body,
                referer="/competitor-sales",
            )
        summary = {
            "shop_name": shop_name,
            "daily_sales": compact(raw.get("daily_sales"), max_list=10),
            "sales_history": compact(raw.get("sales_history"), max_list=10),
        }
        return wrap_result(summary, raw, include_full=include_full)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_shop_analyze(
    shop: str,
    max_listing_offset: int = 100,
    include_full: bool = False,
) -> dict[str, Any]:
    """Analyze a shop: profile, badge, listings-fresh pages, sales history, top tags."""
    settings = get_settings()
    client = get_client()
    try:
        raw = workflows.flow_shop_info(
            client, settings, shop, max_listing_offset=max_listing_offset
        )
        summary = {
            "shop": shop,
            "info": compact(raw.get("info"), max_list=10),
            "badge": compact(raw.get("badge")),
            "listing_pages": len(raw.get("listings_fresh") or []),
        }
        return wrap_result(summary, raw, include_full=include_full)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_top_sellers(
    mode: str = "list",
    page: int = 1,
    per_page: int = 100,
    country: str = "",
    category: str = "",
    year_started: str = "all_time",
    sort_by: str = "sales",
    sort_order: str = "desc",
    only_active: bool = False,
) -> dict[str, Any]:
    """Top sellers. mode: list | yesterday | countries | most_sales_etsy."""
    client = get_client()
    ref = "/top-sellers"
    try:
        if mode == "countries":
            return {"data": client.get("/api/top-sellers/countries", referer=ref)}
        if mode == "yesterday":
            return {
                "data": client.get(
                    "/api/top-sellers/most-sales-yesterday",
                    params={"page": page, "perPage": per_page},
                    referer=ref,
                )
            }
        if mode == "most_sales_etsy":
            return {
                "data": client.get(
                    "/api/top-sellers/most-sales-etsy",
                    params={"country": country or "ALL"},
                    referer=ref,
                )
            }
        return {
            "data": client.get(
                "/api/top-sellers",
                params={
                    "yearStarted": year_started,
                    "category": category,
                    "country": country,
                    "page": page,
                    "perPage": per_page,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                    "onlyActiveShops": str(only_active).lower(),
                },
                referer=ref,
            )
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_trending(
    kind: str = "report",
    marketplace: Optional[str] = None,
    country: str = "USA",
    period: str = "monthly",
    category: str = "all",
    date: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    """
    Trending data.
    kind: report | buzz | availability
    date: optional YYYYMM for historical trending-report.
    """
    settings = get_settings()
    client = get_client()
    ctx = resolve_context(client, settings)
    marketplace = marketplace or ctx.marketplace
    try:
        if kind == "availability":
            return {
                "data": client.get("/api/trending-report/availability", referer="/trending")
            }
        if kind == "buzz":
            return {
                "data": client.get(
                    "/api/trend-buzz",
                    params={
                        "marketplace": marketplace,
                        "country": country,
                        "period": "one",
                        "category": "Keyword" if category == "all" else category,
                    },
                    referer="/trend-buzz",
                )
            }
        params: dict[str, Any] = {
            "category": category,
            "limit": limit,
            "marketplace": marketplace,
            "period": period,
        }
        if date:
            params["date"] = date
        return {
            "data": client.get("/api/trending-report", params=params, referer="/trending")
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_listing_health(
    page: int = 1,
    per_page: int = 5,
    order_field: str = "total_issues",
    order_direction: str = "desc",
) -> dict[str, Any]:
    """Listing health-check dashboard + paginated listing issues."""
    client = get_client()
    ref = "/dashboard"
    try:
        return {
            "dashboard": client.get("/api/health-check/dashboard", referer=ref),
            "listings": client.get(
                "/api/listings/health-check",
                params={
                    "order_direction": order_direction,
                    "order_field": order_field,
                    "page": page,
                    "per_page": per_page,
                },
                referer=ref,
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_settings_read() -> dict[str, Any]:
    """Read settings: member, shops, marketplaces, categories, invoices, preferences."""
    settings = get_settings()
    client = get_client()
    try:
        return compact(workflows.flow_settings(client, settings), max_list=20)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ---------------------------------------------------------------------------
# Escape hatches
# ---------------------------------------------------------------------------


@mcp.tool()
def erank_raw_request(
    method: str,
    path: str,
    query_json: Optional[str] = None,
    body_json: Optional[str] = None,
    referer: Optional[str] = None,
) -> dict[str, Any]:
    """
    Escape hatch: call any /api path. query_json and body_json are JSON strings.
    Telemetry paths (/api/logs) blocked unless ERANK_ALLOW_TELEMETRY=1.
    Writes should still respect ERANK_ALLOW_WRITES for safety on known mutators.
    """
    client = get_client()
    method_u = method.upper()
    try:
        if method_u in {"POST", "PUT", "PATCH", "DELETE"}:
            mutators = (
                "save-keyword",
                "/track",
                "track-preference",
                "quota/increment",
                "member-preferences/save",
            )
            if any(m in path for m in mutators):
                _require_writes()
        params = json.loads(query_json) if query_json else None
        body = json.loads(body_json) if body_json else None
        if params is not None and not isinstance(params, dict):
            return {"error": "query_json must decode to an object"}
        data = client.request(
            method_u,
            path,
            params=params,
            json_body=body,
            referer=referer,
        )
        return {"data": compact(data)}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_replay_flow(
    flow_name: str,
    keyword: Optional[str] = None,
    shop: Optional[str] = None,
    include_full: bool = False,
) -> dict[str, Any]:
    """
    Replay a HAR-mirrored flow.
    flow_name: dashboard | keyword_tool_full | rank_checker | competitor_shop |
               top_sellers | trending | settings | shop_info
    """
    settings = get_settings()
    client = get_client()
    try:
        if flow_name == "dashboard":
            raw = workflows.flow_dashboard(client, settings)
        elif flow_name == "keyword_tool_full":
            if not keyword:
                return {"error": "keyword required for keyword_tool_full"}
            raw = workflows.flow_keyword_tool(client, settings, keyword)
        elif flow_name == "rank_checker":
            if not keyword:
                return {"error": "keyword required for rank_checker"}
            raw = workflows.flow_rank_checker(client, settings, keyword, shop=shop)
        elif flow_name == "competitor_shop":
            raw = workflows.flow_competitor(client, settings, shop_name=shop)
        elif flow_name == "top_sellers":
            raw = workflows.flow_top_sellers(client, settings)
        elif flow_name == "trending":
            raw = workflows.flow_trending(client, settings)
        elif flow_name == "settings":
            raw = workflows.flow_settings(client, settings)
        elif flow_name == "shop_info":
            if not shop:
                return {"error": "shop required for shop_info"}
            raw = workflows.flow_shop_info(client, settings, shop)
        else:
            return {
                "error": f"Unknown flow: {flow_name}",
                "available": list(workflows.FLOWS.keys()),
            }
        keys = list(raw.keys()) if isinstance(raw, dict) else []
        summary = {"flow": flow_name, "keys": keys, "key_count": len(keys)}
        return wrap_result(summary, raw, include_full=include_full)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


@mcp.tool()
def erank_catalog_info(group: Optional[str] = None) -> dict[str, Any]:
    """Inspect HAR-derived API catalog (endpoint templates). Optional feature group filter."""
    cat = load_catalog()
    if group:
        eps = cat.by_group(group)
        return {
            "group": group,
            "count": len(eps),
            "endpoints": [
                {
                    "method": e["method"],
                    "path_template": e["path_template"],
                    "har_count": e.get("har_count"),
                }
                for e in eps
            ],
        }
    return {
        "endpoint_count": cat.endpoint_count,
        "groups": cat.groups(),
        "marketplaces_seen": cat.marketplaces_seen(),
    }


def run() -> None:
    mcp.run(transport="stdio")
