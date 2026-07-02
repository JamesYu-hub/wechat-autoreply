#!/usr/bin/env python3
"""Send generated reply drafts through WeChat AppleScript."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autoreply.poll_unread import BASE_DIR, DB_PATH, init_database, run_wechat_cli


SCRIPT_PATH = BASE_DIR.parent / "sendwechat.scpt"
UI_SEARCH_NAMES = {
    "filehelper": "File",
}


def generated_drafts(db_path: Path = DB_PATH, contact: str | None = None) -> list[dict[str, Any]]:
    query = """
        SELECT id, contact_name, contact_username, reply_messages_json, reply_text
        FROM reply_drafts
        WHERE status = 'generated'
          AND NOT EXISTS (
              SELECT 1 FROM reply_drafts newer
              WHERE newer.contact_username = reply_drafts.contact_username
                AND newer.status = 'generated'
                AND newer.id > reply_drafts.id
          )
    """
    params: list[Any] = []
    if contact:
        query += " AND (contact_name = ? OR contact_username = ?)"
        params.extend([contact, contact])
    query += " ORDER BY id"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
    drafts = []
    for row in rows:
        messages = json.loads(row["reply_messages_json"]) if row["reply_messages_json"] else [row["reply_text"]]
        drafts.append({**dict(row), "reply_messages": messages})
    return drafts


def send_message(contact_name: str, message: str) -> None:
    command = ["/usr/bin/osascript", str(SCRIPT_PATH), contact_name, message]
    result = subprocess.run(
        command,
        capture_output=True, check=False, text=True, timeout=30,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"sender exit {result.returncode}"
        if "not allowed to send keystrokes" in detail:
            detail += (
                "\nGrant Accessibility permission to the project Python executable or the parent terminal/background "
                "process in System Settings > Privacy & Security > Accessibility."
            )
        raise RuntimeError(detail)


def verify_message(contact_username: str, message: str) -> bool:
    for _ in range(5):
        time.sleep(1)
        payload = run_wechat_cli("history", contact_username, "--limit", "30")
        if isinstance(payload, dict) and any(
            str(line).strip().endswith(message) for line in payload.get("messages", [])
        ):
            return True
    return False


def mark_sent(draft_id: int, messages: list[str], db_path: Path = DB_PATH) -> None:
    sent_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        draft = conn.execute(
            "SELECT contact_username, user_prompt FROM reply_drafts WHERE id = ?",
            (draft_id,),
        ).fetchone()
        conn.execute("UPDATE reply_drafts SET status = 'sent', sent_at = ?, error = NULL WHERE id = ?", (sent_at, draft_id))
        conn.execute(
            """
            UPDATE unread_messages
            SET status = 'replied', replied_at = ?, reply_text = ?
            WHERE id IN (SELECT message_id FROM reply_draft_messages WHERE draft_id = ?)
            """,
            (sent_at, "\n".join(messages), draft_id),
        )
        if draft:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_turns (
                    contact_username, role, content, source_key, created_at
                ) VALUES (?, 'user', ?, ?, ?)
                """,
                (draft[0], draft[1], f"draft:{draft_id}:user", sent_at),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_turns (
                    contact_username, role, content, source_key, created_at
                ) VALUES (?, 'assistant', ?, ?, ?)
                """,
                (
                    draft[0],
                    json.dumps({"messages": messages}, ensure_ascii=False),
                    f"draft:{draft_id}:assistant",
                    sent_at,
                ),
            )


def send_generated(contact: str, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    drafts = generated_drafts(db_path=db_path, contact=contact)
    for draft in drafts:
        try:
            for message in draft["reply_messages"]:
                search_name = UI_SEARCH_NAMES.get(draft["contact_username"], draft["contact_name"])
                send_message(search_name, message)
                if not verify_message(draft["contact_username"], message):
                    raise RuntimeError("WeChat history verification failed after AppleScript send")
            mark_sent(draft["id"], draft["reply_messages"], db_path)
        except Exception as exc:
            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE reply_drafts SET error = ? WHERE id = ?", (str(exc), draft["id"]))
            raise
    return drafts


def send_contacts(contact_usernames: set[str], db_path: Path = DB_PATH) -> dict[str, list[dict[str, Any]]]:
    sent: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for contact_username in sorted(contact_usernames):
        try:
            sent.extend(send_generated(contact_username, db_path))
        except Exception as exc:
            errors.append({"contact_username": contact_username, "error": str(exc)})
    return {"sent": sent, "errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Actually send; default is dry-run.")
    parser.add_argument("--contact", help="Only send drafts for this exact display name or username.")
    args = parser.parse_args()
    init_database()
    drafts = generated_drafts(contact=args.contact)
    if not args.send:
        print(json.dumps({"dry_run": True, "drafts": drafts}, ensure_ascii=False))
        return 0
    if not args.contact:
        print("[autoreply] --send requires --contact to prevent accidental bulk sending", file=sys.stderr)
        return 2
    try:
        drafts = send_generated(args.contact)
    except Exception as exc:
        print(f"[autoreply] send failed for {args.contact}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"sent_drafts": len(drafts), "contact": args.contact}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
