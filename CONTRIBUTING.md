# Contributing

Thanks for considering a contribution.

This project is designed for local-first WeChat private-message auto-reply
workflows. Please keep privacy, user consent, and accidental-send risk in mind
for every change.

## Development Setup

```bash
uv venv
uv sync --extra dev
cp autoreply/config.env.example autoreply/config.env
```

Then edit `autoreply/config.env` with local paths. Do not commit
`autoreply/config.env`.

Run tests:

```bash
uv run pytest
./.venv/bin/python -m unittest discover -s autoreply -p 'test_*.py'
```

## Pull Request Checklist

- Do not include real WeChat messages, contact names, `wxid_*` values, logs, or
  SQLite databases.
- Do not include machine-specific paths such as `/Users/<name>/...`.
- Update `autoreply/config.env.example` when adding config.
- Keep generated runtime files out of commits.
- Add or update tests for behavior changes.
- Document macOS permissions and any safety implications.

## Coding Notes

- Prefer configuration through environment variables over hardcoded local paths.
- Treat all chat data as private by default.
- Keep automation opt-in and clearly documented.
