"""
WhatsApp notification module.
Supports:
1. Official Twilio WhatsApp API (TwilioWhatsAppSender)
2. Free CallMeBot WhatsApp API (CallMeBotWhatsAppSender - zero-cost personal WhatsApp gateway)
3. Local Outbox & Fallback Sender (LocalOutboxWhatsAppSender - records dispatches without crashing)
Includes message splitting for WhatsApp's 1600-character limit and error fallback alerts.
"""

from __future__ import annotations

import logging
import os
import urllib.parse
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import requests

logger = logging.getLogger(__name__)

# Twilio WhatsApp message body limit is 1600 characters.
# Safety threshold at 1500 to account for unicode and metadata.
MAX_WHATSAPP_MSG_LENGTH = 1500
IST = timezone(timedelta(hours=5, minutes=30))


class BaseWhatsAppSender(ABC):
    """Abstract Base Class for WhatsApp message senders."""

    @abstractmethod
    def send_text(self, to_number: str, text: str) -> bool:
        """Sends a single text message to the recipient."""
        raise NotImplementedError


class TwilioWhatsAppSender(BaseWhatsAppSender):
    """Official Twilio WhatsApp API implementation."""

    def __init__(
        self,
        account_sid: Optional[str] = None,
        auth_token: Optional[str] = None,
        from_number: Optional[str] = None,
    ) -> None:
        self.account_sid = account_sid or os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        self.auth_token = auth_token or os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        self.from_number = from_number or os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886").strip()

    def send_text(self, to_number: str, text: str) -> bool:
        """Sends a text message using Twilio REST Client."""
        if not self.account_sid or not self.auth_token:
            raise ValueError(
                "TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be configured in .env to send messages via Twilio."
            )

        from twilio.rest import Client

        client = Client(self.account_sid, self.auth_token)
        formatted_to = to_number if to_number.startswith("whatsapp:") else f"whatsapp:{to_number}"
        formatted_from = self.from_number if self.from_number.startswith("whatsapp:") else f"whatsapp:{self.from_number}"

        logger.info("Sending WhatsApp message via Twilio from %s to %s (%d chars)",
                    formatted_from, formatted_to, len(text))
        try:
            message = client.messages.create(
                body=text,
                from_=formatted_from,
                to=formatted_to,
            )
            logger.info("Twilio message dispatched successfully (SID: %s, Status: %s)",
                        message.sid, message.status)
            return True
        except Exception as err:
            logger.error("Failed to send Twilio WhatsApp message: %s", err)
            raise


class CallMeBotWhatsAppSender(BaseWhatsAppSender):
    """
    CallMeBot Free WhatsApp API:
    Allows zero-setup free WhatsApp notifications to personal phone numbers.
    Setup: Send 'I allow callmebot to send me messages' to +34 644 44 47 62 on WhatsApp.
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("CALLMEBOT_API_KEY", "").strip()

    def send_text(self, to_number: str, text: str) -> bool:
        clean_phone = to_number.replace("whatsapp:", "").replace("+", "").strip()
        encoded_text = urllib.parse.quote(text)
        url = f"https://api.callmebot.com/whatsapp.php?phone={clean_phone}&text={encoded_text}&apikey={self.api_key}"

        logger.info("Sending WhatsApp message via CallMeBot to %s...", clean_phone)
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                logger.info("CallMeBot message sent successfully.")
                return True
            else:
                logger.warning("CallMeBot returned status %d: %s", resp.status_code, resp.text)
                return False
        except Exception as err:
            logger.error("CallMeBot request failed: %s", err)
            raise


class LocalOutboxWhatsAppSender(BaseWhatsAppSender):
    """
    Autonomous fallback sender:
    Logs messages to console and appends to 'outbox/sent_messages.log'
    when external SMS/WhatsApp API keys are not yet configured.
    Ensures zero-crash automated execution in CI/CD and local environments.
    """

    def __init__(self, log_file: str = "sent_messages.log") -> None:
        self.log_file = log_file

    def send_text(self, to_number: str, text: str) -> bool:
        now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        divider = "=" * 60
        entry = (
            f"\n{divider}\n"
            f"DISPATCHED AT: {now_str}\n"
            f"RECIPIENT:     {to_number}\n"
            f"CONTENT:\n{text}\n"
            f"{divider}\n"
        )
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(entry)
            logger.info("Dispatched to local outbox log: %s (Recipient: %s)", self.log_file, to_number)
        except Exception as err:
            logger.warning("Could not append to %s: %s", self.log_file, err)

        print(entry)
        return True


def get_whatsapp_sender() -> BaseWhatsAppSender:
    """
    Factory function returning the most appropriate WhatsApp sender:
    1. If Twilio keys exist -> TwilioWhatsAppSender
    2. If CallMeBot key exists -> CallMeBotWhatsAppSender
    3. Otherwise -> LocalOutboxWhatsAppSender (autonomous zero-crash dispatcher)
    """
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if twilio_sid and twilio_token and not twilio_sid.startswith("ACXXXXX"):
        return TwilioWhatsAppSender(twilio_sid, twilio_token)

    callmebot_key = os.getenv("CALLMEBOT_API_KEY", "").strip()
    if callmebot_key:
        return CallMeBotWhatsAppSender(callmebot_key)

    logger.info("No external WhatsApp API credentials configured; using LocalOutboxWhatsAppSender.")
    return LocalOutboxWhatsAppSender()


def split_message_if_needed(text: str, max_chars: int = MAX_WHATSAPP_MSG_LENGTH) -> List[str]:
    """
    Splits text into chunks <= max_chars, breaking only on paragraph or line boundaries
    to prevent truncating code snippets or sentences mid-word.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_len = 0

    lines = text.split("\n")
    for line in lines:
        line_len = len(line) + 1  # +1 for newline
        if current_len + line_len > max_chars and current_chunk:
            chunks.append("\n".join(current_chunk).strip())
            current_chunk = [line]
            current_len = line_len
        else:
            current_chunk.append(line)
            current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk).strip())

    return chunks


def format_difficulty_badge(difficulty: str) -> str:
    """Returns a visual badge for difficulty."""
    diff_lower = difficulty.lower()
    if diff_lower == "easy":
        return "🟢 *Easy*"
    elif diff_lower == "medium":
        return "🟡 *Medium*"
    elif diff_lower == "hard":
        return "🔴 *Hard*"
    return f"⚪ *{difficulty}*"


def format_morning_messages(problem: Any, solution: Any) -> List[str]:
    """
    Constructs the complete morning message containing:
    - Title, Difficulty, Link
    - Short Summary
    - Approach Explanation
    - Time & Space Complexity
    - Verified Solution Code
    Returns a list of 1 or more message chunks respecting WhatsApp limits.
    """
    diff_badge = format_difficulty_badge(problem.difficulty)
    verified_badge = "✅ *Verified with Example Tests*" if solution.verified else "⚠️ *Verification Pending*"

    # Part 1: Problem Overview and Approach
    part1 = (
        f"☀️ *LeetCode Problem of the Day*\n"
        f"📅 {problem.date}\n\n"
        f"📌 *{problem.id}. {problem.title}* ({diff_badge})\n"
        f"🔗 {problem.link}\n\n"
        f"📝 *Summary:*\n{problem.get_summary(300)}\n\n"
        f"💡 *Approach:*\n{solution.approach}\n\n"
        f"📊 *Complexity:*\n"
        f"• Time: `{solution.time_complexity}`\n"
        f"• Space: `{solution.space_complexity}`\n\n"
        f"🛡️ *Status:* {verified_badge}"
    )

    # Part 2: Verified Code Snippet
    part2 = (
        f"💻 *Python 3 Solution:*\n"
        f"```python\n{solution.code.strip()}\n```"
    )

    full_message = f"{part1}\n\n{part2}"

    # If the combined message fits cleanly within WhatsApp limits, send as 1 message
    if len(full_message) <= MAX_WHATSAPP_MSG_LENGTH:
        return [full_message]

    # Otherwise, split cleanly into Part 1 and Part 2 (with Part numbering)
    part1_labeled = f"{part1}\n\n_(1/2 - Code follows below)_"
    part2_labeled = f"💻 *Python 3 Solution (2/2):*\n```python\n{solution.code.strip()}\n```"

    result_chunks: List[str] = [part1_labeled]
    result_chunks.extend(split_message_if_needed(part2_labeled, MAX_WHATSAPP_MSG_LENGTH))
    return result_chunks


def format_evening_message(problem: Any, hint: str) -> str:
    """
    Constructs the short evening reminder message:
    'Reminder: today's LeetCode problem is <title> (<difficulty>). Have you solved it yet? <link>'
    plus a one-line hint.
    """
    diff_badge = format_difficulty_badge(problem.difficulty)
    return (
        f"🔔 *Evening LeetCode Reminder*\n\n"
        f"Reminder: Today's problem is *{problem.title}* ({diff_badge}).\n"
        f"Have you solved it yet? 🚀\n\n"
        f"🔗 *Solve here:* {problem.link}\n\n"
        f"💡 *Hint:* {hint.strip()}"
    )


def format_error_fallback_message(error_details: str) -> str:
    """Constructs a fallback notification if the daily workflow encountered an error."""
    return (
        f"⚠️ *LeetCode Daily Bot Alert*\n\n"
        f"We encountered an issue processing today's Problem of the Day.\n\n"
        f"Error details:\n`{error_details[:300]}`\n\n"
        f"Please check the workflow logs."
    )
