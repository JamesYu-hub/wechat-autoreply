#!/usr/bin/env python3
"""Collect all new private text messages discovered by wechat-cli."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("AUTOREPLY_DB_PATH", BASE_DIR / "unread_messages.sqlite3"))
WECHAT_CLI = os.environ.get(
    "AUTOREPLY_WECHAT_CLI",
    str(BASE_DIR.parent / ".venv" / "bin" / "wechat-cli"),
)
HISTORY_LIMIT = int(os.environ.get("AUTOREPLY_HISTORY_LIMIT", "1000"))
INITIAL_LOOKBACK_SECONDS = int(os.environ.get("AUTOREPLY_INITIAL_LOOKBACK_SECONDS", "600"))
ALLOWED_SYSTEM_USERNAMES = {
    username.strip()
    for username in os.environ.get("AUTOREPLY_ALLOWED_SYSTEM_USERNAMES", "").split(",")
    if username.strip()
}
HISTORY_LINE_PATTERN = re.compile(
    r"^\[(?P<sent_at>\d{4}-\d{2}-\d{2} \d{2}:\d{2})\]\s+"
    r"(?P<sender>.*?):\s*(?P<text>.*)$",
    re.DOTALL,
)

BLOCKED_USERNAMES = {
    "blogapp", "brandservicesessionholder", "brandsessionholder", "cardpackage",
    "conversationboxservice", "feedsapp", "filehelper", "floatbottle", "fmessage",
    "helper_entry", "lbsapp", "masssendapp", "medianote", "newsapp",
    "notification_messages", "notifymessage", "officialaccounts", "opencustomerservicemsg", "qmessage",
    "qqmail", "readerapp", "shakeapp", "tmessage", "voiceinputapp", "weibo", "weixin",
}
TEXT_TYPES = {"1", "text", "文本"}

# The next stage can import this module and read messages inserted by one poll.
unread_text: list[dict[str, Any]] = []


def init_database(db_path: Path = DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS unread_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fingerprint TEXT NOT NULL UNIQUE,
                contact_name TEXT NOT NULL,
                contact_username TEXT NOT NULL,
                message_text TEXT NOT NULL,
                message_timestamp INTEGER NOT NULL,
                message_type TEXT NOT NULL,
                unread_count INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'processing', 'replied', 'failed', 'ignored')),
                raw_json TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                replied_at TEXT,
                reply_text TEXT,
                error TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS session_audit (
                username TEXT PRIMARY KEY,
                contact_name TEXT NOT NULL,
                category TEXT NOT NULL,
                eligible_for_autoreply INTEGER NOT NULL,
                exclusion_reason TEXT,
                unread_count INTEGER NOT NULL DEFAULT 0,
                last_message_type TEXT NOT NULL,
                last_session_timestamp INTEGER NOT NULL,
                audited_at TEXT NOT NULL,
                raw_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reply_drafts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_fingerprint TEXT NOT NULL UNIQUE,
                contact_name TEXT NOT NULL,
                contact_username TEXT NOT NULL,
                system_prompt TEXT NOT NULL,
                user_prompt TEXT NOT NULL,
                reply_text TEXT,
                status TEXT NOT NULL DEFAULT 'generating'
                    CHECK (status IN ('generating', 'generated', 'failed', 'sent')),
                model TEXT NOT NULL,
                created_at TEXT NOT NULL,
                generated_at TEXT,
                sent_at TEXT,
                error TEXT
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(reply_drafts)")}
        if "reply_messages_json" not in columns:
            conn.execute("ALTER TABLE reply_drafts ADD COLUMN reply_messages_json TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reply_draft_messages (
                draft_id INTEGER NOT NULL REFERENCES reply_drafts(id) ON DELETE CASCADE,
                message_id INTEGER NOT NULL REFERENCES unread_messages(id),
                PRIMARY KEY (draft_id, message_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_unread_messages_status "
            "ON unread_messages(status, message_timestamp)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_cursors (
                contact_username TEXT PRIMARY KEY,
                contact_name TEXT NOT NULL,
                last_session_timestamp INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conversation_turns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_username TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                source_key TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversation_turns_contact "
            "ON conversation_turns(contact_username, id)"
        )
        sent_drafts = conn.execute(
            """
            SELECT id, contact_username, user_prompt,
                   COALESCE(reply_messages_json, reply_text, ''), COALESCE(sent_at, created_at)
            FROM reply_drafts
            WHERE status = 'sent'
            ORDER BY id
            """
        ).fetchall()
        for draft_id, contact_username, user_prompt, reply_content, sent_at in sent_drafts:
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_turns (
                    contact_username, role, content, source_key, created_at
                ) VALUES (?, 'user', ?, ?, ?)
                """,
                (contact_username, user_prompt, f"draft:{draft_id}:user", sent_at),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO conversation_turns (
                    contact_username, role, content, source_key, created_at
                ) VALUES (?, 'assistant', ?, ?, ?)
                """,
                (contact_username, reply_content, f"draft:{draft_id}:assistant", sent_at),
            )


def run_wechat_cli(*args: str) -> Any:
    command = [*shlex.split(WECHAT_CLI), *args, "--format", "json"]
    for attempt in range(3):
        try:
            result = subprocess.run(
                command, capture_output=True, check=False, text=True, timeout=120,
            )
        except subprocess.TimeoutExpired as exc:
            if attempt == 2:
                raise RuntimeError(
                    f"wechat-cli timed out after 120 seconds: {' '.join(command)}"
                ) from exc
            time.sleep(1)
            continue
        if result.returncode == 0:
            return json.loads(result.stdout)
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        if "database disk image is malformed" not in detail or attempt == 2:
            raise RuntimeError(f"wechat-cli failed: {detail}")
        time.sleep(0.5)
    raise RuntimeError("wechat-cli failed after retries")


def classify_session(message: dict[str, Any]) -> tuple[str, str | None]:
    username = str(message.get("username") or "").strip()
    if not username:
        return "invalid", "missing_username"
    if bool(message.get("is_group")) or username.endswith("@chatroom"):
        return "group", "group_chat"
    if username.startswith("gh_"):
        return "official_account", "official_account"
    if username.endswith("@openim"):
        return "openim_service", "openim_service"
    if username.startswith("@placeholder_"):
        return "placeholder", "wechat_placeholder"
    if username in ALLOWED_SYSTEM_USERNAMES:
        return "private_contact", None
    if username.lower() in BLOCKED_USERNAMES or "sessionholder" in username.lower():
        return "system", "wechat_system_session"
    return "private_contact", None


def is_private_session(message: dict[str, Any]) -> bool:
    return classify_session(message)[0] == "private_contact"


def is_private_activity_summary(message: dict[str, Any]) -> bool:
    return (
        is_private_session(message)
        and (
            bool(str(message.get("last_message") or "").strip())
            or bool(str(message.get("msg_type") or "").strip())
        )
    )


def is_private_text_summary(message: dict[str, Any]) -> bool:
    return is_private_activity_summary(message) and str(message.get("msg_type") or "").strip().lower() in TEXT_TYPES


def infer_message_type(text: str) -> str:
    for label in ("图片", "文件", "链接", "链接/文件", "视频", "语音", "表情", "位置", "名片", "通话"):
        if text.startswith(f"[{label}]"):
            return label
    return "文本"


def sanitize_message_text(text: str, message_type: str) -> str:
    if message_type == "语音":
        return "[语音消息，当前无法读取语音内容]"
    if message_type == "图片" and "(local_id=" in text:
        return "[图片，当前无法识别图片内容]"
    return text


def parse_history_lines(
    lines: list[Any],
    *,
    contact_name: str,
    contact_username: str,
) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    occurrences: Counter[str] = Counter()
    for raw_line in lines:
        line = str(raw_line)
        match = HISTORY_LINE_PATTERN.match(line.strip())
        if not match or (
            match.group("sender").strip().lower() == "me"
            and contact_username not in ALLOWED_SYSTEM_USERNAMES
        ):
            continue
        text = match.group("text").strip()
        if not text:
            continue
        message_type = infer_message_type(text)
        text = sanitize_message_text(text, message_type)
        sent_at = datetime.strptime(match.group("sent_at"), "%Y-%m-%d %H:%M")
        occurrence_key = f"{sent_at.isoformat()}|{match.group('sender').strip()}|{text}"
        occurrences[occurrence_key] += 1
        parsed.append(
            {
                "contact_name": contact_name,
                "contact_username": contact_username,
                "message_text": text,
                "message_timestamp": int(sent_at.timestamp()),
                "message_type": message_type,
                "unread_count": 1,
                "occurrence": occurrences[occurrence_key],
                "raw_line": line,
            }
        )
    return parsed


def message_fingerprint(message: dict[str, Any]) -> str:
    stable_fields = [
        str(message["contact_username"]),
        str(message["message_timestamp"]),
        str(message["message_text"]),
        str(message.get("occurrence") or 1),
    ]
    return hashlib.sha256("\0".join(stable_fields).encode("utf-8")).hexdigest()


def store_messages(messages: list[dict[str, Any]], db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    collected_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inserted: list[dict[str, Any]] = []
    with sqlite3.connect(db_path) as conn:
        for message in messages:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO unread_messages (
                    fingerprint, contact_name, contact_username, message_text,
                    message_timestamp, message_type, unread_count, raw_json, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_fingerprint(message), message["contact_name"],
                    message["contact_username"], message["message_text"],
                    message["message_timestamp"], message["message_type"],
                    message.get("unread_count", 1),
                    json.dumps(message, ensure_ascii=False, sort_keys=True), collected_at,
                ),
            )
            if cursor.rowcount == 1:
                inserted.append(message)
    return inserted


def get_cursor(contact_username: str, db_path: Path = DB_PATH) -> int | None:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT last_session_timestamp FROM contact_cursors WHERE contact_username = ?",
            (contact_username,),
        ).fetchone()
    return int(row[0]) if row else None


def cursor_count(db_path: Path = DB_PATH) -> int:
    with sqlite3.connect(db_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM contact_cursors").fetchone()[0])


def update_cursor(message: dict[str, Any], db_path: Path = DB_PATH) -> None:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO contact_cursors (
                contact_username, contact_name, last_session_timestamp, updated_at
            ) VALUES (?, ?, ?, ?)
            ON CONFLICT(contact_username) DO UPDATE SET
                contact_name = excluded.contact_name,
                last_session_timestamp = MAX(last_session_timestamp, excluded.last_session_timestamp),
                updated_at = excluded.updated_at
            """,
            (
                str(message["username"]), str(message.get("chat") or message["username"]),
                int(message.get("timestamp") or 0), now,
            ),
        )


def history_start_time(previous_timestamp: int) -> str:
    # Include the cursor's minute because history timestamps do not expose seconds.
    start = datetime.fromtimestamp(previous_timestamp).replace(second=0)
    return start.strftime("%Y-%m-%d %H:%M:%S")


def collect_session_history(
    session: dict[str, Any],
    *,
    first_call: bool,
    db_path: Path = DB_PATH,
) -> list[dict[str, Any]]:
    previous = get_cursor(str(session["username"]), db_path)
    limit = HISTORY_LIMIT
    args = ["history", str(session["username"])]
    if previous is not None:
        args.extend(["--start-time", history_start_time(previous)])
    elif first_call:
        limit = max(int(session.get("unread") or 1), 1)
    else:
        session_timestamp = int(session.get("timestamp") or time.time())
        start = datetime.fromtimestamp(session_timestamp - INITIAL_LOOKBACK_SECONDS)
        args.extend(["--start-time", start.strftime("%Y-%m-%d %H:%M:%S")])
    args.extend(["--limit", str(limit)])

    payload = run_wechat_cli(*args)
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise ValueError("wechat-cli history must return an object containing messages")
    messages = parse_history_lines(
        payload["messages"],
        contact_name=str(session.get("chat") or session["username"]),
        contact_username=str(session["username"]),
    )
    update_cursor(session, db_path)
    return messages


def seed_contact_cursors(db_path: Path = DB_PATH) -> None:
    payload = run_wechat_cli("sessions", "--limit", "10000")
    if not isinstance(payload, list):
        raise ValueError("wechat-cli sessions must return a JSON array")
    audited_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    eligible_usernames: list[str] = []
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM session_audit")
        for session in payload:
            if not isinstance(session, dict):
                continue
            category, reason = classify_session(session)
            username = str(session.get("username") or "")
            conn.execute(
                """
                INSERT INTO session_audit (
                    username, contact_name, category, eligible_for_autoreply,
                    exclusion_reason, unread_count, last_message_type,
                    last_session_timestamp, audited_at, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username, str(session.get("chat") or username), category,
                    int(category == "private_contact"), reason,
                    int(session.get("unread") or 0), str(session.get("msg_type") or ""),
                    int(session.get("timestamp") or 0), audited_at,
                    json.dumps(session, ensure_ascii=False, sort_keys=True),
                ),
            )
            if category == "private_contact":
                eligible_usernames.append(username)
        if eligible_usernames:
            placeholders = ",".join("?" for _ in eligible_usernames)
            conn.execute(
                f"DELETE FROM contact_cursors WHERE contact_username NOT IN ({placeholders})",
                eligible_usernames,
            )
        else:
            conn.execute("DELETE FROM contact_cursors")
    for session in payload:
        if isinstance(session, dict) and is_private_session(session):
            update_cursor(session, db_path)


def poll(db_path: Path = DB_PATH) -> dict[str, Any]:
    global unread_text
    init_database(db_path)
    payload = run_wechat_cli("new-messages")
    if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
        raise ValueError("wechat-cli new-messages must return an object containing messages")

    needs_cursor_baseline = cursor_count(db_path) == 0
    sessions = [message for message in payload["messages"] if is_private_activity_summary(message)]
    collected: list[dict[str, Any]] = []
    for session in sessions:
        collected.extend(
            collect_session_history(session, first_call=bool(payload.get("first_call")), db_path=db_path)
        )
    if needs_cursor_baseline:
        seed_contact_cursors(db_path)
    unread_text = store_messages(collected, db_path)
    return {
        "activity_count": len(sessions),
        "inserted_count": len(unread_text),
        "unread_text": unread_text,
    }


def main() -> int:
    try:
        result = poll()
    except Exception as exc:
        print(f"[autoreply] poll failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
