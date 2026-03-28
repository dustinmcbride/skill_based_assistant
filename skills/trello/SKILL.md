---
description: Manage Trello boards, lists, and cards.
---

# Trello

## When to use
Explicit Trello operations where the user names Trello directly, or structural board management:
"move this card to done", "what's on my Trello board", "archive that card", "show my boards".
For general task capture ("add a todo", "remind me to…"), use the **tasks** skill instead —
it decides whether the task belongs on Trello or in Obsidian.

## Guidelines
- Always call `trello_overview` first to get board/list/card IDs — never guess IDs
- After a write operation the cache is updated automatically; no need to refresh
- When the user refers to a board or list by partial name, match case-insensitively
- Prefer `trello_move_card` over archive+recreate when the user wants to change a card's status
- Call `trello_refresh_cache` only when the user explicitly asks for fresh data or suspects stale state

## Output format
Use the board and list names (not IDs) in responses. Keep confirmations concise:
"Added 'Fix login bug' to In Progress on Web App."
