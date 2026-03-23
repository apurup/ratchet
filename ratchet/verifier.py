"""
Verifier - Sandboxed code execution and test runner
"""

import subprocess
import tempfile
import os
import json
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum


class VerificationStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIP = "skip"


@dataclass
class TestCase:
    name: str
    input_data: Any = None
    expected: Any = None
    code: Optional[str] = None


@dataclass
class ExecutionResult:
    status: VerificationStatus
    output: str = ""
    error: Optional[str] = None
    exit_code: int = 0
    duration_ms: float = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value if hasattr(self.status, 'value') else self.status,
            "output": self.output,
            "error": self.error,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "tests": self.tests,
        }


class Verifier:
    """Sandboxed code execution and verification engine."""
    def __init__(self, sandbox_dir: Optional[str] = None):
        self.sandbox_dir = sandbox_dir or tempfile.mkdtemp(prefix="ratchet_")
        os.makedirs(self.sandbox_dir, exist_ok=True)

    async def execute_async(self, code: str, language: str = "python", timeout: int = 30) -> ExecutionResult:
        import time
        start = time.time()
        ext = ".py" if language == "python" else ".js" if language in ("javascript", "js") else ".txt"
        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, dir=self.sandbox_dir, delete=False) as f:
            f.write(code)
            filepath = f.name
        try:
            cmd = ["python", filepath] if language == "python" else ["node", filepath]
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, cwd=self.sandbox_dir,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecutionResult(status=VerificationStatus.ERROR, error=f"Timeout after {timeout}s", duration_ms=(time.time()-start)*1000)
            duration_ms = (time.time() - start) * 1000
            return ExecutionResult(
                status=VerificationStatus.PASS if proc.returncode == 0 else VerificationStatus.FAIL,
                output=stdout.decode() if stdout else "",
                error=stderr.decode() if stderr else None,
                exit_code=proc.returncode,
                duration_ms=duration_ms,
            )
        except Exception as e:
            return ExecutionResult(status=VerificationStatus.ERROR, error=str(e), duration_ms=(time.time()-start)*1000)
        finally:
            try: os.unlink(filepath)
            except: pass

    def execute(self, code: str, language: str = "python", timeout: int = 30) -> ExecutionResult:
        return asyncio.run(self.execute_async(code, language, timeout))

    async def verify_code_async(self, code: str, tests: List[TestCase], language: str = "python", timeout: int = 30) -> ExecutionResult:
        import time
        start = time.time()
        harness = self._generate_harness(code, tests, language)
        ext = ".py" if language == "python" else ".js"
        with tempfile.NamedTemporaryFile(mode="w", suffix=ext, dir=self.sandbox_dir, delete=False) as f:
            f.write(harness)
            filepath = f.name
        try:
            cmd = ["python", filepath] if language == "python" else ["node", filepath]
            proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return ExecutionResult(status=VerificationStatus.ERROR, error="Timeout", duration_ms=(time.time()-start)*1000)
            output = stdout.decode()
            results = []
            try: results = json.loads(output)
            except: results = [{"name": "parse", "passed": False, "output": output}]
            passed = sum(1 for r in results if r.get("passed", False))
            return ExecutionResult(
                status=VerificationStatus.PASS if passed == len(tests) else VerificationStatus.FAIL,
                output=output, exit_code=proc.returncode, duration_ms=(time.time()-start)*1000,
                tests_passed=passed, tests_failed=len(tests)-passed, tests=results,
            )
        except Exception as e:
            return ExecutionResult(status=VerificationStatus.ERROR, error=str(e), duration_ms=(time.time()-start)*1000)
        finally:
            try: os.unlink(filepath)
            except: pass

    def verify_code(self, code: str, tests: List[TestCase], language: str = "python", timeout: int = 30) -> ExecutionResult:
        return asyncio.run(self.verify_code_async(code, tests, language, timeout))

    def _generate_harness(self, code: str, tests: List[TestCase], language: str) -> str:
        if language == "python":
            test_blocks = []
            for i, t in enumerate(tests):
                inp = repr(t.input_data)
                exp = repr(t.expected)
                fn = code.split("def ")[1].split("(")[0] if "def " in code else "unknown"
                test_blocks.append(f"try:\n    r={fn}({inp})\n    ok=r=={exp}\nexcept Exception as e:\n    ok=False\nprint(json.dumps({{'name':{repr(t.name)},'passed':ok,'expected':{exp},'actual':r}}))")
            return f"import json\n{code}\n" + "\n".join(test_blocks)
        return f"{code}\nconsole.log('tests')"


# Hermes compatibility — import and re-export HermesVerifier from deterministic
from ratchet.deterministic.verifier import HermesVerifier
