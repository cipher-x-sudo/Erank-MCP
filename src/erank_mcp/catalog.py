"""Load and query the HAR-derived API catalog."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from erank_mcp.config import get_settings


class Catalog:
    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.endpoints: list[dict[str, Any]] = data.get("endpoints", [])
        self._by_key = {(e["method"].upper(), e["path_template"]): e for e in self.endpoints}

    @property
    def endpoint_count(self) -> int:
        return len(self.endpoints)

    def find(self, method: str, path_template: str) -> Optional[dict[str, Any]]:
        return self._by_key.get((method.upper(), path_template))

    def by_group(self, group: str) -> list[dict[str, Any]]:
        return [e for e in self.endpoints if e.get("feature_group") == group]

    def groups(self) -> list[str]:
        return sorted({e.get("feature_group", "other") for e in self.endpoints})

    def marketplaces_seen(self) -> list[str]:
        return list(self.data.get("marketplaces_seen") or [])


@lru_cache(maxsize=1)
def load_catalog(path: str | None = None) -> Catalog:
    settings = get_settings()
    catalog_path = Path(path) if path else settings.catalog_path
    if not catalog_path.exists():
        return Catalog({"endpoints": [], "endpoint_count": 0, "marketplaces_seen": []})
    with catalog_path.open("r", encoding="utf-8") as f:
        return Catalog(json.load(f))
