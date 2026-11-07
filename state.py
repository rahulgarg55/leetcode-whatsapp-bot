"""
State management and duplicate protection module.
Persists daily problem details and verified solutions to state.json
to enable evening reminder reuse and prevent duplicate message dispatch.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_STATE_FILE = "state.json"
IST = timezone(timedelta(hours=5, minutes=30))


class StateManager:
    """Manages reading, writing, and deduplication checks in state.json."""

    def __init__(self, file_path: Optional[str] = None) -> None:
        self.file_path = file_path or os.getenv("STATE_FILE_PATH", DEFAULT_STATE_FILE)

    def load_state(self) -> Optional[Dict[str, Any]]:
        """Loads state dictionary from file, returning None if missing or corrupted."""
        if not os.path.exists(self.file_path):
            logger.info("No existing state file found at %s", self.file_path)
            return None

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data
        except Exception as err:
            logger.warning("Failed to parse state file %s: %s", self.file_path, err)
            return None

    def save_state(
        self,
        date_str: str,
        problem: Any,
        solution: Optional[Any] = None,
        hint: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Saves today's problem and solution data to state.json.
        Preserves existing sent_history if date matches.
        """
        existing = self.load_state() or {}
        existing_history = existing.get("sent_history", {}) if existing.get("date") == date_str else {}

        state_data: Dict[str, Any] = {
            "date": date_str,
            "updated_at": datetime.now(IST).isoformat(),
            "problem": {
                "id": getattr(problem, "id", problem.get("id") if isinstance(problem, dict) else ""),
                "title": getattr(problem, "title", problem.get("title") if isinstance(problem, dict) else ""),
                "title_slug": getattr(problem, "title_slug", problem.get("title_slug") if isinstance(problem, dict) else ""),
                "difficulty": getattr(problem, "difficulty", problem.get("difficulty") if isinstance(problem, dict) else ""),
                "link": getattr(problem, "link", problem.get("link") if isinstance(problem, dict) else ""),
                "summary": problem.get_summary() if hasattr(problem, "get_summary") else problem.get("summary", ""),
            },
            "sent_history": {
                "morning": existing_history.get("morning"),
                "evening": existing_history.get("evening"),
            },
        }

        if solution:
            state_data["solution"] = {
                "approach": getattr(solution, "approach", ""),
                "time_complexity": getattr(solution, "time_complexity", ""),
                "space_complexity": getattr(solution, "space_complexity", ""),
                "code": getattr(solution, "code", ""),
                "verified": getattr(solution, "verified", False),
                "attempts": getattr(solution, "attempts", 1),
                "verification_notes": getattr(solution, "verification_notes", ""),
                "hint": getattr(solution, "hint", hint or ""),
            }
        elif hint:
            state_data["solution"] = {"hint": hint}

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            logger.info("State successfully updated at %s", self.file_path)
        except Exception as err:
            logger.error("Failed to write state file %s: %s", self.file_path, err)

        return state_data

    def is_already_sent_today(self, date_str: str, mode: str) -> bool:
        """
        Checks whether the specified mode (morning or evening) has already
        been successfully dispatched today.
        """
        state = self.load_state()
        if not state or state.get("date") != date_str:
            return False

        sent_history = state.get("sent_history", {})
        timestamp = sent_history.get(mode.lower())
        if timestamp:
            logger.info("Duplicate check: mode '%s' was already sent at %s", mode, timestamp)
            return True
        return False

    def mark_as_sent(self, date_str: str, mode: str) -> None:
        """Marks the specified mode as sent with an ISO timestamp."""
        state = self.load_state() or {"date": date_str, "sent_history": {}}
        if state.get("date") != date_str:
            state["date"] = date_str
            state["sent_history"] = {}

        if "sent_history" not in state:
            state["sent_history"] = {}

        now_iso = datetime.now(IST).isoformat()
        state["sent_history"][mode.lower()] = now_iso

        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.info("Marked '%s' as sent at %s", mode, now_iso)
        except Exception as err:
            logger.error("Failed to update sent history in state: %s", err)
