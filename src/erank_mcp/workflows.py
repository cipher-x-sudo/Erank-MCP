"""Multi-step flows mirroring the captured HAR browsing session (minus telemetry)."""

from __future__ import annotations

from typing import Any

from erank_mcp.client import ErankHttpClient
from erank_mcp.config import Settings
from erank_mcp.context import resolve_context


def flow_dashboard(client: ErankHttpClient, settings: Settings) -> dict[str, Any]:
    ctx = resolve_context(client, settings)
    shop = ctx.require_shop()
    shop_id = ctx.require_shop_id()
    member_id = ctx.require_member_id()
    ref = "/dashboard"
    out: dict[str, Any] = {}
    steps = [
        ("shop_profile", "GET", "/api/dashboard/shop-profile", None, None),
        ("member_preferences", "GET", "/api/account/member-preferences", None, None),
        ("member_shops", "GET", "/api/member-shops", None, None),
        ("last_refresh", "GET", "/api/refresh-data/listings/last-refresh", None, None),
        ("motd", "GET", "/api/motd-v3/dashboard", None, None),
        ("soe_score_card", "GET", "/api/dashboard/soe-score-card", None, None),
        ("sales_rank_scorecard", "GET", "/api/dashboard/sales-rank-scorecard", None, None),
        (
            "inventory_value",
            "GET",
            f"/api/dashboard/inventory-value/{shop_id}/{shop}",
            None,
            None,
        ),
        ("search_history", "GET", "/api/search-history", None, None),
        ("top_sellers_most", "GET", "/api/top-sellers/most-sales-etsy", {"country": "ALL"}, None),
        ("trending_category", "GET", "/api/dashboard/trending-etsy-category-marketplace", None, None),
        ("competitors", "GET", "/api/dashboard/competitors", None, None),
        ("competitor_graph", "GET", "/api/competitor/graph", None, None),
        ("refresh_status", "GET", "/api/refresh-data/status", None, None),
        ("shop_ga", "GET", "/api/ga4/shop-ga", {"shop_id": shop_id}, None),
        ("check_ga", "GET", "/api/ga4/check-my-ga", {"shop_id": shop_id}, None),
        ("top_listings_changes", "GET", "/api/dashboard/top-listings-changes", {"shop_id": shop_id}, None),
        ("listings_analyze_history", "GET", "/api/listings/analyze-history", None, None),
        ("shop_analyze_history", "GET", "/api/shop/analyze-history", None, None),
        ("keywordlist_names", "GET", "/api/keywordlist/names", None, None),
        ("etsy_popularity", "GET", "/api/etsy-popularity", None, None),
        ("events", "GET", "/api/dashboard/events", {"limit": 5}, None),
        ("similar_listings", "GET", "/api/dashboard/similar-listings", None, None),
        ("news", "GET", "/api/dashboard/news", None, None),
        ("whats_new", "GET", "/api/dashboard/whats-new", {"lang": "en"}, None),
        ("learn_and_grow", "GET", "/api/dashboard/learn-and-grow", {"lang": "en"}, None),
        ("category_report", "GET", "/api/dashboard/category-report", {"category": "accessories"}, None),
        ("paddle", "GET", "/api/check-paddle-restriction", None, None),
        (
            "oauth_validity",
            "GET",
            "/api/oauth/check-token-validity",
            {"shop_id": shop_id, "member_id": member_id},
            None,
        ),
        ("quota_none_daily", "GET", "/api/quota/none-daily", None, None),
        ("health_dashboard", "GET", "/api/health-check/dashboard", None, None),
        (
            "listings_health",
            "GET",
            "/api/listings/health-check",
            {
                "order_direction": "desc",
                "order_field": "total_issues",
                "page": 1,
                "per_page": 5,
            },
            None,
        ),
        ("track_preference", "GET", "/api/competitor/competitors/track-preference", None, None),
        ("oauth_revoked", "GET", "/api/oauth/check-all-revoked-tokens", None, None),
        ("sales_history", "GET", "/api/competitor/sales-history", {"shop_name": shop}, None),
        ("active_listings", "GET", f"/api/dashboard/total-active-listings/{shop}", None, None),
    ]
    for name, method, path, params, body in steps:
        try:
            out[name] = client.request(method, path, params=params, json_body=body, referer=ref)
        except Exception as exc:  # noqa: BLE001 — collect per-step errors in replay
            out[name] = {"_error": str(exc)}
    return out


def flow_keyword_tool(
    client: ErankHttpClient,
    settings: Settings,
    keyword: str,
    *,
    country: str | None = None,
    marketplace: str | None = None,
    include_serp: bool = True,
    related_per_page: int = 100,
    match: str = "default",
    page: int = 1,
) -> dict[str, Any]:
    ctx = resolve_context(client, settings)
    country = country or ctx.country
    marketplace = marketplace or ctx.marketplace
    ref = f"/keyword-tool?keyword={keyword}&country={country}&source={marketplace}"
    out: dict[str, Any] = {"keyword": keyword, "country": country, "marketplace": marketplace}
    # UI "Match:" dropdown -> exactly one opensearch filter is true
    if match not in ("exact", "phrase", "default", "broad"):
        raise ValueError(f"match must be exact|phrase|default|broad, got {match!r}")
    match_filters = {
        f"opensearch_filters[{m}_match]": str(m == match).lower()
        for m in ("exact", "phrase", "default", "broad")
    }

    out["autocomplete"] = client.get(
        "/api/keyword-tool/autocomplete",
        params={"keyword": keyword, "marketplace": marketplace, "country": country.lower()},
        referer=ref,
    )
    out["stats"] = client.get(
        "/api/keyword-tool/stats",
        params={"keyword": keyword, "country": country, "marketplace": marketplace},
        referer=ref,
    )
    out["motd"] = client.get("/api/motd-v3/keyword-tool", referer=ref)
    out["presets"] = client.get("/api/presets", params={"section": "kt_keyword_ideas"}, referer=ref)

    related = client.get(
        "/api/keyword-tool/related-searches",
        params={
            "keyword": keyword,
            "marketplace": marketplace,
            "country": country,
            **match_filters,
            "page": page,
            "per_page": related_per_page,
        },
        referer=ref,
    )
    out["related_searches"] = related

    related_keywords = _extract_related_keywords(related, keyword)

    out["near_matches"] = client.get(
        "/api/keyword-tool/near-matches",
        params={"country": country, "keyword": keyword, "marketplace": marketplace},
        referer=ref,
    )
    out["top_listings"] = client.get(
        "/api/keyword-tool/top-listings",
        params={"keyword": keyword, "marketplace": marketplace, "country": country},
        referer=ref,
    )
    out["quota"] = client.get("/api/quota/daily", referer=ref)
    out["etsy_tags"] = client.get(
        "/api/keyword-tool/etsy-tags",
        params={
            "keyword": keyword,
            "marketplace": marketplace,
            "country": country,
            **match_filters,
        },
        referer=ref,
    )

    post_body = {
        "keyword": keyword,
        "marketplace": marketplace,
        "country": country,
        "keywords": related_keywords,
    }
    out["competition"] = client.post(
        "/api/keyword-tool/competition", json_body=post_body, referer=ref
    )
    out["google_data"] = client.post(
        "/api/keyword-tool/google-data", json_body=post_body, referer=ref
    )
    # KD endpoint wants {kw: number} maps for competition + avg_searches (per HAR), not a keyword list
    out["keyword_difficulty"] = client.post(
        "/api/keyword-tool/keyword-difficulty",
        json_body={
            "keyword": keyword,
            "marketplace": marketplace,
            "country": country,
            "competition": _order_values(out["competition"], related_keywords),
            "avg_searches": _order_values(
                {r["keyword"]: r.get("avg_searches") for r in _rows(related)}, related_keywords
            ),
            "row_offset": (page - 1) * related_per_page,
        },
        referer=ref,
    )

    if include_serp:
        out["serp_analysis"] = client.get(
            "/api/keyword-tool/serp-analysis",
            params={"country": country, "keyword": keyword, "marketplace": marketplace},
            referer=ref,
        )

    out["available_marketplaces"] = client.get(
        "/api/keyword-tool/stats/available-marketplaces", referer=ref
    )
    return out


def _rows(related: Any) -> list[dict[str, Any]]:
    """related-searches returns {"data": [{keyword, avg_searches: {...}, ...}], "meta": {...}}."""
    items = related.get("data") if isinstance(related, dict) else related
    return [i for i in items or [] if isinstance(i, dict) and i.get("keyword")]


def _order_values(metric_map: Any, keywords: list[str]) -> dict[str, Any]:
    """{kw: {"order_value": n, ...}} -> {kw: n} for the given keywords."""
    m = metric_map if isinstance(metric_map, dict) else {}
    out = {}
    for k in keywords:
        v = m.get(k)
        out[k] = v.get("order_value", 0) if isinstance(v, dict) else (v or 0)
    return out


def _extract_related_keywords(related: Any, seed: str) -> list[str]:
    keywords = [seed] + [str(r["keyword"]) for r in _rows(related)]
    # Deduplicate preserving order; cap like UI (~100)
    seen: set[str] = set()
    out: list[str] = []
    for k in keywords:
        kl = k.lower()
        if kl not in seen:
            seen.add(kl)
            out.append(k)
        if len(out) >= 100:
            break
    return out


def flow_rank_checker(
    client: ErankHttpClient,
    settings: Settings,
    keyword: str,
    *,
    shop: str | None = None,
    country: str | None = None,
    marketplace: str | None = None,
    max_offset: int = 400,
    page_size: int = 100,
) -> dict[str, Any]:
    ctx = resolve_context(client, settings)
    shop = shop or ctx.require_shop()
    country = country or ctx.country
    marketplace = marketplace or ctx.marketplace
    ref = "/rank-checker"
    out: dict[str, Any] = {}
    out["motd"] = client.get("/api/motd-v3/rank-checker", referer=ref)
    out["shops"] = client.get("/api/rank-checker/shops", referer=ref)
    out["history"] = client.get("/api/rank-checker/get-history", referer=ref)
    out["countries"] = client.get("/api/rank-checker/countries", referer=ref)
    out["quota"] = client.get("/api/quota/daily", referer=ref)
    out["keyword_stats"] = client.get(
        "/api/rank-checker/keyword-stats",
        params={"keyword": keyword, "country": country, "marketplace": marketplace},
        referer=ref,
    )
    pages = []
    for offset in range(0, max_offset + 1, page_size):
        pages.append(
            client.get(
                "/api/rank-checker/single-term",
                params={
                    "keyword": keyword,
                    "shop": shop,
                    "shop_name": shop,
                    "offset": offset,
                },
                referer=ref,
            )
        )
    out["single_term_pages"] = pages
    out["serp"] = client.post(
        "/api/rank-checker/serp",
        json_body={"keyword": keyword, "shop": shop, "country": country, "marketplace": marketplace},
        referer=ref,
    )
    return out


def flow_competitor(
    client: ErankHttpClient,
    settings: Settings,
    *,
    shop_name: str | None = None,
    shop_id: int | None = None,
) -> dict[str, Any]:
    ctx = resolve_context(client, settings)
    shop_name = shop_name or ctx.require_shop()
    member_id = ctx.require_member_id()
    ref = "/competitor-sales"
    out: dict[str, Any] = {}
    out["motd"] = client.get("/api/motd-v3/competitor-sales", referer=ref)
    out["quota"] = client.get("/api/quota/none-daily", referer=ref)
    out["daily_sales"] = client.get("/api/competitor/daily-sales", referer=ref)
    out["full_sales"] = client.get("/api/competitor/full-sales", referer=ref)
    out["tracking_started"] = client.get(
        "/api/competitor/tracking-started",
        params={"member_id": member_id},
        referer=ref,
    )
    out["track_preference"] = client.get(
        "/api/competitor/competitors/track-preference", referer=ref
    )
    if shop_id:
        out["shop_sales"] = client.get(
            f"/api/competitor/shop-sales/{shop_id}", referer=ref
        )
    out["sales_history"] = client.get(
        "/api/competitor/sales-history/",
        params={"shop_name": shop_name},
        referer=ref,
    )
    out["shops"] = client.get("/api/competitor/shops", referer=ref)
    return out


def flow_top_sellers(client: ErankHttpClient, settings: Settings) -> dict[str, Any]:
    ref = "/top-sellers"
    out: dict[str, Any] = {}
    out["motd"] = client.get("/api/motd-v3/top-sellers", referer=ref)
    out["countries"] = client.get("/api/top-sellers/countries", referer=ref)
    out["list"] = client.get(
        "/api/top-sellers",
        params={
            "yearStarted": "all_time",
            "category": "",
            "country": "",
            "page": 1,
            "perPage": 100,
            "sort_by": "sales",
            "sort_order": "desc",
            "onlyActiveShops": "false",
        },
        referer=ref,
    )
    out["most_sales_yesterday"] = client.get(
        "/api/top-sellers/most-sales-yesterday",
        params={"page": 1, "perPage": 100},
        referer=ref,
    )
    return out


def flow_shop_info(
    client: ErankHttpClient,
    settings: Settings,
    shop: str,
    *,
    max_listing_offset: int = 400,
) -> dict[str, Any]:
    ref = f"/shop-info/{shop}"
    out: dict[str, Any] = {"shop": shop}
    out["info"] = client.get(f"/api/shop-info/{shop}", referer=ref)
    out["badge"] = client.get(f"/api/shop-info/{shop}/badge", referer=ref)
    pages = []
    for offset in range(0, max_listing_offset + 1, 100):
        pages.append(
            client.get(
                f"/api/shop-info/{shop}/listings-fresh",
                params={"offset": offset},
                referer=ref,
            )
        )
    out["listings_fresh"] = pages
    out["sales_history"] = client.get(
        "/api/competitor/sales-history/",
        params={"shop_name": shop},
        referer=ref,
    )
    out["quota"] = client.get("/api/quota/daily", referer=ref)
    try:
        out["top_tags"] = client.post(
            "/api/competitor/top-tags",
            json_body={"shop_name": shop},
            referer=ref,
        )
    except Exception as exc:  # noqa: BLE001
        out["top_tags"] = {"_error": str(exc)}
    return out


def flow_trending(client: ErankHttpClient, settings: Settings) -> dict[str, Any]:
    ref = "/trending"
    out: dict[str, Any] = {}
    out["motd_buzz"] = client.get("/api/motd-v3/trend-buzz", referer="/trend-buzz")
    ctx = resolve_context(client, settings)
    out["trend_buzz"] = client.get(
        "/api/trend-buzz",
        params={
            "marketplace": ctx.marketplace,
            "country": "USA",
            "period": "one",
            "category": "Keyword",
        },
        referer="/trend-buzz",
    )
    out["availability"] = client.get("/api/trending-report/availability", referer=ref)
    out["motd"] = client.get("/api/motd-v3/trending", referer=ref)
    out["report"] = client.get(
        "/api/trending-report",
        params={
            "category": "all",
            "limit": 100,
            "marketplace": ctx.marketplace,
            "period": "monthly",
        },
        referer=ref,
    )
    return out


def flow_settings(client: ErankHttpClient, settings: Settings) -> dict[str, Any]:
    ctx = resolve_context(client, settings)
    mid = ctx.require_member_id()
    shop_id = ctx.require_shop_id()
    ref = "/settings"
    out: dict[str, Any] = {}
    out["motd"] = client.get("/api/motd-v3/settings", referer=ref)
    out["invoices"] = client.get(f"/api/settings/invoices/{mid}", referer=ref)
    out["shop_list"] = client.get(f"/api/settings/shop-list/{mid}", referer=ref)
    out["marketplaces"] = client.get("/api/settings/marketplaces", referer=ref)
    out["categories"] = client.get("/api/settings/categories", referer=ref)
    out["preferences"] = client.get("/api/account/member-preferences", referer=ref)
    out["member"] = client.get(f"/api/settings/member/{mid}", referer=ref)
    out["oauth"] = client.get(
        "/api/oauth/check-token-validity",
        params={"shop_id": shop_id, "member_id": mid},
        referer=ref,
    )
    return out


FLOWS = {
    "dashboard": flow_dashboard,
    "keyword_tool_full": flow_keyword_tool,
    "rank_checker": flow_rank_checker,
    "competitor_shop": flow_competitor,
    "top_sellers": flow_top_sellers,
    "trending": flow_trending,
    "settings": flow_settings,
    "shop_info": flow_shop_info,
}
