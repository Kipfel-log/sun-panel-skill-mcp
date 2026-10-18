# Sun-Panel Skill + MCP

[简体中文](README.zh-CN.md)

Manage [Sun-Panel](https://doc.sun-panel.top/) navigation entries from an AI assistant, a command line, or a local stdio MCP server. The skill and MCP server share one API client.

## Features

- Read the version, list groups, and look up groups and entries.
- Preview, create, and update entries: title, URL, LAN URL, icon, description, and group.
- Read-only MCP tools by default; enable create/update with `--allow-write`.
- Check HTTP and Sun-Panel business errors, refuse redirects, and verify writes.
- No default server, bundled credentials, network listener, or raw endpoint passthrough.

This manages navigation entries. It does not install or control the applications behind them.

## Requirements

- Python 3.11+.
- CLI: Python standard library only.
- MCP: `python -m pip install -r requirements.txt` (official MCP Python SDK 2.3.0).
- Updates require stable Sun-Panel 1.8.1+ because earlier releases had an omitted-field/icon preservation bug.

## Configure

Set these environment variables in the process that runs the CLI or MCP server:

| Variable | Purpose |
|---|---|
| `SUN_PANEL_BASE_URL` | Your panel origin or full `/openapi/v1` base URL |
| `SUN_PANEL_TOKEN` | OpenAPI token, sent only in the `token` request header |
| `SUN_PANEL_ALLOW_HTTP` | Set to `1` only for an explicitly approved HTTP deployment |

The client connects directly and does not use system proxies. Keep TLS verification enabled. If a reverse proxy returns an HTML login page, configure an authenticated API route; do not treat that as an expired Sun-Panel token.

Example for Bash (the token is entered interactively and is not embedded in command history):

```bash
export SUN_PANEL_BASE_URL='https://panel.example.com/openapi/v1'
read -r -s -p 'Sun-Panel token: ' SUN_PANEL_TOKEN; printf '\n'
export SUN_PANEL_TOKEN
python sun-panel/scripts/sun_panel.py version
python sun-panel/scripts/sun_panel.py groups
# Clear the token after use:
unset SUN_PANEL_TOKEN
```

All example addresses are placeholders. Use your own server and do not commit real tokens or local configuration.

## CLI

After setting the environment:

```bash
python sun-panel/scripts/sun_panel.py group --id 1
python sun-panel/scripts/sun_panel.py item --only-name nav-example

# Edit examples/entry.json to select a real group and application URL.
# Preview only:
python sun-panel/scripts/sun_panel.py create --file examples/entry.json
# Execute an authorized change and read it back:
python sun-panel/scripts/sun_panel.py create --file examples/entry.json --yes

python sun-panel/scripts/sun_panel.py update --file examples/changes.json
python sun-panel/scripts/sun_panel.py update --file examples/changes.json --yes
```

Every new entry needs a stable `onlyName`. Display titles are not identifiers. There is no documented API for listing every entry in the supported v1 API, so existing entries need their known `onlyName`.

Updates send only explicitly supplied fields; omitted fields remain unchanged. Empty strings explicitly clear optional text. Use either `itemGroupID` or `itemGroupOnlyName`, not both.

## Install the skill

Copy the `sun-panel/` directory into your skill directory, for example `~/.codex/skills/sun-panel/` (or `$CODEX_HOME/skills/sun-panel/` when configured). Reload skills as required by your client. Configure the environment for the process that executes the scripts.

The skill can use an already connected `sun_panel_*` MCP server or the included CLI. Example request: “Use $sun-panel to add this application to my navigation page.”

## MCP

Install dependencies into a virtual environment, then configure your MCP client using [mcp.example.json](mcp.example.json). Replace the Python and script paths with absolute paths. Supply `SUN_PANEL_TOKEN` through your client's secret/environment configuration or the environment inherited when the client starts; the example deliberately contains no token.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python sun-panel/scripts/sun_panel_mcp.py
```

On Windows, the interpreter is `.venv\Scripts\python.exe`. To expose write tools, append `--allow-write` to the script arguments.

| Tools | Default |
|---|---|
| `sun_panel_version`, `sun_panel_list_groups`, `sun_panel_get_group`, `sun_panel_get_item` | Read-only |
| `sun_panel_preview_create`, `sun_panel_preview_update` | Read-only previews |
| `sun_panel_create_item`, `sun_panel_update_item` | Only with `--allow-write` |

This server runs locally over stdio. The computer running it must be able to reach the configured panel. No HTTP MCP server is deployed.

## Verification and known limits

`executed: true` means the API accepted the write. `verified: true` means the requested fields were confirmed by read-back. CLI exit codes:

| Code | Meaning |
|---|---|
| `0` | Read/preview completed, or write verified |
| `1` | Request, validation, authentication, or network error |
| `3` | Write accepted, but verification needs attention; inspect before retrying |

Some Sun-Panel 1.8.1 deployments return an empty `iconUrl` even when the browser displays the saved icon. The result then reports `verification_status: needs_visual_check` and `unverified_fields: ["iconUrl"]`. Inspect the rendered card and image load; do not repeat an accepted write just because the icon read-back is empty. Local icon downloads also need a visual check because the returned URL can differ from the original.

Network failures are not automatically retried. After an interrupted write, read the target before retrying. This API has no conditional updates, so coordinate concurrent edits to the same entry.

Only documented operations are exposed. There is no entry deletion, global entry listing, group creation, ordering, layout, wallpaper, Docker control, or application installation tool here. Batch updates require a v2 development release and are not exposed.

## Tests

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Tests use a local mock panel and the official SDK. They do not access a real NAS. Development was also checked against Sun-Panel 1.8.1, including entry creation, icon changes, and rendered image verification. This is an independent integration, not an official Sun-Panel project.

API references are summarized in [sun-panel/references/api.md](sun-panel/references/api.md). Dependencies and upstream projects retain their own licenses.
