# Security Policy

## Supported Versions

This repository is experimental local automation software. Security fixes are
handled on the main branch unless a release process is added later.

## Reporting a Vulnerability

If you find a vulnerability, please do not publish private chat logs, contacts,
database files, or access tokens in an issue.

For now, report issues through a private GitHub security advisory if the
repository is public and advisories are enabled. If advisories are not enabled,
open a minimal issue that describes the risk without including private data.

## Sensitive Data

Never commit:

- `.env` or `autoreply/config.env`
- SQLite databases under `data/` or `autoreply/`
- logs under `data/` or `autoreply/logs/`
- real WeChat contact names, message content, `wxid_*` values, media metadata,
  or generated replies
- machine-specific absolute paths such as `/Users/<name>/...`

## Local Automation Warning

The autoreply workflow can control WeChat through AppleScript and macOS
Accessibility permissions. Review and test changes carefully before enabling
automatic sending.
