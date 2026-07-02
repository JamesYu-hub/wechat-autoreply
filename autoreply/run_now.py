#!/usr/bin/env python3
"""Immediately poll, generate drafts, and optionally send one contact's reply."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from autoreply import adaptive_scheduler, generate_replies, poll_unread, send_replies


def reset_idle_timer(
    *,
    state_path: Path = adaptive_scheduler.STATE_PATH,
    clock: callable = time.time,
) -> dict:
    state = adaptive_scheduler.default_state()
    state["next_poll_at"] = clock() + adaptive_scheduler.IDLE_INTERVAL_SECONDS
    adaptive_scheduler.save_state(state, state_path)
    return state


def run_now(
    *,
    send: bool = False,
    contact: str | None = None,
    state_path: Path = adaptive_scheduler.STATE_PATH,
    clock: callable = time.time,
) -> dict:
    if send and not contact:
        raise ValueError("--send requires --contact")
    poll_result = poll_unread.poll()
    drafts = generate_replies.generate_all()
    result = {"poll": poll_result, "reply_drafts": drafts}
    if send:
        sent = send_replies.send_generated(contact)
        result["sent"] = {
            "contact": contact,
            "draft_count": len(sent),
            "messages": [message for draft in sent for message in draft["reply_messages"]],
        }
    result["scheduler"] = reset_idle_timer(state_path=state_path, clock=clock)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--send", action="store_true", help="Actually send the generated reply.")
    parser.add_argument("--contact", help="Exact display name or username to send.")
    args = parser.parse_args()
    try:
        result = run_now(send=args.send, contact=args.contact)
    except Exception as exc:
        print(f"[autoreply] immediate run failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
