# Privacy Notes

This project processes local WeChat data. Assume all runtime data is private.

## Data That Must Stay Local

- WeChat messages and generated replies
- contact names, group names, and `wxid_*` identifiers
- SQLite databases
- logs
- local model paths
- macOS permission/debug output
- `.env` and `autoreply/config.env`

## Public Repository Rules

Before pushing to GitHub:

1. Use example config files instead of real config files.
2. Keep databases and logs ignored by Git.
3. Replace personal paths with placeholders.
4. Replace real contact names with examples.
5. Run a text scan for private values before committing.

Example scan:

```bash
rg -n "(/Users/|wxid_|Qwen|真实联系人名)" .
```

Adjust the search terms to include your real contact names before upload.
