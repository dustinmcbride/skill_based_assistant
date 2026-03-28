# MCP server list passed directly to the Anthropic API.
# To add a server: append a dict. No other changes needed.
#
# Auth is handled externally (OAuth tokens managed by the MCP server).
# Do not store credentials here.

MCP_SERVERS: list[dict] = [
    # {"type": "url", "url": "https://<hass-instance>/api/mcp", "name": "home-assistant"},
    # {"type": "url", "url": "https://gcal.mcp.claude.com/mcp", "name": "google-calendar"},
    # {"type": "url", "url": "https://gmail.mcp.claude.com/mcp", "name": "gmail"},
]
