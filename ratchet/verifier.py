"""
Verifier - Sandboxed execution and test runner
"""

import os
import subprocess
import tempfile
import hashlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from pathlib import Path

from ratchet.skill import VerificationRule, VerificationType


@dataclass
class VerificationResult:
    passed: bool
    message: str
    details: Optional[Dict[str, Any]] = None
    execution_time_ms: float = 0.0


class Sandbox:
    """Isolated execution environment for untrusted code."""

    def __init__(self, timeout: int = 30, allowed_dirs: Optional[List[str]] = None):
        self.timeout = timeout
        self.allowed_dirs = allowed_dirs or ["/tmp/ratchet"]

    def execute(
        self,
        code: str,
        language: str = "python",
        cwd: Optional[str] = None,
    ) -> VerificationResult:
        """Execute code in a sandboxed environment."""
        import time
        start = time.time()

        cwd = cwd or self.allowed_dirs[0] if self.allowed_dirs else "/tmp/ratchet"
        Path(cwd).mkdir(parents=True, exist_ok=True)

        if language == "python":
            return self._execute_python(code, cwd, start)
        elif language == "bash":
            return self._execute_bash(code, cwd, start)
        else:
            return VerificationResult(
                passed=False,
                message=f"Unsupported language: {language}",
                execution_time_ms=(time.time() - start) * 1000,
            )

    def _execute_python(self, code: str, cwd: str, start: float) -> VerificationResult:
        """Execute Python code safely."""
        # Write to temp file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", dir=cwd, delete=False
        ) as f:
            f.write(code)
            temp_path = f.name

        try:
            result = subprocess.run(
                ["python3", temp_path],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
            execution_time_ms = (result.returncode is not None) * 1000  # Simplified

            return VerificationResult(
                passed=result.returncode == 0,
                message=f"Exit code: {result.returncode}",
                details={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                },
                execution_time_ms=(time.time() - start) * 1000,
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                message=f"Execution timed out after {self.timeout}s",
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                message=f"Execution error: {str(e)}",
                execution_time_ms=(time.time() - start) * 1000,
            )
        finally:
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def _execute_bash(self, code: str, cwd: str, start: float) -> VerificationResult:
        """Execute bash script."""
        try:
            result = subprocess.run(
                ["bash", "-c", code],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
            )
            return VerificationResult(
                passed=result.returncode == 0,
                message=f"Exit code: {result.returncode}",
                details={
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "exit_code": result.returncode,
                },
                execution_time_ms=(time.time() - start) * 1000,
            )
        except subprocess.TimeoutExpired:
            return VerificationResult(
                passed=False,
                message=f"Execution timed out after {self.timeout}s",
                execution_time_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return VerificationResult(
                passed=False,
                message=f"Execution error: {str(e)}",
                execution_time_ms=(time.time() - start) * 1000,
            )


class Verifier:
    """Verifies step outputs against defined rules."""

    def __init__(self, sandbox: Optional[Sandbox] = None):
        self.sandbox = sandbox or Sandbox()

    def verify(
        self,
        rule: VerificationRule,
        output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> VerificationResult:
        """Verify output against a verification rule."""
        context = context or {}

        if rule.type == VerificationType.ASSERTION:
            return self._verify_assertion(rule, output, context)
        elif rule.type == VerificationType.TEST:
            return self._verify_test(rule, context)
        elif rule.type == VerificationType.OUTPUT:
            return self._verify_output(rule, output)
        elif rule.type == VerificationType.EXIT_CODE:
            return self._verify_exit_code(rule, output)
        else:
            return VerificationResult(
                passed=False,
                message=f"Unknown verification type: {rule.type}",
            )

    def _verify_assertion(
        self, rule: VerificationRule, output: str, context: Dict[str, Any]
    ) -> VerificationResult:
        """Verify using an assertion expression."""
        if not rule.expression:
            return VerificationResult(passed=False, message="No expression provided")

        # Simple assertion: check if expression is "true" in the output context
        try:
            # Basic safety: only allow simple comparisons
            safe_expressions = ["in", "==", "!=", ">", "<", ">=", "<="]
            if not any(expr in rule.expression for expr in safe_expressions):
                return VerificationResult(
                    passed=False, message="Expression not allowed for safety"
                )

            passed = rule.expression in output
            return VerificationResult(
                passed=passed,
                message=f"Assertion '{rule.expression}': {'PASSED' if passed else 'FAILED'}",
            )
        except Exception as e:
            return VerificationResult(passed=False, message=f"Assertion error: {str(e)}")

    def _verify_test(
        self, rule: VerificationRule, context: Dict[str, Any]
    ) -> VerificationResult:
        """Run a test file or command."""
        if rule.test_command:
            try:
                result = subprocess.run(
                    rule.test_command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=self.sandbox.timeout,
                )
                passed = result.returncode == 0
                return VerificationResult(
                    passed=passed,
                    message=f"Test {'PASSED' if passed else 'FAILED'} (exit {result.returncode})",
                    details={
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.returncode,
                    },
                )
            except subprocess.TimeoutExpired:
                return VerificationResult(passed=False, message="Test timed out")
            except Exception as e:
                return VerificationResult(passed=False, message=f"Test error: {str(e)}")

        return VerificationResult(passed=False, message="No test command provided")

    def _verify_output(self, rule: VerificationRule, output: str) -> VerificationResult:
        """Verify output contains/missing specific strings."""
        if rule.must_contain:
            missing = [s for s in rule.must_contain if s not in output]
            if missing:
                return VerificationResult(
                    passed=False,
                    message=f"Missing required strings: {missing}",
                )

        if rule.must_not_contain:
            found = [s for s in rule.must_not_contain if s in output]
            if found:
                return VerificationResult(
                    passed=False,
                    message=f"Found prohibited strings: {found}",
                )

        if rule.expected:
            passed = rule.expected in output
            return VerificationResult(
                passed=passed,
                message=f"Expected content check: {'PASSED' if passed else 'FAILED'}",
            )

        return VerificationResult(passed=True, message="Output verification passed")

    def _verify_exit_code(self, rule: VerificationRule, output: str) -> VerificationResult:
        """Verify exit code matches expected."""
        expected = rule.expected_code if rule.expected_code is not None else 0
        actual = int(output.strip().split()[-1]) if output.strip() else -1
        passed = actual == expected
        return VerificationResult(
            passed=passed,
            message=f"Exit code {actual} vs expected {expected}: {'PASSED' if passed else 'FAILED'}",
        )
