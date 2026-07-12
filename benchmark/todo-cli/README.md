# todo-cli

A deliberately minimal personal todo CLI. Three commands, one JSON file, nothing else.

```bash
todo add "장보기"   # register a task
todo list           # show open tasks (oldest first, with ids)
todo done 1         # complete a task by id
```

- Store: `~/.todo.json` — human-readable, hand-editable JSON. Done items are hidden from `list` but kept in the file forever.
- No priorities, due dates, tags, search, edit, or delete — by design. Fix mistakes by re-adding or hand-editing the JSON.
- A corrupt store file (bad JSON or wrong shape) makes every command abort without touching the file.

## Development

```bash
uv sync
uv run pytest
uv run todo list
```

Spec: see `.ultimateinterview/todo-cli-app/handoff.md` (interview working state).
