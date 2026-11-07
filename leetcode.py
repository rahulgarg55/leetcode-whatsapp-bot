"""
LeetCode Problem of the Day (POTD) fetcher module.
Fetches daily coding challenge details from LeetCode's public GraphQL API.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from bs4 import BeautifulSoup
import requests

logger = logging.getLogger(__name__)

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

DAILY_QUESTION_QUERY = """
query questionOfToday {
    activeDailyCodingChallengeQuestion {
        date
        userStatus
        link
        question {
            questionId
            questionFrontendId
            title
            titleSlug
            content
            difficulty
            isPaidOnly
            codeSnippets {
                lang
                langSlug
                code
            }
            exampleTestcases
            hints
        }
    }
}
"""


@dataclass
class ExampleTestCase:
    """Represents a single example test case with input, expected output, and explanation."""
    input_raw: str
    output_raw: str
    explanation: Optional[str] = None


@dataclass
class LeetCodeProblem:
    """Structured representation of a LeetCode problem."""
    id: str
    title: str
    title_slug: str
    difficulty: str
    link: str
    date: str
    is_paid_only: bool
    statement_text: str
    html_content: str
    starter_code: str
    examples: List[ExampleTestCase] = field(default_factory=list)
    hints: List[str] = field(default_factory=list)
    raw_example_testcases: Optional[str] = None

    def get_summary(self, max_length: int = 400) -> str:
        """Returns a concise summary of the problem statement."""
        # Grab the first 1-2 paragraphs of statement
        paragraphs = [p.strip() for p in self.statement_text.split("\n\n") if p.strip()]
        if not paragraphs:
            return self.statement_text[:max_length]
        
        summary = paragraphs[0]
        if len(paragraphs) > 1 and len(summary) < 200:
            summary += "\n\n" + paragraphs[1]

        if len(summary) > max_length:
            summary = summary[:max_length].rstrip() + "..."
        return summary


def clean_html_to_text(html_content: str) -> str:
    """
    Cleans LeetCode HTML description into human-readable plain text / markdown.
    Preserves lists, code formatting, and paragraph line breaks.
    """
    if not html_content:
        return ""

    soup = BeautifulSoup(html_content, "html.parser")

    # Replace <pre> blocks with clear newline boundaries
    for pre in soup.find_all("pre"):
        pre_text = pre.get_text()
        pre.replace_with(f"\n```\n{pre_text.strip()}\n```\n")

    # Replace <code> blocks with inline markdown backticks
    for code in soup.find_all("code"):
        code_text = code.get_text()
        code.replace_with(f"`{code_text}`")

    # Replace <li> with bullet markers
    for li in soup.find_all("li"):
        li.insert_before("\n• ")

    text = soup.get_text()

    # Normalize excessive newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def parse_examples_from_html(html_content: str) -> List[ExampleTestCase]:
    """
    Extracts structured input/output example test cases from HTML <pre> elements or text.
    """
    if not html_content:
        return []

    examples: List[ExampleTestCase] = []
    soup = BeautifulSoup(html_content, "html.parser")

    # Check <pre> tags which LeetCode typically uses for Example blocks
    for pre in soup.find_all("pre"):
        pre_text = pre.get_text().strip()
        
        input_match = re.search(r"Input:\s*(.+?)(?=\n\s*Output:|$)", pre_text, re.DOTALL | re.IGNORECASE)
        output_match = re.search(r"Output:\s*(.+?)(?=\n\s*Explanation:|$)", pre_text, re.DOTALL | re.IGNORECASE)
        exp_match = re.search(r"Explanation:\s*(.+)$", pre_text, re.DOTALL | re.IGNORECASE)

        if input_match and output_match:
            inp_str = input_match.group(1).strip()
            out_str = output_match.group(1).strip()
            exp_str = exp_match.group(1).strip() if exp_match else None
            examples.append(ExampleTestCase(
                input_raw=inp_str,
                output_raw=out_str,
                explanation=exp_str
            ))

    # Fallback to regex across the full cleaned text if no <pre> tags matched
    if not examples:
        text = soup.get_text()
        pattern = r"Input:\s*(.+?)\n\s*Output:\s*(.+?)(?=\n\s*(?:Explanation:|Example|\Z))"
        matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
        for inp, out in matches:
            examples.append(ExampleTestCase(
                input_raw=inp.strip(),
                output_raw=out.strip()
            ))

    return examples


def fetch_daily_problem(timeout: int = 15) -> LeetCodeProblem:
    """
    Fetches the active Problem of the Day (POTD) from LeetCode GraphQL API.
    Raises RuntimeError if LeetCode is unreachable or returns malformed response.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com/",
    }

    payload = {"query": DAILY_QUESTION_QUERY}

    logger.info("Fetching LeetCode Problem of the Day from %s", LEETCODE_GRAPHQL_URL)
    try:
        response = requests.post(
            LEETCODE_GRAPHQL_URL,
            json=payload,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as err:
        logger.error("Network error connecting to LeetCode: %s", err)
        raise RuntimeError(f"Failed to connect to LeetCode API: {err}") from err
    except ValueError as err:
        logger.error("Failed to parse JSON response from LeetCode: %s", err)
        raise RuntimeError("Invalid JSON received from LeetCode") from err

    daily_challenge = data.get("data", {}).get("activeDailyCodingChallengeQuestion")
    if not daily_challenge or not daily_challenge.get("question"):
        error_msg = data.get("errors", [{}])[0].get("message", "No active daily question found")
        logger.error("LeetCode GraphQL error: %s", error_msg)
        raise RuntimeError(f"LeetCode daily challenge unavailable: {error_msg}")

    q_data = daily_challenge["question"]
    date_str = daily_challenge.get("date", "")
    rel_link = daily_challenge.get("link", "")
    full_link = f"https://leetcode.com{rel_link}" if rel_link.startswith("/") else rel_link

    # Check for paid-only problems
    is_paid_only = bool(q_data.get("isPaidOnly"))
    if is_paid_only:
        logger.warning("Today's problem (%s) is a Premium-only problem.", q_data.get("title"))

    html_content = q_data.get("content") or ""
    clean_statement = clean_html_to_text(html_content)
    examples = parse_examples_from_html(html_content)

    # Extract Python 3 starter snippet
    code_snippets = q_data.get("codeSnippets") or []
    starter_code = ""
    for snippet in code_snippets:
        if snippet.get("langSlug") == "python3":
            starter_code = snippet.get("code", "")
            break
        elif snippet.get("langSlug") == "python" and not starter_code:
            starter_code = snippet.get("code", "")

    # Default fallback starter code if not provided
    if not starter_code:
        starter_code = "class Solution:\n    def solve(self):\n        pass\n"

    problem = LeetCodeProblem(
        id=str(q_data.get("questionFrontendId") or q_data.get("questionId") or "0"),
        title=q_data.get("title", "Unknown Title"),
        title_slug=q_data.get("titleSlug", ""),
        difficulty=q_data.get("difficulty", "Medium"),
        link=full_link,
        date=date_str,
        is_paid_only=is_paid_only,
        statement_text=clean_statement,
        html_content=html_content,
        starter_code=starter_code,
        examples=examples,
        hints=q_data.get("hints") or [],
        raw_example_testcases=q_data.get("exampleTestcases"),
    )

    logger.info("Successfully fetched POTD: %s (%s) - %s examples extracted",
                problem.title, problem.difficulty, len(problem.examples))
    return problem
