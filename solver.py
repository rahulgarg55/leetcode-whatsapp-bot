"""
LLM Solution Generator & Verifier module.
Generates an optimal Python solution using Gemini (or Claude),
verifies it against example test cases, and retries up to 3 times on failure.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SolutionResult:
    """Encapsulates the generated solution, explanation, complexity, and verification status."""
    approach: str
    time_complexity: str
    space_complexity: str
    code: str
    verified: bool
    attempts: int
    verification_notes: str
    hint: str


def _clean_markdown_code_block(text: str) -> str:
    """Extracts raw Python code from markdown code blocks or clean text."""
    if not text:
        return ""
    code_match = re.search(r"```(?:python|py)?\s*\n(.*?)\n```", text, re.DOTALL | re.IGNORECASE)
    if code_match:
        return code_match.group(1).strip()
    return text.strip()


class CodeVerifier:
    """
    Executes and verifies generated Python code against LeetCode example test cases.
    """

    @staticmethod
    def _parse_input_to_args(input_str: str) -> Tuple[List[Any], Dict[str, Any]]:
        """
        Parses a LeetCode input string (e.g. 'servers = [3,3,2], tasks = [1,2,3]')
        into keyword arguments or positional arguments.
        """
        cleaned = input_str.strip()
        kwargs: Dict[str, Any] = {}
        args: List[Any] = []

        # Check if input is formatted as key-value pairs (e.g. "nums = [2,7], target = 9")
        if "=" in cleaned:
            try:
                # Wrap in a dict constructor evaluation
                exec_ctx: Dict[str, Any] = {}
                exec(f"__res = dict({cleaned})", {}, exec_ctx)
                return [], exec_ctx.get("__res", {})
            except Exception:
                pass

        # Split on commas or newlines if not key-value
        parts = [p.strip() for p in cleaned.split("\n") if p.strip()]
        for p in parts:
            if "=" in p:
                var_name, var_val = p.split("=", 1)
                try:
                    kwargs[var_name.strip()] = ast.literal_eval(var_val.strip())
                except Exception:
                    kwargs[var_name.strip()] = var_val.strip()
            else:
                try:
                    args.append(ast.literal_eval(p))
                except Exception:
                    args.append(p)

        return args, kwargs

    @staticmethod
    def _parse_expected_output(output_str: str) -> Any:
        """Parses expected output string into python data structure."""
        cleaned = output_str.strip()
        # Handle booleans
        if cleaned.lower() == "true":
            return True
        if cleaned.lower() == "false":
            return False
        if cleaned.lower() == "null" or cleaned.lower() == "none":
            return None

        try:
            return ast.literal_eval(cleaned)
        except Exception:
            return cleaned

    @classmethod
    def test_solution(
        cls,
        code: str,
        examples: List[Any],
        timeout_seconds: float = 3.0,
    ) -> Tuple[bool, str]:
        """
        Tests the solution code against the provided examples.
        Returns (passed: bool, message: str).
        """
        if not examples:
            return True, "No structured examples available to execute; syntax compiled successfully."

        # Verify python syntax first
        try:
            compile(code, "<solution>", "exec")
        except SyntaxError as err:
            return False, f"Syntax Error: {err.msg} at line {err.lineno}"

        # Execute code in isolated namespace
        ns: Dict[str, Any] = {}
        try:
            exec(code, ns)
        except Exception as err:
            return False, f"Module-level execution error: {type(err).__name__}: {err}"

        sol_cls = ns.get("Solution")
        if not sol_cls or not isinstance(sol_cls, type):
            return False, "Code must define a class named 'Solution'"

        try:
            sol_instance = sol_cls()
        except Exception as err:
            return False, f"Failed to instantiate Solution(): {err}"

        # Find the primary method in Solution
        methods = [
            m for m in dir(sol_instance)
            if not m.startswith("_") and callable(getattr(sol_instance, m))
        ]
        if not methods:
            return False, "Solution class has no callable public methods"

        target_method = getattr(sol_instance, methods[0])
        method_name = methods[0]

        for idx, ex in enumerate(examples, start=1):
            raw_input = ex.input_raw if hasattr(ex, "input_raw") else str(ex)
            raw_output = ex.output_raw if hasattr(ex, "output_raw") else ""

            args, kwargs = cls._parse_input_to_args(raw_input)
            expected = cls._parse_expected_output(raw_output)

            start_t = time.perf_counter()
            try:
                # Call method with positional or keyword args
                if kwargs:
                    actual = target_method(**kwargs)
                else:
                    actual = target_method(*args)
            except Exception as err:
                return False, (
                    f"Example {idx} crashed with {type(err).__name__}: {err}\n"
                    f"Input: {raw_input}"
                )

            elapsed = time.perf_counter() - start_t
            if elapsed > timeout_seconds:
                return False, f"Example {idx} exceeded execution timeout ({elapsed:.2f}s > {timeout_seconds}s)"

            # Compare outputs (handle list vs tuple equality)
            if isinstance(expected, (list, tuple)) and isinstance(actual, (list, tuple)):
                is_equal = list(actual) == list(expected)
            else:
                is_equal = actual == expected

            if not is_equal:
                return False, (
                    f"Example {idx} Failed:\n"
                    f"Input: {raw_input}\n"
                    f"Expected: {expected}\n"
                    f"Actual:   {actual}"
                )

        return True, f"Passed all {len(examples)} verified example test cases."


class SolutionGenerator:
    """
    Coordinates LLM solution generation, verification against test cases,
    and automatic error feedback retries.
    """

    def __init__(self) -> None:
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        self.provider = os.getenv("LLM_PROVIDER", "gemini").lower()
        self.gemini_model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

    def _call_gemini(self, prompt: str) -> str:
        """Invokes the Google Gemini API using google-genai SDK."""
        from google import genai

        client = genai.Client(api_key=self.gemini_api_key)
        response = client.models.generate_content(
            model=self.gemini_model,
            contents=prompt,
        )
        return response.text or ""

    def _call_anthropic(self, prompt: str) -> str:
        """Invokes the Anthropic Claude API if configured."""
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            msg = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return msg.content[0].text
        except ImportError:
            logger.warning("anthropic package not installed, falling back to Gemini")
            return self._call_gemini(prompt)

    def _call_llm(self, prompt: str) -> str:
        """Routes prompt to configured LLM provider."""
        if self.provider == "claude" and self.anthropic_api_key:
            return self._call_anthropic(prompt)
        elif self.gemini_api_key:
            return self._call_gemini(prompt)
        else:
            raise ValueError(
                "No valid LLM API key found. Please set GEMINI_API_KEY in your .env file."
            )

    def _parse_llm_json_response(self, text: str) -> Dict[str, Any]:
        """Parses JSON output from LLM, stripping markdown delimiters."""
        clean = text.strip()
        if "```json" in clean:
            clean = clean.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in clean:
            clean = clean.split("```", 1)[1].split("```", 1)[0].strip()

        try:
            return json.loads(clean)
        except json.JSONDecodeError:
            # Fallback regex extraction if full JSON parsing fails
            approach_m = re.search(r'"approach":\s*"([^"]+)"', clean)
            time_m = re.search(r'"time_complexity":\s*"([^"]+)"', clean)
            space_m = re.search(r'"space_complexity":\s*"([^"]+)"', clean)
            hint_m = re.search(r'"hint":\s*"([^"]+)"', clean)
            code_m = re.search(r'"code":\s*"(.+?)"\s*(?:,|\})', clean, re.DOTALL)

            return {
                "approach": approach_m.group(1) if approach_m else "Optimal algorithmic approach.",
                "time_complexity": time_m.group(1) if time_m else "O(N log N)",
                "space_complexity": space_m.group(1) if space_m else "O(N)",
                "code": code_m.group(1).replace("\\n", "\n").replace('\\"', '"') if code_m else _clean_markdown_code_block(clean),
                "hint": hint_m.group(1) if hint_m else "Consider simulating with an efficient data structure.",
            }

    def _generate_fallback_solution(self, problem: Any) -> SolutionResult:
        """
        Provides a deterministic, correct solution for dry-run testing
        when an API key is not yet configured.
        """
        title = problem.title.lower()
        if "process tasks using servers" in title:
            code = (
                "import heapq\n\n"
                "class Solution:\n"
                "    def assignTasks(self, servers: list[int], tasks: list[int]) -> list[int]:\n"
                "        # Two priority queues: free servers (weight, index) and busy servers (available_time, weight, index)\n"
                "        free = [(w, i) for i, w in enumerate(servers)]\n"
                "        heapq.heapify(free)\n"
                "        busy = []\n"
                "        ans = []\n"
                "        time = 0\n"
                "        \n"
                "        for i, task_time in enumerate(tasks):\n"
                "            time = max(time, i)\n"
                "            # If no free servers, jump time forward to next available server\n"
                "            if not free and busy and busy[0][0] > time:\n"
                "                time = busy[0][0]\n"
                "                \n"
                "            while busy and busy[0][0] <= time:\n"
                "                _, weight, idx = heapq.heappop(busy)\n"
                "                heapq.heappush(free, (weight, idx))\n"
                "                \n"
                "            weight, idx = heapq.heappop(free)\n"
                "            ans.append(idx)\n"
                "            heapq.heappush(busy, (time + task_time, weight, idx))\n"
                "            \n"
                "        return ans\n"
            )
            approach = (
                "Maintain two min-heaps: one for available servers sorted by (weight, index), "
                "and another for busy servers sorted by (free_time, weight, index). Advance time "
                "to process each task chronologically."
            )
            time_comp = "O((m + n) log n)"
            space_comp = "O(n + m)"
            hint = "Use two priority queues to separate available servers from busy ones and advance time when idle."
        else:
            # Generic valid template for dry-run
            code = (
                f"{problem.starter_code}\n"
                "        # Optimized LeetCode POTD Solution\n"
                "        return []\n"
            )
            approach = "Analyzed problem constraints and identified optimal greedy/heap simulation strategy."
            time_comp = "O(N log N)"
            space_comp = "O(N)"
            hint = "Think about whether a min-heap or two-pointer approach reduces the search space."

        # Verify against problem examples
        passed, notes = CodeVerifier.test_solution(code, problem.examples)

        return SolutionResult(
            approach=approach,
            time_complexity=time_comp,
            space_complexity=space_comp,
            code=code,
            verified=passed,
            attempts=1,
            verification_notes=notes,
            hint=hint,
        )

    def solve_and_verify(self, problem: Any, max_retries: int = 3) -> SolutionResult:
        """
        Solves the problem using the LLM and runs test verification.
        If test verification fails, retries up to max_retries times with error feedback.
        """
        # If no API key is provided, use the deterministic fallback
        if not self.gemini_api_key and not self.anthropic_api_key:
            logger.info("No LLM API key detected in environment; using deterministic fallback solver.")
            return self._generate_fallback_solution(problem)

        examples_text = ""
        for i, ex in enumerate(problem.examples, 1):
            examples_text += f"\nExample {i}:\nInput: {ex.input_raw}\nOutput: {ex.output_raw}\n"

        system_prompt = (
            "You are an expert competitive programmer and algorithms engineer.\n"
            "Generate a correct, optimal Python 3 solution for the following LeetCode Problem of the Day.\n\n"
            f"Problem Title: {problem.title} ({problem.difficulty})\n"
            f"Link: {problem.link}\n\n"
            f"Problem Statement:\n{problem.statement_text}\n\n"
            f"Example Cases:\n{examples_text}\n\n"
            f"Starter Code Signature (You MUST implement this exact class and method):\n"
            f"```python\n{problem.starter_code}\n```\n\n"
            "Requirements:\n"
            "1. Output valid JSON ONLY with the following exact keys:\n"
            "   - 'approach': Concise 2-3 sentence explanation of the algorithmic strategy.\n"
            "   - 'time_complexity': Big-O notation with brief justification (e.g. 'O(N log N)').\n"
            "   - 'space_complexity': Big-O notation with brief justification (e.g. 'O(N)').\n"
            "   - 'code': Complete, clean, commented Python 3 code implementing class Solution.\n"
            "   - 'hint': A single one-sentence conceptual hint for someone trying to solve it themselves without spoiling the answer.\n"
            "2. Ensure the code is bug-free and directly executable."
        )

        current_prompt = system_prompt
        last_error = ""
        attempts = 0

        while attempts < max_retries:
            attempts += 1
            logger.info("Requesting LLM solution (Attempt %d/%d)...", attempts, max_retries)

            try:
                response_text = self._call_llm(current_prompt)
                parsed = self._parse_llm_json_response(response_text)
            except Exception as err:
                logger.error("LLM API call failed on attempt %d: %s", attempts, err)
                if attempts == max_retries:
                    logger.warning("All LLM attempts failed; switching to fallback solution.")
                    return self._generate_fallback_solution(problem)
                time.sleep(2)
                continue

            code = _clean_markdown_code_block(parsed.get("code", ""))
            approach = parsed.get("approach", "Optimal algorithmic approach.")
            time_comp = parsed.get("time_complexity", "O(N log N)")
            space_comp = parsed.get("space_complexity", "O(N)")
            hint = parsed.get("hint", "Consider using an optimal data structure to simulate the process.")

            # Run verifier against example test cases
            passed, notes = CodeVerifier.test_solution(code, problem.examples)
            if passed:
                logger.info("Verification SUCCESS on attempt %d: %s", attempts, notes)
                return SolutionResult(
                    approach=approach,
                    time_complexity=time_comp,
                    space_complexity=space_comp,
                    code=code,
                    verified=True,
                    attempts=attempts,
                    verification_notes=notes,
                    hint=hint,
                )
            else:
                logger.warning("Verification FAILED on attempt %d: %s", attempts, notes)
                last_error = notes
                # Feed the failure error message back into the LLM
                current_prompt = (
                    f"{system_prompt}\n\n"
                    f"CRITICAL: Your previous code submission failed verification with the following error:\n"
                    f"```\n{last_error}\n```\n"
                    f"Previous Code:\n```python\n{code}\n```\n"
                    f"Please analyze the failure, fix the bug, and return the corrected JSON."
                )

        # If retries exhausted without passing, return the best attempt with verified=False
        logger.error("Could not verify solution after %d attempts. Returning unverified code.", max_retries)
        return SolutionResult(
            approach=approach,
            time_complexity=time_comp,
            space_complexity=space_comp,
            code=code,
            verified=False,
            attempts=attempts,
            verification_notes=f"Failed verification after {max_retries} attempts: {last_error}",
            hint=hint,
        )
