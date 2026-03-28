---
description: Read, create, and search notes in an Obsidian vault.
---

# Notes

## When to use
Requests involving personal notes, journal entries, Obsidian vault operations,
"search my notes for", "read my note about", "create a note about", etc.
For general task capture ("add a todo", "remind me to…"), use the **tasks** skill instead —
it decides whether the task belongs on Trello or in Obsidian.

## Guidelines
- Default vault location: ~/Documents/Obsidian (override with OBSIDIAN_VAULT env var)
- Notes are Markdown files (.md)
- Prepend new notes with YAML frontmatter (date, tags) when creating
- Never overwrite an existing note without confirmation — append or create a new file instead
- When searching, return matching excerpts, not full file contents

## Output format
For note contents: render as plain text (strip Markdown only if asked).
For search results: show filename, relevant excerpt, and creation date.
