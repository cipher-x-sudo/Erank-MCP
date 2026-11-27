# eRank MCP

HAR-driven [MCP](https://modelcontextprotocol.io) server for [members.erank.com](https://members.erank.com). Authenticates with **browser-exported cookies**, mirrors the Axios session headers from the SPA (`X-User-Agent: erank-app/3.0`, XSRF), and exposes **semantic tools** that replay the flows captured in your HAR.

> Personal / single-account automation. Respect eRank Terms of Service and your plan quotas. Do not commit cookies or HARs that contain PII.

## Setup

```bash
cd "E:\Codes\ERANK MCP"
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

### 1. Harmonize the HAR (offline)

```bash
python scripts/harmonize_har.py --har members.erank.com.har --out catalog/api-catalog.json
```

Regenerate whenever eRank’s UI/API changes and you capture a new HAR.

### 2. Export cookies

1. Log in at https://members.erank.com in Chrome.
2. Export cookies for `members.erank.com` / `.erank.com` with **Cookie-Editor** or **EditThisCookie** (JSON).
3. Save as **`cookies.json` in the project root** (`E:\Codes\ERANK MCP\cookies.json`).  
   See `cookies.example.json` for the shape. The file is gitignored.

Optional `.env` (defaults already use root `cookies.json`):

```env
ERANK_COOKIE_FILE=cookies.json
ERANK_ALLOW_WRITES=0
ERANK_ALLOW_TELEMETRY=0
```

### 3. Smoke-check session

```bash
python -c "from erank_mcp.server import erank_session_status; import json; print(json.dumps(erank_session_status(), indent=2)[:2000])"
```

Or call the MCP tool `erank_session_status` from Cursor after wiring (below).

## Cursor MCP config

Add to Cursor MCP settings (`mcp.json`):

```json
{
  "mcpServers": {
    "erank": {
      "command": "E:\\Codes\\ERANK MCP\\.venv\\Scripts\\python.exe",
      "args": ["-m", "erank_mcp"],
      "env": {
        "ERANK_COOKIE_FILE": "E:\\Codes\\ERANK MCP\\cookies.json",
        "ERANK_DEFAULT_COUNTRY": "GLO",
        "ERANK_DEFAULT_MARKETPLACE": "etsy",
        "ERANK_ALLOW_WRITES": "0",
        "ERANK_ALLOW_TELEMETRY": "0"
      }
    }
  }
}
```

Use the absolute path to the venv interpreter so Cursor finds the installed package.

## Tools

| Tool | Purpose |
|------|---------|
| `erank_session_status` | Cookie/session health, shop profile, quota |
| `erank_dashboard_snapshot` | Dashboard bundle (configurable sections) |
| `erank_keyword_research` | Keyword tool orchestration (HAR flow) |
| `erank_keyword_list` | List names / terms / terms-kl / quotas |
| `erank_save_keyword` | Save keyword (writes gated) |
| `erank_rank_check` | Rank checker + optional SERP |
| `erank_competitor_intel` | Competitor sales; optional track |
| `erank_shop_analyze` | Shop info + listings-fresh |
| `erank_top_sellers` | Top sellers / yesterday / countries |
| `erank_trending` | Trending report / trend buzz |
| `erank_listing_health` | Listing health check |
| `erank_settings_read` | Account settings read |
| `erank_quota` | Daily / none-daily quota |
| `erank_raw_request` | Any `/api` path escape hatch |
| `erank_replay_flow` | Replay named HAR flows |
| `erank_catalog_info` | Inspect HAR catalog templates |

Mutating endpoints require `ERANK_ALLOW_WRITES=1`. `/api/logs` is blocked unless `ERANK_ALLOW_TELEMETRY=1`.

## Project layout

```
scripts/harmonize_har.py   # HAR → catalog
catalog/api-catalog.json   # generated endpoint templates
src/erank_mcp/
  client.py                # httpx + cookies + XSRF
  server.py                # MCP tools
  workflows.py             # multi-step HAR flows
```

## Security checklist

- Keep `.env`, cookie files, and `*.har` out of git (see `.gitignore`).
- Never paste full cookie values into chat logs.
- Rotate session if a HAR with Intercom/PII was shared.
- This is not an official eRank API; endpoints can change without notice — re-run the harmonizer.

## Tests

```bash
pytest -q
```
