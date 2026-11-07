#!/usr/bin/env python3
"""
LeetCode Problem of the Day WhatsApp Bot.

Dispatches a verified daily solution in the morning (10:30 AM IST)
and a helpful progress reminder with a conceptual hint in the evening (6:30 PM IST).

CLI Usage:
    python main.py --mode morning --dry-run
    python main.py --mode evening --dry-run
    python main.py --mode morning
    python main.py --mode evening
    python main.py --mode morning --force
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone, timedelta

# Ensure UTF-8 output on all systems (Windows, Linux, macOS)
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from dotenv import load_dotenv

# Load local .env if present
load_dotenv()

from leetcode import fetch_daily_problem, LeetCodeProblem
from solver import SolutionGenerator, SolutionResult
from whatsapp import (
    get_whatsapp_sender,
    format_morning_messages,
    format_evening_message,
    format_error_fallback_message,
)
from state import StateManager, IST

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("leetcode_bot")


def get_current_date_ist() -> str:
    """Returns today's date in YYYY-MM-DD format based on Indian Standard Time."""
    return datetime.now(IST).strftime("%Y-%m-%d")


def run_morning_mode(
    dry_run: bool,
    force: bool,
    to_number: str,
    state_mgr: StateManager,
) -> int:
    """Executes the morning workflow: Fetch POTD -> Solve -> Verify -> Send."""
    today_str = get_current_date_ist()
    logger.info("Starting MORNING run for date: %s", today_str)

    # 1. Duplicate protection check
    if not force and state_mgr.is_already_sent_today(today_str, "morning"):
        logger.info("Morning message already dispatched today (%s). Skipping (use --force to override).", today_str)
        return 0

    # 2. Fetch LeetCode POTD
    try:
        problem = fetch_daily_problem()
    except Exception as err:
        logger.error("Failed to fetch LeetCode POTD: %s", err)
        if not dry_run:
            sender = get_whatsapp_sender()
            fallback = format_error_fallback_message(f"Failed to fetch LeetCode POTD: {err}")
            sender.send_text(to_number, fallback)
        return 1

    # 3. Solve & Verify Solution
    solver = SolutionGenerator()
    solution = solver.solve_and_verify(problem, max_retries=3)

    # 4. Save state for evening reminder reuse
    state_mgr.save_state(today_str, problem, solution, hint=solution.hint)

    # 5. Format message(s)
    messages = format_morning_messages(problem, solution)

    # 6. Send or Dry-Run Print
    if dry_run:
        print("\n" + "=" * 60)
        print(" [DRY RUN] MORNING WHATSAPP MESSAGE DISPATCH")
        print(f" Recipient: {to_number}")
        print(f" Total Message Chunks: {len(messages)}")
        print("=" * 60)
        for idx, msg in enumerate(messages, 1):
            print(f"\n--- [Chunk {idx}/{len(messages)}] ({len(msg)} characters) ---")
            print(msg)
        print("\n" + "=" * 60)
        print(" [DRY RUN] Completed successfully. (No actual SMS/WhatsApp API charges)")
        print("=" * 60 + "\n")
    else:
        sender = get_whatsapp_sender()
        for idx, msg in enumerate(messages, 1):
            logger.info("Dispatching chunk %d/%d to %s...", idx, len(messages), to_number)
            sender.send_text(to_number, msg)
        state_mgr.mark_as_sent(today_str, "morning")
        logger.info("Morning run finished successfully.")

    return 0


def run_evening_mode(
    dry_run: bool,
    force: bool,
    to_number: str,
    state_mgr: StateManager,
) -> int:
    """Executes the evening workflow: Check state -> Generate Hint -> Send short reminder."""
    today_str = get_current_date_ist()
    logger.info("Starting EVENING run for date: %s", today_str)

    # 1. Duplicate protection check
    if not force and state_mgr.is_already_sent_today(today_str, "evening"):
        logger.info("Evening reminder already dispatched today (%s). Skipping (use --force to override).", today_str)
        return 0

    # 2. Check saved state
    state = state_mgr.load_state()
    problem_obj = None
    hint_text = ""

    if state and state.get("date") == today_str and state.get("problem"):
        p_dict = state["problem"]
        logger.info("Reusing existing morning state for '%s'", p_dict.get("title"))
        # Reconstruct light problem object
        problem_obj = type("SimpleProblem", (), p_dict)()
        hint_text = state.get("solution", {}).get("hint", "")

    # 3. Fallback: If state is missing or from yesterday, re-fetch question
    if not problem_obj or not getattr(problem_obj, "title", None):
        logger.warning("No state found for today (%s). Re-fetching question from LeetCode...", today_str)
        try:
            problem_obj = fetch_daily_problem()
            hint_text = (
                problem_obj.hints[0] if problem_obj.hints
                else "Break down the problem constraints and check whether a greedy, two-pointer, or heap simulation applies."
            )
            state_mgr.save_state(today_str, problem_obj, hint=hint_text)
        except Exception as err:
            logger.error("Failed to fetch LeetCode POTD in evening fallback: %s", err)
            if not dry_run:
                sender = get_whatsapp_sender()
                fallback = format_error_fallback_message(f"Failed to fetch evening reminder: {err}")
                sender.send_text(to_number, fallback)
            return 1

    if not hint_text:
        hint_text = "Think about optimal sub-structures and consider sorting or priority queues."

    # 4. Format evening reminder
    message = format_evening_message(problem_obj, hint_text)

    # 5. Send or Dry-Run Print
    if dry_run:
        print("\n" + "=" * 60)
        print(" [DRY RUN] EVENING WHATSAPP REMINDER DISPATCH")
        print(f" Recipient: {to_number}")
        print(f" Total Length: {len(message)} characters")
        print("=" * 60)
        print(message)
        print("\n" + "=" * 60)
        print(" [DRY RUN] Completed successfully. (No actual SMS/WhatsApp API charges)")
        print("=" * 60 + "\n")
    else:
        sender = get_whatsapp_sender()
        sender.send_text(to_number, message)
        state_mgr.mark_as_sent(today_str, "evening")
        logger.info("Evening reminder finished successfully.")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LeetCode Problem of the Day WhatsApp Bot",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        choices=["morning", "evening"],
        default="morning",
        help="Execution mode: 'morning' (solution & explanation) or 'evening' (reminder & hint)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print messages to stdout without calling the Twilio WhatsApp API",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force execution even if already sent today (bypasses duplicate protection)",
    )
    parser.add_argument(
        "--state-file",
        default="state.json",
        help="Path to state persistence file",
    )

    args = parser.parse_args()

    to_number = os.getenv("TO_WHATSAPP_NUMBER", "whatsapp:+917807221279").strip()
    state_mgr = StateManager(args.state_file)

    if args.mode == "morning":
        return run_morning_mode(args.dry_run, args.force, to_number, state_mgr)
    elif args.mode == "evening":
        return run_evening_mode(args.dry_run, args.force, to_number, state_mgr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
