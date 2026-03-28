# Personal Assistant

A modular personal assistant built on the Anthropic SDK. Supports voice/API commands, interactive chat, and webhook-driven automation. Routes requests to skill domains automatically and dispatches tools to local Python functions or remote MCP servers.

## Features

- **Three interaction modes** — chat (interactive CLI), command (API, no follow-up questions), and capture (async note intake)
- **Multi-user** — isolated history, config, and personas per user
- **Just-in-time skill routing** — a fast cheap model picks the right skill before the main agent runs; skill instructions are injected into the system prompt only when needed
- **Telegram bot** — bidirectional messaging via webhook; agent responses sent back to user
- **Email automation** — AgentMail webhook automatically detects and files travel info from incoming emails
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
# edit .env and fill in ANTHROPIC_API_KEY and any integrations you want
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

### Capture mode (API)

Append a quick note to the inbox and let the agent file it. Runs in the background; sends a Telegram confirmation when done.

```bash
uv run python server.py
```

```bash
curl -X POST http://localhost:5055/capture/tim \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: your-secret-key-here' \
  -d '{"message": "buy oat milk on the way home"}'
```

Response (immediate):

```json
{"status": "received"}
```

Or use the included script:

```bash
python scripts/send_capture.py -u tim -m "buy oat milk on the way home"

# Random shorthand lists (for testing)
python scripts/send_capture.py --chore
python scripts/send_capture.py --grocery
python scripts/send_capture.py --admin
python scripts/send_capture.py --thought
```

Health check: `GET /health`

## Webhooks

### Telegram

The server registers a Telegram webhook on startup. Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_URL` — the bot will receive messages, run them through the agent, and reply.

### Email (AgentMail)

Point your AgentMail webhook at `POST /webhook/email`. Incoming emails are automatically scanned for travel information and filed to `Trips/` in the Obsidian vault.

## Configuration

### Environment variables (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Anthropic API key |
| `CAPTURE_API_KEY` | Yes | API key for the `/capture` endpoint |
| `CONFIG_FILE_URL` | No | URL to load user config JSON (supports `file://` and GitHub raw paths) |
| `GITHUB_PAT` | No | GitHub PAT for authenticated access to `CONFIG_FILE_URL` |
| `OBSIDIAN_VAULT` | No | Path to Obsidian vault (default: `obsidian_vault`) |
| `ALLOWED_PATHS` | No | Comma-separated paths the filesystem skill can access (default: `OBSIDIAN_VAULT`) |
| `TELEGRAM_BOT_TOKEN` | No | Telegram bot token from BotFather |
| `TELEGRAM_WEBHOOK_URL` | No | Public URL where Telegram sends updates |
| `TELEGRAM_WEBHOOK_SECRET` | No | Optional secret token for webhook auth |
| `AGENTMAIL_API_KEY` | No | AgentMail API key |
| `AGENTMAIL_INBOX_ID` | No | AgentMail inbox to monitor |
| `AGENTMAIL_WEBHOOK_SECRET` | No | Svix webhook secret for signature verification |
| `TRELLO_API_KEY` | No | Trello API key |
| `TRELLO_TOKEN` | No | Trello OAuth token |
| `HOST` | No | Server bind host (default: `0.0.0.0`) |
| `PORT` | No | Server bind port (default: `5055`) |
| `ASSISTANT_DIR` | No | Base directory for assistant data (default: `~/.assistant`) |

### Remote config

Set `CONFIG_FILE_URL` to a JSON file defining users and persona URLs:

```json
{
  "soul_base_url": "file:///path/to/soul.md",
  "users": [
    {
      "id": "tim",
      "name": "Tim Fish",
      "persona_url": "file:///path/to/personas/tim.md",
      "telegram_chat_id": "123456789"
    }
  ]
}
```

GitHub raw paths are supported (no `https://` prefix needed):

```
CONFIG_FILE_URL=owner/repo/refs/heads/main/path/to/config.json
```

## Skills

| Domain | Description |
|--------|-------------|
| `calendar` | Manage calendar events, reminders, and scheduling |
| `email` | Check and read emails via AgentMail |
| `filesystem` | Read, write, list, and search files on the local filesystem |
| `notes` | Read, create, and search notes in an Obsidian vault |
| `tasks` | Route todos to Trello (actionable) or Obsidian (notes/ideas) |
| `telegram` | Send messages via Telegram |
| `trello` | Manage Trello boards, lists, and cards |
| `trips` | Extract and file travel information to the Obsidian vault |

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
├── config.py           # Constants, model names, mode prompts, remote config loading
├── user.py             # User loading and persona management
├── memory.py           # Per-user conversation history with smart trimming
├── skill_loader.py     # Skill discovery and just-in-time routing
├── agent.py            # Agentic tool-use loop
├── mcp_servers.py      # Remote MCP server list
├── server.py           # FastAPI server (capture, Telegram, email webhooks)
├── run.py              # CLI chat mode entrypoint
├── .env.sample         # Environment variable template
├── scripts/
│   └── send_capture.py # CLI helper to send capture requests
├── skills/
│   ├── calendar/
│   ├── email/
│   ├── filesystem/
│   ├── notes/
│   ├── tasks/
│   ├── telegram/
│   ├── trello/
│   └── trips/
└── tests/
```

## Tests

```bash
python -m pytest tests/ -v
```
