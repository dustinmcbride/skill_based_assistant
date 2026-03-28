---
description: Read, write, list, and search files on the local filesystem.
---

# Filesystem

## When to use
Requests involving reading files, writing or appending content, listing directories,
or searching for files by name or content.

## Guidelines
- Expand `~` in paths before operations
- Never delete files without explicit user confirmation
- When listing, show file sizes and modification times where helpful
- Prefer reading over guessing file content
- Limit read output to a reasonable size (first 200 lines for large files)

## Output format
Return plain text. For listings, use a simple indented tree or line-per-entry format.
