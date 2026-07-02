from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from autoreply import generate_replies, poll_unread


class GenerateRepliesTests(unittest.TestCase):
    def test_punctuation_only_reply_uses_safe_fallback(self) -> None:
        self.assertEqual(generate_replies.normalize_message("？？"), generate_replies.FALLBACK_REPLY)
        self.assertEqual(generate_replies.normalize_message("好的"), "好的")
        self.assertEqual(
            generate_replies.normalize_message("我看了你发的链接，稍后回复。"),
            "收到你发的链接了，稍后回复。",
        )
        self.assertEqual(generate_replies.normalize_message("你他妈看一下"), generate_replies.FALLBACK_REPLY)

    def test_parses_multiple_reply_messages(self) -> None:
        self.assertEqual(
            generate_replies.parse_reply_messages('{"messages":["我去，真的假的","等我看看"]}'),
            ["我去，真的假的", "等我看看"],
        )

    def test_question_mark_only_gets_conversational_reply(self) -> None:
        batch = {"messages": [{"message_text": "？？"}]}
        self.assertEqual(
            generate_replies.enforce_batch_safety(["怎么了"], batch),
            ["啥意思"],
        )

    def test_pending_messages_are_grouped_by_contact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            poll_unread.store_messages(
                [
                    self.message("a", "甲", "第一条", 1),
                    self.message("b", "乙", "另一人", 2),
                    self.message("a", "甲", "第二条", 3),
                ],
                db_path,
            )

            batches = generate_replies.pending_batches(db_path)

            self.assertEqual(len(batches), 2)
            batch_a = next(batch for batch in batches if batch["contact_username"] == "a")
            self.assertEqual([message["message_text"] for message in batch_a["messages"]], ["第一条", "第二条"])

    def test_pending_batches_can_be_scoped_to_current_contacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            poll_unread.store_messages(
                [self.message("new", "新联系人", "新消息", 1), self.message("old", "旧联系人", "旧消息", 2)],
                db_path,
            )

            batches = generate_replies.pending_batches(db_path, {"new"})

            self.assertEqual([batch["contact_username"] for batch in batches], ["new"])

    def test_generates_one_draft_for_one_contacts_complete_batch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            poll_unread.store_messages(
                [self.message("a", "甲", "第一条", 1), self.message("a", "甲", "第二条", 2)],
                db_path,
            )

            with patch.object(generate_replies, "call_qwen", return_value=["好的", "我晚点看看。"]) as call:
                first = generate_replies.generate_all(db_path)
                second = generate_replies.generate_all(db_path)

            self.assertEqual(first[0]["reply_messages"], ["好的", "我晚点看看。"])
            self.assertEqual(second[0]["draft_id"], first[0]["draft_id"])
            self.assertEqual(call.call_count, 1)
            self.assertIn("第一条", call.call_args.args[1])
            self.assertIn("第二条", call.call_args.args[1])
            self.assertEqual(call.call_args.args[2], [])

    def test_sticker_only_batch_is_ignored_without_calling_model(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            message = self.message("a", "甲", "[表情]", 1)
            message["message_type"] = "表情"
            poll_unread.store_messages([message], db_path)

            with patch.object(generate_replies, "call_qwen") as call:
                result = generate_replies.generate_all(db_path)

            self.assertEqual(result[0]["status"], "ignored")
            call.assert_not_called()

    def test_bracketed_wechat_sticker_is_recognized(self) -> None:
        self.assertTrue(
            generate_replies.is_sticker_only_batch(
                {"messages": [{"message_type": "文本", "message_text": "[皱眉]"}]}
            )
        )

    def test_conversation_history_is_isolated_per_contact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            import sqlite3

            with sqlite3.connect(db_path) as conn:
                conn.executemany(
                    """
                    INSERT INTO conversation_turns (
                        contact_username, role, content, source_key, created_at
                    ) VALUES (?, ?, ?, ?, 'now')
                    """,
                    [
                        ("a", "user", "甲的历史", "a-u"),
                        ("a", "assistant", "甲的回复", "a-a"),
                        ("b", "user", "乙的历史", "b-u"),
                    ],
                )

            self.assertEqual(
                generate_replies.conversation_history("a", db_path),
                [
                    {"role": "user", "content": "甲的历史"},
                    {"role": "assistant", "content": "甲的回复"},
                ],
            )

    @staticmethod
    def message(username: str, name: str, text: str, timestamp: int) -> dict[str, object]:
        return {
            "contact_name": name,
            "contact_username": username,
            "message_text": text,
            "message_timestamp": timestamp,
            "message_type": "文本",
            "unread_count": 1,
            "occurrence": 1,
            "raw_line": text,
        }


if __name__ == "__main__":
    unittest.main()
