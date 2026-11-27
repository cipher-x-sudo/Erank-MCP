"""Compact summaries for agent-friendly tool responses."""

from __future__ import annotations

from typing import Any


def compact(data: Any, *, max_list: int = 25, depth: int = 0, max_depth: int = 4) -> Any:
    if depth >= max_depth:
        return "...(truncated)"
    if isinstance(data, dict):
        return {k: compact(v, max_list=max_list, depth=depth + 1, max_depth=max_depth) for k, v in data.items()}
    if isinstance(data, list):
        if len(data) > max_list:
            head = [compact(x, max_list=max_list, depth=depth + 1, max_depth=max_depth) for x in data[:max_list]]
            return head + [f"...(+{len(data) - max_list} more)"]
        return [compact(x, max_list=max_list, depth=depth + 1, max_depth=max_depth) for x in data]
    if isinstance(data, str) and len(data) > 500:
        return data[:500] + "..."
    return data


def _v(metric: Any) -> Any:
    """eRank cells are {"value": "2,272", "order_value": 2272, ...}; return the display value."""
    if isinstance(metric, dict):
        v = metric.get("value", metric.get("avg_searches"))
        return None if v in ("", "Unknown", "N/A") else v
    return metric


def _trend(trend: Any) -> list[Any] | None:
    """search_trend is a list of {date, value} (rows) or {yyyymm: n} (marketplace stats)."""
    if isinstance(trend, list):
        return [t.get("value") for t in trend if isinstance(t, dict)]
    if isinstance(trend, dict):
        return [trend[k] for k in sorted(trend)]
    return None


def _kw_row(item: dict[str, Any], *, comp: dict, kd: dict, google: dict, tags: dict) -> dict[str, Any]:
    """One row with the same columns as the eRank Keyword Ideas / Near Matches table."""
    kw = str(item.get("keyword") or item.get("term"))
    row = {
        "keyword": kw,
        "search_trend": _trend(item.get("search_trend")),
        "avg_searches": _v(item.get("avg_searches")),
        "avg_clicks": _v(item.get("avg_clicks")),
        "avg_ctr": _v(item.get("ctr")),
        "kd": _v(item.get("keyword_difficulty")) or _v(kd.get(kw)),
        "etsy_competition": _v(comp.get(kw)) or _v(item.get("competition")),
        "tag_occurrences": item.get("occurrences", tags.get(kw)),
        "chars": item.get("character_count", len(kw)),
        "google_searches": _v(google.get(kw)) or _v(item.get("google")),
        "is_top_tag": kw in tags,
    }
    return {k: v for k, v in row.items() if v is not None}


def _as_map(blob: Any) -> dict[str, Any]:
    return blob if isinstance(blob, dict) else {}


def _as_list(blob: Any) -> list[Any]:
    if isinstance(blob, dict):
        blob = blob.get("data")
    return blob if isinstance(blob, list) else []


def _ctx(payload: dict[str, Any]) -> dict[str, dict]:
    tags = {t["keyword"]: t.get("occurrences") for t in _as_list(payload.get("etsy_tags")) if isinstance(t, dict) and t.get("keyword")}
    return {
        "comp": _as_map(payload.get("competition")),
        "kd": _as_map(payload.get("keyword_difficulty")),
        "google": _as_map(payload.get("google_data")),
        "tags": tags,
    }


def keyword_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Keyword Ideas tab: every related-searches row merged with competition / KD / Google / tags."""
    ctx = _ctx(payload)
    return [_kw_row(i, **ctx) for i in _as_list(payload.get("related_searches")) if isinstance(i, dict) and i.get("keyword")]


def top_tags(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Tags used by top listings for this search, most used first."""
    tags = _ctx(payload)["tags"]
    return [{"keyword": k, "occurrences": n} for k, n in sorted(tags.items(), key=lambda kv: -(kv[1] or 0))]


def near_matches_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    ctx = _ctx(payload)
    return [_kw_row(i, **ctx) for i in _as_list(payload.get("near_matches")) if isinstance(i, dict) and i.get("keyword")]


def seed_stats(payload: dict[str, Any]) -> dict[str, Any]:
    s = _as_map(payload.get("stats"))
    return {
        "avg_searches": _v(s.get("avg_searches")),
        "avg_clicks": _v(s.get("avg_clicks")),
        "avg_ctr": _v(s.get("ctr")),
        "etsy_competition": _v(s.get("competition")),
        "search_trend": [{"month": t.get("y"), "value": next((v for k, v in t.items() if k != "y"), None)} for t in s.get("search_trend") or [] if isinstance(t, dict)],
    }


def top_listings_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    tl = _as_map(payload.get("top_listings")).get("listings")
    keep = ("rank", "listing_id", "title", "shop_name", "price", "views", "daily_views", "num_favorers", "age_in_days", "est_sales", "est_revenue", "tags")
    out = []
    for l in _as_list(tl):
        if not isinstance(l, dict):
            continue
        row = {k: l.get(k) for k in keep}
        # eRank sends no links; Etsy URLs are derivable from id / shop name
        row["listing_url"] = f"https://www.etsy.com/listing/{l['listing_id']}" if l.get("listing_id") else None
        row["shop_url"] = f"https://www.etsy.com/shop/{l['shop_name']}" if l.get("shop_name") else None
        imgs = l.get("images") or []
        row["image_url"] = imgs[0].get("url_75x75") if imgs and isinstance(imgs[0], dict) else None
        row["shop_image_url"] = l.get("shop_image_url")
        out.append(row)
    return out


def serp_summary(payload: dict[str, Any]) -> dict[str, Any] | None:
    s = payload.get("serp_analysis")
    if not isinstance(s, dict):
        return None
    return {k: s.get(k) for k in ("stats", "popular_categories", "prices", "processing_times", "word_cloud") if k in s}


def marketplaces_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "marketplace": m.get("marketplace") or key,
            "avg_searches": _v(m.get("avg_searches")),
            "avg_clicks": _v(m.get("avg_clicks")),
            "avg_ctr": _v(m.get("ctr")),
            "search_trend": _trend(m.get("search_trend")),
        }
        for key, m in _as_map(payload.get("marketplace_stats")).items()
        if isinstance(m, dict)
    ]


def wrap_result(
    summary: Any,
    full: Any,
    *,
    include_full: bool = True,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"summary": summary}
    if include_full:
        out["_meta"] = {"full_response": compact(full), **(meta or {})}
    elif meta:
        out["_meta"] = meta
    return out
