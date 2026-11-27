#!/usr/bin/env python3
"""Offline HAR → catalog/api-catalog.json harmonizer for members.erank.com."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

KNOWN_SHOP_IDS = {"68807058", "62446517"}
KNOWN_LIST_IDS = {"1968657"}
KNOWN_MEMBER_IDS = {"2743076"}
KNOWN_SHOPS = {
    "lunavellebyjabeen",
    "pearpebbears",
}

FEATURE_RULES: list[tuple[str, str]] = [
    (r"^/api/keyword-tool/", "keyword_tool"),
    (r"^/api/keywordlist/", "keyword_list"),
    (r"^/api/rank-checker/", "rank_checker"),
    (r"^/api/competitor/", "competitor"),
    (r"^/api/dashboard/", "dashboard"),
    (r"^/api/shop-info/", "shop_info"),
    (r"^/api/top-sellers", "top_sellers"),
    (r"^/api/trend-buzz", "trending"),
    (r"^/api/trending-report", "trending"),
    (r"^/api/shop-trends", "trending"),
    (r"^/api/quota/", "quota"),
    (r"^/api/settings/", "settings"),
    (r"^/api/account/", "account"),
    (r"^/api/listings/", "listings"),
    (r"^/api/health-check/", "health"),
    (r"^/api/oauth/", "oauth"),
    (r"^/api/ga4/", "ga4"),
    (r"^/api/motd", "motd"),
    (r"^/api/cms/", "cms"),
    (r"^/api/presets", "presets"),
    (r"^/api/logs", "telemetry"),
    (r"^/api/intercom", "telemetry"),
    (r"^/api/search-history", "dashboard"),
    (r"^/api/etsy-popularity", "dashboard"),
    (r"^/api/member-shops", "account"),
    (r"^/api/refresh-data/", "dashboard"),
    (r"^/api/shop/analyze-history", "dashboard"),
    (r"^/api/demographics/", "trending"),
    (r"^/api/taxonomies/", "trending"),
    (r"^/api/check-paddle", "account"),
]


def feature_group(path: str) -> str:
    for pattern, group in FEATURE_RULES:
        if re.search(pattern, path):
            return group
    return "other"


def templatize_segment(seg: str, prev: str | None) -> str:
    lower = seg.lower()
    if seg in KNOWN_SHOP_IDS:
        return "{shop_id}"
    if seg in KNOWN_LIST_IDS:
        return "{list_id}"
    if seg in KNOWN_MEMBER_IDS:
        return "{member_id}"
    if lower in KNOWN_SHOPS:
        return "{shop}"
    if re.fullmatch(r"\d{6,}", seg):
        if prev in {"shop-sales", "inventory-value", "terms-kl", "quota", "terms"}:
            return "{id}"
        if prev in {"shop-list", "member", "invoices"}:
            return "{member_id}"
        return "{numeric_id}"
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{2,}", seg) and prev in {
        "shop-info",
        "total-active-listings",
        "inventory-value",
        "sales-history",
    }:
        # shop slug after known prefixes; inventory-value is /{shop_id}/{shop}
        if prev == "inventory-value":
            return "{shop}"
        return "{shop}"
    return seg


def templatize_path(path: str) -> str:
    parts = path.strip("/").split("/")
    out: list[str] = []
    for i, seg in enumerate(parts):
        prev = parts[i - 1] if i > 0 else None
        # Special-case keywordlist terms-kl: /terms-kl/{list_id}/{marketplace}/{country}/{flag}
        if i >= 1 and parts[i - 1] == "terms-kl" and re.fullmatch(r"\d+", seg):
            out.append("{list_id}")
            continue
        if i >= 2 and parts[i - 2] == "terms-kl" and re.fullmatch(r"[A-Za-z]+", seg):
            out.append("{marketplace}")
            continue
        if i >= 3 and parts[i - 3] == "terms-kl" and re.fullmatch(r"[A-Za-z]+", seg):
            out.append("{country}")
            continue
        if i >= 4 and parts[i - 4] == "terms-kl" and re.fullmatch(r"\d+", seg):
            out.append("{flag}")
            continue
        out.append(templatize_segment(seg, prev))
    return "/" + "/".join(out)


def referer_path(headers: list[dict[str, str]]) -> str | None:
    for h in headers:
        if h.get("name", "").lower() == "referer":
            try:
                return urlparse(h["value"]).path + (
                    ("?" + urlparse(h["value"]).query) if urlparse(h["value"]).query else ""
                )
            except Exception:
                return h.get("value")
    return None


def summarize_body(text: str | None) -> Any:
    if not text:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"_raw_preview": text[:200]}
    if isinstance(data, dict):
        # Keep structure; truncate long keyword arrays
        out: dict[str, Any] = {}
        for k, v in data.items():
            if isinstance(v, list) and len(v) > 5:
                out[k] = v[:5] + [f"...(+{len(v) - 5} more)"]
            else:
                out[k] = v
        return out
    return data


def harmonize(har_path: Path) -> dict[str, Any]:
    with har_path.open("r", encoding="utf-8") as f:
        har = json.load(f)

    entries = har.get("log", {}).get("entries", [])
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    marketplace_values: set[str] = set()

    for entry in entries:
        req = entry.get("request", {})
        url = req.get("url", "")
        if "members.erank.com/api/" not in url:
            continue
        parsed = urlparse(url)
        path = parsed.path
        method = req.get("method", "GET").upper()
        template = templatize_path(path)
        key = (method, template)

        qs = parse_qs(parsed.query, keep_blank_values=True)
        query_keys = {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
        if "marketplace" in qs:
            for m in qs["marketplace"]:
                marketplace_values.add(m)

        body = None
        post = req.get("postData") or {}
        if post.get("text"):
            body = summarize_body(post["text"])

        ref = referer_path(req.get("headers") or [])
        group = feature_group(path)

        if key not in buckets:
            buckets[key] = {
                "method": method,
                "path_template": template,
                "example_path": path,
                "feature_group": group,
                "query_params": {},
                "body_sample": body,
                "referer_template": ref,
                "har_count": 0,
                "status_samples": [],
            }

        b = buckets[key]
        b["har_count"] += 1
        for qk, qv in query_keys.items():
            if qk not in b["query_params"]:
                b["query_params"][qk] = qv
        if body and not b["body_sample"]:
            b["body_sample"] = body
        if ref and not b["referer_template"]:
            b["referer_template"] = ref
        status = entry.get("response", {}).get("status")
        if status is not None and status not in b["status_samples"] and len(b["status_samples"]) < 5:
            b["status_samples"].append(status)

    endpoints = sorted(buckets.values(), key=lambda e: (e["feature_group"], e["path_template"], e["method"]))

    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ep in endpoints:
        by_group[ep["feature_group"]].append(ep)

    return {
        "source": str(har_path.name),
        "base_url": "https://members.erank.com",
        "endpoint_count": len(endpoints),
        "marketplaces_seen": sorted(marketplace_values),
        "endpoints": endpoints,
        "by_group": {k: v for k, v in sorted(by_group.items())},
    }


def write_group_files(catalog: dict[str, Any], out_dir: Path) -> None:
    group_dir = out_dir / "endpoints"
    group_dir.mkdir(parents=True, exist_ok=True)
    for group, eps in catalog.get("by_group", {}).items():
        path = group_dir / f"{group}.json"
        path.write_text(json.dumps(eps, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harmonize eRank HAR into API catalog")
    parser.add_argument(
        "--har",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "members.erank.com.har",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "catalog" / "api-catalog.json",
    )
    args = parser.parse_args()

    if not args.har.exists():
        raise SystemExit(f"HAR not found: {args.har}")

    catalog = harmonize(args.har)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    # Slim public catalog: drop by_group duplication in main file size control — keep both
    slim = {k: v for k, v in catalog.items() if k != "by_group"}
    args.out.write_text(json.dumps(slim, indent=2), encoding="utf-8")
    write_group_files(catalog, args.out.parent)
    print(f"Wrote {catalog['endpoint_count']} endpoints → {args.out}")
    print(f"Groups: {', '.join(catalog['by_group'].keys())}")


if __name__ == "__main__":
    main()
