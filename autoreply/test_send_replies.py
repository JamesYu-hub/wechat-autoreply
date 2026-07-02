from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoreply import poll_unread, send_replies


class SendRepliesTests(unittest.TestCase):
    @patch("autoreply.send_replies.send_generated")
    def test_send_contacts_sends_each_contact_separately(self, send_generated) -> None:
        send_generated.side_effect = [[{"id": 1}], RuntimeError("failed")]

        result = send_replies.send_contacts({"b", "a"})

        self.assertEqual(send_generated.call_args_list[0].args[0], "a")
        self.assertEqual(send_generated.call_args_list[1].args[0], "b")
        self.assertEqual(result["sent"], [{"id": 1}])
        self.assertEqual(result["errors"][0]["contact_username"], "b")

    def test_mark_sent_updates_draft_and_source_messages(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            poll_unread.store_messages([self.message()], db_path)
            with sqlite3.connect(db_path) as conn:
                message_id = conn.execute("SELECT id FROM unread_messages").fetchone()[0]
                draft_id = conn.execute(
                    """
                    INSERT INTO reply_drafts (
                        request_fingerprint, contact_name, contact_username, system_prompt,
                        user_prompt, reply_text, reply_messages_json, status, model, created_at
                    ) VALUES ('fingerprint', '甲', 'a', 'system', 'user', '好\\n收到',
                              '["好","收到"]', 'generated', 'model', 'now')
                    """
                ).lastrowid
                conn.execute(
                    "INSERT INTO reply_draft_messages (draft_id, message_id) VALUES (?, ?)",
                    (draft_id, message_id),
                )

            send_replies.mark_sent(draft_id, ["好", "收到"], db_path)

            with sqlite3.connect(db_path) as conn:
                draft_status = conn.execute("SELECT status FROM reply_drafts").fetchone()[0]
                message_status = conn.execute("SELECT status FROM unread_messages").fetchone()[0]
                turns = conn.execute(
                    "SELECT role, content FROM conversation_turns ORDER BY id"
                ).fetchall()
            self.assertEqual(draft_status, "sent")
            self.assertEqual(message_status, "replied")
            self.assertEqual([turn[0] for turn in turns], ["user", "assistant"])
            self.assertIn("收到", turns[1][1])

    @staticmethod
    def message() -> dict[str, object]:
        return {
            "contact_name": "甲",
            "contact_username": "a",
            "message_text": "你好",
            "message_timestamp": 1,
            "message_type": "文本",
            "unread_count": 1,
            "occurrence": 1,
            "raw_line": "你好",
        }
