from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from autoreply import adaptive_scheduler, run_now


class RunNowTests(unittest.TestCase):
    @patch("autoreply.run_now.send_replies.send_generated")
    @patch("autoreply.run_now.generate_replies.generate_all")
    @patch("autoreply.run_now.poll_unread.poll")
    def test_immediate_run_polls_and_generates_without_sending(self, poll, generate, send) -> None:
        poll.return_value = {"inserted_count": 1}
        generate.return_value = [{"draft_id": 1}]

        with tempfile.TemporaryDirectory() as directory:
            result = run_now.run_now(
                state_path=Path(directory) / "state.json",
                clock=lambda: 100,
            )

        self.assertEqual(result["poll"]["inserted_count"], 1)
        self.assertEqual(result["reply_drafts"], [{"draft_id": 1}])
        self.assertEqual(
            result["scheduler"]["next_poll_at"],
            100 + adaptive_scheduler.IDLE_INTERVAL_SECONDS,
        )
        send.assert_not_called()

    @patch("autoreply.run_now.send_replies.send_generated")
    @patch("autoreply.run_now.generate_replies.generate_all", return_value=[])
    @patch("autoreply.run_now.poll_unread.poll", return_value={"inserted_count": 1})
    def test_immediate_run_can_send_one_contact(self, poll, generate, send) -> None:
        send.return_value = [{"reply_messages": ["你好", "收到"]}]

        with tempfile.TemporaryDirectory() as directory:
            result = run_now.run_now(
                send=True,
                contact="甲",
                state_path=Path(directory) / "state.json",
                clock=lambda: 100,
            )

        send.assert_called_once_with("甲")
        self.assertEqual(result["sent"]["messages"], ["你好", "收到"])

    def test_send_requires_contact(self) -> None:
        with self.assertRaises(ValueError):
            run_now.run_now(send=True)

    def test_reset_timer_returns_to_idle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = run_now.reset_idle_timer(state_path=state_path, clock=lambda: 50)

            self.assertEqual(state["mode"], "idle")
            self.assertEqual(state["next_poll_at"], 50 + adaptive_scheduler.IDLE_INTERVAL_SECONDS)
