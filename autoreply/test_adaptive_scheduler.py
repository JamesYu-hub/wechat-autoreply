from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from autoreply import adaptive_scheduler


class AdaptiveSchedulerTests(unittest.TestCase):
    def test_idle_poll_runs_when_cron_wakes_slightly_before_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = adaptive_scheduler.default_state()
            state["next_poll_at"] = 101
            adaptive_scheduler.save_state(state, state_path)
            poller_calls = []

            with patch.object(adaptive_scheduler, "IDLE_INTERVAL_SECONDS", 60):
                adaptive_scheduler.run(
                    poller=lambda: poller_calls.append(True)
                    or {"activity_count": 0, "inserted_count": 0, "unread_text": []},
                    clock=lambda: 100,
                    state_path=state_path,
                )

        self.assertEqual(poller_calls, [True])

    def test_idle_poll_still_skips_well_before_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            state = adaptive_scheduler.default_state()
            state["next_poll_at"] = 110
            adaptive_scheduler.save_state(state, state_path)
            poller_calls = []

            adaptive_scheduler.run(
                poller=lambda: poller_calls.append(True) or {},
                clock=lambda: 100,
                state_path=state_path,
            )

        self.assertEqual(poller_calls, [])

    @patch("autoreply.adaptive_scheduler.send_replies.send_contacts")
    @patch("autoreply.adaptive_scheduler.generate_replies.generate_all")
    def test_new_messages_generate_and_send_only_current_contacts(self, generate, send) -> None:
        generate.return_value = [{"draft_id": 1}]
        send.return_value = {"sent": [{"id": 1}], "errors": []}
        poll_result = {
            "activity_count": 1,
            "inserted_count": 1,
            "unread_text": [{"contact_username": "new_contact"}],
        }

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(StopIteration):
                adaptive_scheduler.run(
                    poller=lambda: poll_result,
                    sleeper=lambda _: (_ for _ in ()).throw(StopIteration()),
                    clock=lambda: 100,
                    state_path=Path(directory) / "state.json",
                )

        generate.assert_called_once_with(contact_usernames={"new_contact"})
        send.assert_called_once_with({"new_contact"})

    def test_activity_switches_to_ten_second_mode(self) -> None:
        state = adaptive_scheduler.default_state()

        keep_running = adaptive_scheduler.apply_result(state, activity_count=1, now=100)

        self.assertTrue(keep_running)
        self.assertEqual(state["mode"], "active")
        self.assertEqual(state["interval_seconds"], 10)
        self.assertEqual(state["next_poll_at"], 110)

    def test_thirty_empty_active_polls_switch_back_to_idle_interval(self) -> None:
        state = adaptive_scheduler.default_state()
        adaptive_scheduler.apply_result(state, activity_count=1, now=100)

        for index in range(29):
            self.assertTrue(adaptive_scheduler.apply_result(state, activity_count=0, now=110 + index * 10))
        self.assertFalse(adaptive_scheduler.apply_result(state, activity_count=0, now=400))

        self.assertEqual(state["mode"], "idle")
        self.assertEqual(state["interval_seconds"], adaptive_scheduler.IDLE_INTERVAL_SECONDS)
        self.assertEqual(state["consecutive_empty_polls"], 0)
        self.assertEqual(state["next_poll_at"], 400 + adaptive_scheduler.IDLE_INTERVAL_SECONDS)


if __name__ == "__main__":
    unittest.main()
