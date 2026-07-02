from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from autoreply import poll_unread


class PollUnreadTests(unittest.TestCase):
    def test_filters_sessions(self) -> None:
        self.assertTrue(poll_unread.is_private_text_summary(self.session()))
        self.assertFalse(poll_unread.is_private_text_summary(self.session(username="123@chatroom", is_group=True)))
        self.assertFalse(poll_unread.is_private_text_summary(self.session(username="gh_news")))
        self.assertFalse(poll_unread.is_private_text_summary(self.session(username="brandsessionholder")))
        self.assertFalse(poll_unread.is_private_text_summary(self.session(username="notifymessage")))
        self.assertFalse(poll_unread.is_private_text_summary(self.session(username="123@openim")))
        self.assertFalse(poll_unread.is_private_text_summary(self.session(msg_type="图片")))

    def test_parses_all_incoming_lines_and_ignores_my_messages(self) -> None:
        messages = poll_unread.parse_history_lines(
            [
                "[2026-06-13 19:09] 朋友: 相同内容",
                "[2026-06-13 19:09] 朋友: 相同内容",
                "[2026-06-13 19:10] me: 我的回复",
                "[2026-06-13 19:11] 朋友: 第三条",
            ],
            contact_name="朋友",
            contact_username="wxid_friend",
        )

        self.assertEqual([message["message_text"] for message in messages], ["相同内容", "相同内容", "第三条"])
        self.assertEqual([message["occurrence"] for message in messages], [1, 2, 1])

    def test_sanitizes_media_messages_for_prompt(self) -> None:
        messages = poll_unread.parse_history_lines(
            [
                "[2026-06-13 19:09] 朋友: [图片] (local_id=12)",
                "[2026-06-13 19:10] 朋友: [文件] 报告.pdf",
                "[2026-06-13 19:11] 朋友: [语音] <msg>secret</msg>",
            ],
            contact_name="朋友",
            contact_username="wxid_friend",
        )

        self.assertEqual([message["message_type"] for message in messages], ["图片", "文件", "语音"])
        self.assertEqual(messages[0]["message_text"], "[图片，当前无法识别图片内容]")
        self.assertEqual(messages[2]["message_text"], "[语音消息，当前无法读取语音内容]")

    def test_deduplicates_history_overlap_but_keeps_identical_messages(self) -> None:
        messages = poll_unread.parse_history_lines(
            [
                "[2026-06-13 19:09] 朋友: 相同内容",
                "[2026-06-13 19:09] 朋友: 相同内容",
            ],
            contact_name="朋友",
            contact_username="wxid_friend",
        )
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "messages.sqlite3"
            poll_unread.init_database(db_path)
            self.assertEqual(len(poll_unread.store_messages(messages, db_path)), 2)
            self.assertEqual(poll_unread.store_messages(messages, db_path), [])
            with sqlite3.connect(db_path) as conn:
                count = conn.execute("SELECT COUNT(*) FROM unread_messages").fetchone()[0]
            self.assertEqual(count, 2)

    @staticmethod
    def session(
        *,
        username: str = "wxid_friend",
        is_group: bool = False,
        msg_type: str = "文本",
    ) -> dict[str, object]:
        return {
            "chat": "朋友",
            "username": username,
            "is_group": is_group,
            "unread": 3,
            "last_message": "你好",
            "msg_type": msg_type,
            "timestamp": 1781351924,
        }


if __name__ == "__main__":
    unittest.main()
