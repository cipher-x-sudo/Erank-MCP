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


def keyword_table(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a compact keyword research table from orchestrated responses."""
    rows: dict[str, dict[str, Any]] = {}

    def upsert(kw: str, **fields: Any) -> None:
        row = rows.setdefault(kw, {"keyword": kw})
        row.update({k: v for k, v in fields.items() if v is not None})

    seed = payload.get("keyword")
    if seed:
        upsert(str(seed))

    stats = payload.get("stats")
    if isinstance(stats, dict):
        upsert(
            str(seed or stats.get("keyword") or "unknown"),
            searches=stats.get("searches") or stats.get("search_volume") or stats.get("avg_searches"),
            competition=stats.get("competition"),
            difficulty=stats.get("difficulty") or stats.get("keyword_difficulty"),
        )

    related = payload.get("related_searches")
    items = []
    if isinstance(related, dict):
        items = related.get("data") or related.get("keywords") or related.get("results") or []
        if isinstance(items, dict):
            items = items.get("data") or []
    if isinstance(items, list):
        for item in items[:50]:
            if isinstance(item, dict):
                kw = item.get("keyword") or item.get("term")
                if kw:
                    upsert(
                        str(kw),
                        searches=item.get("searches") or item.get("search_volume") or item.get("avg_searches"),
                        competition=item.get("competition"),
                    )

    competition = payload.get("competition")
    if isinstance(competition, dict):
        for item in _iter_named(competition):
            upsert(item["keyword"], competition=item.get("value") or item.get("competition"))

    difficulty = payload.get("keyword_difficulty")
    if isinstance(difficulty, dict):
        for item in _iter_named(difficulty):
            upsert(item["keyword"], difficulty=item.get("value") or item.get("difficulty"))

    google = payload.get("google_data")
    if isinstance(google, dict):
        for item in _iter_named(google):
            upsert(
                item["keyword"],
                google_searches=item.get("searches") or item.get("value") or item.get("google_searches"),
            )

    return list(rows.values())[:80]


def _iter_named(blob: dict[str, Any]) -> list[dict[str, Any]]:
    data = blob.get("data") or blob.get("results") or blob.get("keywords") or blob
    if isinstance(data, dict) and all(isinstance(v, (int, float, str, dict)) for v in data.values()):
        # map of keyword -> metric
        out = []
        for k, v in data.items():
            if k in {"status", "success", "message", "meta"}:
                continue
            if isinstance(v, dict):
                out.append({"keyword": k, **v})
            else:
                out.append({"keyword": k, "value": v})
        return out
    if isinstance(data, list):
        out = []
        for item in data:
            if isinstance(item, dict):
                kw = item.get("keyword") or item.get("term")
                if kw:
                    out.append({"keyword": str(kw), **item})
        return out
    return []


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
