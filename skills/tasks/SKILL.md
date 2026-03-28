---
description: Capture todos, tasks, and action items — routing each to Trello or the Obsidian vault.
---

# Tasks

## When to use
Any request to add, capture, or log a task, todo, action item, or reminder:
"add a todo", "remind me to", "make a note to", "I need to", "don't let me forget".

## Decision logic

When capturing a task, follow these steps in order:

1. **Call `trello_overview`** to see the current boards and lists.
2. **Does the task fit an existing Trello board?**
   - Yes → add it as a card with `trello_create_card`. Use the most specific matching list
     (e.g. "To Do", "Backlog", or "Inbox" if present).
   - No → proceed to step 3.
3. **Does the task belong in the Obsidian vault?**
   - Look for a note that acts as a general task list (e.g. "Tasks.md", "Inbox.md", "TODO.md").
     Use `search_notes` with the query "todo" or "tasks" to find it.
   - If found → append the task with `append_to_note`.
   - If not found → create a new note called "Tasks" with `create_note`.

## Matching rules for Trello

A task fits a Trello board when the subject matter clearly maps to an existing board's theme.
Examples:
- "fix the login bug" → fits a board named "Web App", "Engineering", "Bugs", etc.
- "buy groceries" → does NOT fit "Web App" — goes to Obsidian instead.
- "write blog post about the release" → fits a board named "Marketing", "Content", or "Writing".

When in doubt, prefer Obsidian over creating noise on a Trello board.

## Output format
Always confirm where the task landed:
- "Added 'Fix login bug' to the To Do list on your Web App board."
- "Added 'Buy groceries' to your Tasks note in Obsidian."
