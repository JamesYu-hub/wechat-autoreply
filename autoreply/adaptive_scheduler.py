#!/usr/bin/env python3
"""Persisted adaptive scheduler: idle every 5 minutes, active every 10 seconds."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from autoreply import generate_replies, poll_unread, send_replies


BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = Path(os.environ.get("AUTOREPLY_SCHEDULER_STATE", BASE_DIR / "scheduler_state.json"))
IDLE_INTERVAL_SECONDS = int(os.environ.get("AUTOREPLY_IDLE_INTERVAL_SECONDS", "300"))
ACTIVE_INTERVAL_SECONDS = int(os.environ.get("AUTOREPLY_ACTIVE_INTERVAL_SECONDS", "10"))
EMPTY_POLLS_TO_IDLE = int(os.environ.get("AUTOREPLY_EMPTY_POLLS_TO_IDLE", "30"))
IDLE_WAKE_EARLY_TOLERANCE_SECONDS = float(
    os.environ.get("AUTOREPLY_IDLE_WAKE_EARLY_TOLERANCE_SECONDS", "5")
)


def default_state() -> dict[str, Any]:
    return {
        "mode": "idle",
        "interval_seconds": IDLE_INTERVAL_SECONDS,
        "consecutive_empty_polls": 0,
        "next_poll_at": 0.0,
    }


def load_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        return {**default_state(), **json.loads(path.read_text(encoding="utf-8"))}
    except (OSError, ValueError, TypeError):
        return default_state()


def save_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def apply_result(state: dict[str, Any], activity_count: int, now: float) -> bool:
    if activity_count > 0:
        state.update(
            mode="active",
            interval_seconds=ACTIVE_INTERVAL_SECONDS,
            consecutive_empty_polls=0,
            next_poll_at=now + ACTIVE_INTERVAL_SECONDS,
        )
        return True

    if state["mode"] == "active":
        state["consecutive_empty_polls"] += 1
        if state["consecutive_empty_polls"] >= EMPTY_POLLS_TO_IDLE:
            state.update(
                mode="idle",
                interval_seconds=IDLE_INTERVAL_SECONDS,
                consecutive_empty_polls=0,
                next_poll_at=now + IDLE_INTERVAL_SECONDS,
            )
            return False
        state["next_poll_at"] = now + ACTIVE_INTERVAL_SECONDS
        return True

    state.update(
        interval_seconds=IDLE_INTERVAL_SECONDS,
        consecutive_empty_polls=0,
        next_poll_at=now + IDLE_INTERVAL_SECONDS,
    )
    return False


def run(
    *,
    poller: Callable[[], dict[str, Any]] = poll_unread.poll,
    sleeper: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.time,
    state_path: Path = STATE_PATH,
) -> None:
    state = load_state(state_path)
    now = clock()
    # Cron wakes on the minute, while a completed poll may schedule the next
    # run a second or two after it. Allow that small drift so a one-minute
    # interval does not accidentally become a two-minute interval.
    if (
        state["mode"] == "idle"
        and now + IDLE_WAKE_EARLY_TOLERANCE_SECONDS < float(state["next_poll_at"])
    ):
        print(json.dumps({"skipped": True, **state}, ensure_ascii=False))
        return

    while True:
        result = poller()
        if int(result.get("inserted_count") or 0) > 0:
            contacts = {
                str(message["contact_username"])
                for message in result.get("unread_text", [])
                if message.get("contact_username")
            }
            try:
                result["reply_drafts"] = generate_replies.generate_all(contact_usernames=contacts)
                result["sent_replies"] = send_replies.send_contacts(contacts)
            except Exception as exc:
                result["autoreply_error"] = str(exc)
        now = clock()
        keep_running = apply_result(state, int(result.get("activity_count") or 0), now)
        save_state(state, state_path)
        print(json.dumps({**result, "scheduler": state}, ensure_ascii=False), flush=True)
        if not keep_running:
            if IDLE_INTERVAL_SECONDS < 60:
                sleeper(IDLE_INTERVAL_SECONDS)
                continue
            return
        sleeper(int(state["interval_seconds"]))


if __name__ == "__main__":
    run()
