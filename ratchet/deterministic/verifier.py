"""
Ratchet-compatible Verifier — sandboxes code execution using Ratchet's code_execution_tool.
"""

import json
import tempfile
import os
import asyncio
import time
from typing import Optional, List
from dataclasses import dataclass, field
from enum import Enum


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class TestCase:
    """Matches Ratchet's TestCase for compatibility."""
    name: str
    input_data: any = None
    expected: any = None
    code: Optional[str] = None


@dataclass
class ExecutionResult:
    """Matches Ratchet's ExecutionResult for compatibility."""
    status: VerificationStatus
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    duration_ms: float = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value if hasattr(self.status, "value") else self.status,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests": self.tests,
        }


class RatchetVerifier:
    """
    Sandboxed code execution using Ratchet's code_execution_tool infrastructure.

    - execute(): Run code and return the raw output + exit code
    - verify_code(): Run code with a test harness and return PASS/FAIL per test

    Uses the same sandbox as Ratchet's execute_code tool (UDS RPC, restricted tools,
    no credential access, timeout + output caps).
    """

    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = sandbox_dir or tempfile.mkdtemp(prefix="ratchet_hermes_")
        os.makedirs(self.sandbox_dir, exist_ok=True)

    async def execute_async(
        self,
        code: str,
        language: str = "python",
        timeout: int = 30,
    ) -> ExecutionResult:
        """
        Execute code in Ratchet's sandbox and return the raw result.
        """
        from tools.code_execution_tool import execute_code

        start = time.time()
        try:
            raw = execute_code(code=code, task_id=None, enabled_tools=None)
            result = json.loads(raw)
            duration_ms = (time.time() - start) * 1000

            status_str = result.get("status", "error")
            if status_str == "success":
                status = VerificationStatus.PASS
            elif status_str in ("error", "timeout", "interrupted"):
                status = VerificationStatus.ERROR
            else:
                status = VerificationStatus.FAIL

            return ExecutionResult(
                status=status,
                output=result.get("output", ""),
                error=result.get("error"),
                exit_code=0 if status == VerificationStatus.PASS else 1,
                duration_ms=duration_ms,
            )

        except Exception as e:
            return ExecutionResult(
                status=VerificationStatus.ERROR,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    def execute(self, code: str, language: str = "python", timeout: int = 30) -> ExecutionResult:
        """Sync wrapper for execute_async."""
        return asyncio.run(self.execute_async(code, language, timeout))

    async def verify_code_async(
        self,
        code: str,
        tests: List[TestCase],
        language: str = "python",
        timeout: int = 60,
    ) -> ExecutionResult:
        """
        Execute code wrapped in a test harness.

        Generates a test harness from TestCase definitions, runs it in the sandbox,
        and returns aggregated PASS/FAIL per test.
        """
        start = time.time()
        harness = self._generate_harness(code, tests, language)
        result = await self.execute_async(harness, language, timeout)
        duration_ms = (time.time() - start) * 1000

        if result.error and "timeout" in result.error.lower():
            result.status = VerificationStatus.ERROR
            return result

        # Parse test results from output
        try:
            # Each test prints a JSON line
            test_results = []
            for line in result.output.strip().split("\n"):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    test_results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

            passed = sum(1 for r in test_results if r.get("passed", False))
            failed = len(test_results) - passed

            return ExecutionResult(
                status=VerificationStatus.PASS if passed == len(tests) else VerificationStatus.FAIL,
                output=result.output,
                error=result.error,
                exit_code=result.exit_code,
                duration_ms=duration_ms,
                tests_passed=passed,
                tests_failed=failed,
                tests=test_results,
            )
        except Exception as e:
            return ExecutionResult(
                status=VerificationStatus.ERROR,
                error=f"Failed to parse test results: {e}",
                duration_ms=duration_ms,
            )

    def verify_code(
        self,
        code: str,
        tests: List[TestCase],
        language: str = "python",
        timeout: int = 60,
    ) -> ExecutionResult:
        """Sync wrapper for verify_code_async."""
        return asyncio.run(self.verify_code_async(code, tests, language, timeout))

    def _generate_harness(self, code: str, tests: List[TestCase], language: str) -> str:
        """
        Generate a test harness for the given code and test cases.

        For Python: wraps each test as an assertion and prints JSON results.
        The function under test is inferred from the first 'def ' in the code.
        """
        if language != "python":
            return f"{code}\nprint('tests')"

        test_blocks = []
        for i, t in enumerate(tests):
            inp = repr(t.input_data)
            exp = repr(t.expected)
            # Infer function name from code
            fn_name = self._infer_fn_name(code)

            if t.code:
                # Custom test code provided
                test_blocks.append(f"try:\n    exec({repr(t.code)})\n    ok = True\nexcept Exception as e:\n    ok = False\nprint(json.dumps({{'name': {repr(t.name)}, 'passed': ok}}))")
            else:
                test_blocks.append(
                    f"try:\n"
                    f"    r = {fn_name}({inp})\n"
                    f"    ok = (r == {exp})\n"
                    f"except Exception as e:\n"
                    f"    ok = False\n"
                    f"print(json.dumps({{'name': {repr(t.name)}, 'passed': ok, 'expected': {exp}, 'actual': str(r) if 'r' in dir() else str(e)}}))"
                )

        return "import json\n" + code + "\n" + "\n".join(test_blocks)

    def _infer_fn_name(self, code: str) -> str:
        """Infer the function being tested from code."""
        import re
        match = re.search(r"def\s+(\w+)\s*\(", code)
        if match:
            return match.group(1)
        return "unknown"
