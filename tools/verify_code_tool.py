#!/usr/bin/env python3
"""
Verify Code Tool — Deterministic verification for Hermes-Ratchet.

Runs Python code in Hermes's sandbox with optional test harness.
Returns PASS/FAIL with detailed output for the Reflector to analyze.

Usage:
    verify_code(code="def add(a, b): return a + b", tests=[...])
    verify_code(code="print('hello world')")
"""

import json
import asyncio
import sys
from typing import List, Optional, Dict, Any

from tools.registry import registry


VERIFY_CODE_SCHEMA = {
    "name": "verify_code",
    "description": """Run Python code in a sandboxed environment and optionally verify it against test cases.

Use this to:
- Execute code and capture output for verification by the deterministic execution loop
- Run code with a test harness to get pass/fail per test case
- Verify that generated code produces expected output

Returns a structured result with status (pass/fail/error), output, error, and per-test results.

For simple execution without tests: pass an empty or omitted `tests` array.
For test-driven verification: pass test cases with name, input, and expected output.""",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute.",
            },
            "tests": {
                "type": "array",
                "description": "Optional test cases to run against the code. Each test has name, input_data, and expected.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Human-readable test name."},
                        "input_data": {"description": "Input argument(s) to pass to the function under test."},
                        "expected": {"description": "Expected return value."},
                        "code": {"type": "string", "description": "Optional custom test code. Takes precedence over input_data/expected."},
                    },
                    "required": ["name"],
                },
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 30, max: 120).",
                "default": 30,
            },
            "language": {
                "type": "string",
                "description": "Language (currently only 'python' is supported).",
                "default": "python",
            },
        },
        "required": ["code"],
    },
}


def _normalize_test(t: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a test dict to always have name, with optional input_data/expected/code."""
    return {
        "name": t.get("name", "unnamed_test"),
        "input_data": t.get("input_data"),
        "expected": t.get("expected"),
        "code": t.get("code"),
    }


async def _verify_code_async(
    code: str,
    tests: List[Dict[str, Any]] = None,
    timeout: int = 30,
    language: str = "python",
) -> str:
    """
    Async implementation of verify_code.

    Delegates to the HermesVerifier for sandboxed execution + test harness.
    """
    try:
        # Import here to avoid circular imports
        from ratchet.deterministic.verifier import HermesVerifier, TestCase

        verifier = HermesVerifier()

        normalized_tests = [_normalize_test(t) for t in (tests or [])]

        if normalized_tests:
            test_cases = [
                TestCase(
                    name=t["name"],
                    input_data=t.get("input_data"),
                    expected=t.get("expected"),
                    code=t.get("code"),
                )
                for t in normalized_tests
            ]
            result = await verifier.verify_code_async(
                code=code,
                tests=test_cases,
                language=language,
                timeout=min(timeout, 120),
            )
        else:
            result = await verifier.execute_async(
                code=code,
                language=language,
                timeout=min(timeout, 120),
            )

        return json.dumps(result.to_dict(), ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "status": "error",
            "output": "",
            "error": str(e),
            "exit_code": 1,
            "duration_ms": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests": [],
        })


def _verify_code(args: Dict[str, Any], **kwargs) -> str:
    """Sync wrapper for verify_code."""
    code = args.get("code", "")
    tests = args.get("tests", [])
    timeout = int(args.get("timeout", 30))
    language = args.get("language", "python")

    if not code or not code.strip():
        return json.dumps({
            "status": "error",
            "error": "No code provided.",
            "output": "",
            "exit_code": 1,
        })

    return asyncio.run(_verify_code_async(code, tests, timeout, language))


# --- Registry ---
registry.register(
    name="verify_code",
    toolset="code_execution",
    schema=VERIFY_CODE_SCHEMA,
    handler=_verify_code,
    check_fn=lambda: True,  # Always available
    emoji="✅",
)
