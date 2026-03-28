# Personal Assistant

A modular personal assistant built on the Anthropic SDK. Supports voice/API commands and interactive chat, routes requests to skill domains automatically, and dispatches tools to local Python functions or remote MCP servers.

## Features

- **Two interaction modes** — command (API, no follow-up questions) and chat (interactive CLI)
- **Multi-user** — isolated history, config, and skill overrides per user
- **Just-in-time skill routing** — a fast cheap model picks the right skill before the main agent runs; skill instructions are injected into the system prompt only when needed
- **Zero-friction extensibility** — drop a folder with a `SKILL.md` and a `.py` file, it works

## Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- An Anthropic API key

## Setup

```bash
cd assistant

# Create venv and install all dependencies
uv sync --extra dev

cp .env.sample .env
# edit .env and set ANTHROPIC_API_KEY (and any optional vars)
```

## Usage

### Chat mode (CLI)

```bash
uv run python run.py --user tim 
```

Start a fresh session (clears history):

```bash
uv run python run.py --user tim --fresh
```

### Command mode (API)

```bash
uv run python server.py
```

```bash
curl -X POST http://localhost:5055/command/tim \
  -H 'Content-Type: application/json' \
  -d '{"message": "remind me to call the dentist tomorrow morning"}'
```

Response:

```json
{
  "response": "Done — added a reminder for tomorrow at 9am.",
  "skill": "calendar",
  "actions_taken": ["create_event"]
}
```

Health check: `GET /health`

## Configuration

### Environment variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `HASS_URL` | No | Home Assistant base URL (e.g. `http://homeassistant.local:8123`) |
| `HASS_TOKEN` | No | Home Assistant long-lived access token |
| `OBSIDIAN_VAULT` | No | Path to Obsidian vault (default: `~/Documents/Obsidian`) |
| `HOST` | No | Server bind host (default: `0.0.0.0`) |
| `PORT` | No | Server bind port (default: `5055`) |


The `context` field is injected into the system prompt every session.

## Skills

| Domain | Description |
|--------|-------------|
| `filesystem` | Read, write, list, and search files on the local filesystem |
| `web` | Search the web and fetch content from URLs |
| `calendar` | Manage calendar events, reminders, and scheduling |
| `homelab` | Control smart home devices via Home Assistant |
| `notes` | Read, create, and search notes in an Obsidian vault |

### Adding a skill

1. Create a folder: `skills/<domain>/`
2. Add `skills/<domain>/SKILL.md` — the first descriptive line is used by the router
3. Add `skills/<domain>/<module>.py` with `@register`-decorated functions
4. Done — auto-discovered on next run, no other changes needed

```python
# skills/myskill/tools.py
from skills import register

@register
def do_something(input: str) -> str:
    "One-line description the model will see."
    return f"result: {input}"
```

Rules for skill functions:
- Must have a docstring (becomes the tool description)
- Must use type hints (used to build the JSON schema)
- Must return `str`
- Should handle exceptions internally and return an error string


## MCP Servers

Edit `mcp_servers.py` to add remote MCP servers (Google Calendar, Gmail, Home Assistant, etc.). Uncomment the entries and fill in the URLs — auth is handled externally by the MCP server.

```python
MCP_SERVERS = [
    {"type": "url", "url": "https://gcal.mcp.claude.com/mcp", "name": "google-calendar"},
]
```

## Project Structure

```
assistant/
├── config.py           # Constants, model names, mode prompts
├── user.py             # User loading and auto-provisioning
├── memory.py           # Per-user conversation history
├── skill_loader.py     # Skill discovery and routing
├── agent.py            # Agentic tool-use loop
├── mcp_servers.py      # Remote MCP server list
├── server.py           # FastAPI command mode endpoint
├── run.py              # CLI chat mode entrypoint
├── .env.sample         # Environment variable template
├── skills/
│   ├── filesystem/
│   ├── web/
│   ├── calendar/
│   ├── homelab/
│   └── notes/
└── tests/
```

## Tests

```bash
python -m pytest tests/ -v
```
