# eRank MCP

MCP server for [members.erank.com](https://members.erank.com). Use your logged-in browser session (exported cookies) so Cursor or any MCP client can run keyword research, rank checks, competitor intel, shop analysis, and related eRank workflows.

Not an official eRank product. Use only with accounts you own, respect eRank’s Terms of Service, and watch your plan quotas.

## Requirements

- Python 3.11+
- Active eRank membership
- Cookies exported from a logged-in browser session

## Install

```bash
git clone https://github.com/cipher-x-sudo/Erank-MCP.git
cd Erank-MCP
python -m venv .venv

# Windows
.\.venv\Scripts\activate

# macOS / Linux
# source .venv/bin/activate

pip install -e .
```

For development extras:

```bash
pip install -e ".[dev]"
```

## Authentication

1. Sign in at https://members.erank.com
2. Export cookies for `members.erank.com` / `.erank.com` (Cookie-Editor, EditThisCookie, or equivalent) as JSON
3. Save as `cookies.json` in the project root (see `cookies.example.json`)

`cookies.json` is gitignored. Do not commit it.

Optional `.env` (copy from `.env.example`):

```env
ERANK_COOKIE_FILE=cookies.json
ERANK_DEFAULT_COUNTRY=GLO
ERANK_DEFAULT_MARKETPLACE=etsy
ERANK_ALLOW_WRITES=0
ERANK_ALLOW_TELEMETRY=0
ERANK_WARM_SESSION=1
```

Shop, member, and keyword-list IDs are discovered from the session when unset. You can override them with `ERANK_DEFAULT_SHOP`, `ERANK_DEFAULT_SHOP_ID`, `ERANK_DEFAULT_MEMBER_ID`, or `ERANK_KEYWORD_LIST_ID`.

## Verify session

```bash
python scripts/smoke_session.py
```

Or from Python:

```bash
python -c "from erank_mcp.server import erank_session_status; import json; print(json.dumps(erank_session_status(), indent=2)[:2000])"
```

A healthy response includes cookie status, shop profile, and quota.

## Cursor MCP

Add to your Cursor `mcp.json` (use absolute paths for your machine):

```json
{
  "mcpServers": {
    "erank": {
      "command": "/absolute/path/to/Erank-MCP/.venv/bin/python",
      "args": ["-m", "erank_mcp"],
      "cwd": "/absolute/path/to/Erank-MCP",
      "env": {
        "ERANK_COOKIE_FILE": "/absolute/path/to/Erank-MCP/cookies.json",
        "ERANK_DEFAULT_COUNTRY": "GLO",
        "ERANK_DEFAULT_MARKETPLACE": "etsy",
        "ERANK_ALLOW_WRITES": "0",
        "ERANK_ALLOW_TELEMETRY": "0",
        "ERANK_WARM_SESSION": "1"
      }
    }
  }
}
```

Windows example for `command`:

`E:\\path\\to\\Erank-MCP\\.venv\\Scripts\\python.exe`

A sample config lives in `examples/cursor-mcp.json`.

## CLI

```bash
erank-mcp
# or
python -m erank_mcp
```

## Tools

| Tool | Purpose |
|------|---------|
| `erank_session_status` | Session health, shop profile, quota |
| `erank_dashboard_snapshot` | Dashboard bundle (selectable sections) |
| `erank_keyword_research` | Keyword research orchestration |
| `erank_keyword_list` | Keyword lists, terms, and list quotas |
| `erank_save_keyword` | Save a keyword (writes gated) |
| `erank_rank_check` | Rank checker (+ optional SERP) |
| `erank_competitor_intel` | Competitor sales (+ optional track) |
| `erank_shop_analyze` | Shop info and listings |
| `erank_top_sellers` | Top sellers / yesterday / countries |
| `erank_trending` | Trending report / buzz |
| `erank_listing_health` | Listing health check |
| `erank_settings_read` | Account settings (read) |
| `erank_quota` | Daily / non-daily quota |
| `erank_raw_request` | Escape hatch for any `/api` path |
| `erank_replay_flow` | Replay a named multi-step flow |
| `erank_catalog_info` | Inspect endpoint templates |

Mutating calls need `ERANK_ALLOW_WRITES=1`. Telemetry (`/api/logs`) stays blocked unless `ERANK_ALLOW_TELEMETRY=1`.

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `ERANK_COOKIE_FILE` | `cookies.json` | Path to cookie export |
| `ERANK_COOKIE_HEADER` | — | Optional raw `Cookie` header (overrides file) |
| `ERANK_BASE_URL` | `https://members.erank.com` | API base |
| `ERANK_DEFAULT_COUNTRY` | `GLO` | Default country code |
| `ERANK_DEFAULT_MARKETPLACE` | `etsy` | Default marketplace |
| `ERANK_DEFAULT_SHOP` | auto | Shop name override |
| `ERANK_DEFAULT_SHOP_ID` | auto | Shop id override |
| `ERANK_DEFAULT_MEMBER_ID` | auto | Member id override |
| `ERANK_KEYWORD_LIST_ID` | auto | Keyword list id override |
| `ERANK_ALLOW_WRITES` | `0` | Allow write / mutate tools |
| `ERANK_ALLOW_TELEMETRY` | `0` | Allow `/api/logs` |
| `ERANK_WARM_SESSION` | `1` | Warm session on startup |

## Security

- Never commit `cookies.json`, `.env`, or session dumps
- Prefer file-based cookies over pasting values into chat or configs
- Keep `ERANK_ALLOW_WRITES=0` unless you intentionally need mutations
- Rotate the browser session if cookies may have been exposed
- Endpoints can change without notice; re-export cookies after login/logout

## License

MIT — see [LICENSE](LICENSE).
