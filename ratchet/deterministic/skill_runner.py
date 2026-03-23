"""
Deterministic Skill Runner — runs a skill as a verified multi-step workflow.

Each step is executed with verification before proceeding to the next step.
Failure at any step triggers Reflector analysis + Curator.learn() + retry.
"""

from ratchet.deterministic.generator import RatchetGenerator, GenerationResult
from ratchet.deterministic.verifier import RatchetVerifier, VerificationStatus, TestCase
from ratchet.deterministic.reflector import RatchetReflector, FailureAnalysis
from ratchet.deterministic.curator import RatchetCurator
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from dataclasses import dataclass, field

if TYPE_CHECKING:
    from hermes.knowledge_base import HermesKnowledgeBase

import os
import re
from pathlib import Path

_hermes_home = Path(os.getenv("HERMES_HOME", Path.home() / ".hermes"))


@dataclass
class SkillStepResult:
    """Result of executing a single skill step."""
    step_id: str
    status: VerificationStatus
    output: str
    error: Optional[str] = None
    analysis: Optional[FailureAnalysis] = None


class SkillRunner:
    """
    Executes a skill as a deterministic sequence of verified steps.

    Steps are defined as dicts with: id, type (PROMPT|READ|WRITE|EXEC|VERIFY|BRANCH),
    and type-specific fields.

    On failure: reflects, learns, retries up to max_retries.
    """

    def __init__(
        self,
        agent: "AIAgent",
        max_retries: int = 3,
        kb: Optional["HermesKnowledgeBase"] = None,
    ):
        self.agent = agent
        self.generator = RatchetGenerator(agent)
        self.verifier = RatchetVerifier()
        self.reflector = RatchetReflector(self.generator)
        self.curator = RatchetCurator(kb=kb)
        self.max_retries = max_retries

    async def run_skill(
        self,
        skill_name: str,
        skill_steps: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[SkillStepResult]:
        """
        Run all steps of a skill with verification.

        Returns list of step results in execution order.

        On failure of a VERIFY or EXEC step, triggers reflect → learn → retry loop.
        """
        results: List[SkillStepResult] = []
        step_index = 0

        while step_index < len(skill_steps):
            step = skill_steps[step_index]

            # BRANCH steps may redirect flow
            if step.get("type") == "branch":
                branch_result = await self._run_branch_step(step, context, results)
                # Determine next step index based on branch result
                branch_outcome = branch_result.output.strip().lower()
                if branch_outcome in ("true", "1", "yes") and step.get("if_true"):
                    # Find next step index by id
                    next_ids = step.get("if_true", [])
                    step_index = self._find_step_index(skill_steps, next_ids[0], step_index + 1)
                elif branch_outcome in ("false", "0", "no") and step.get("if_false"):
                    next_ids = step.get("if_false", [])
                    step_index = self._find_step_index(skill_steps, next_ids[0], step_index + 1)
                else:
                    step_index += 1
                results.append(branch_result)
                continue

            # Execute step with retry loop for EXEC/VERIFY
            step_type = step.get("type", "").lower()
            is_retryable = step_type in ("exec", "verify")

            attempt = 0
            step_result: Optional[SkillStepResult] = None

            while attempt <= self.max_retries:
                step_result = await self.run_step(step, context)

                if step_result.status == VerificationStatus.PASS:
                    break

                if not is_retryable:
                    # Non-retryable step — record failure and move on
                    break

                # Analyze failure
                analysis = self.reflector.analyze_failure(
                    code=step.get("command", step.get("code", "")),
                    error=step_result.error or "Unknown error",
                    verification_output=step_result.output,
                    context={"task": skill_name, "skill_name": skill_name, **context},
                )
                step_result.analysis = analysis

                # Learn from failure
                self.curator.add_lesson(
                    failure_pattern=analysis.category,
                    error_signature=step_result.error or "",
                    context=f"Skill: {skill_name}, Step: {step.get('id')}",
                    repair_strategy=analysis.suggested_fix,
                    fix_code=step.get("command"),
                    skill_name=skill_name,
                )

                attempt += 1
                if attempt <= self.max_retries:
                    # Wait before retry (exponential backoff)
                    await self._sleep(attempt)

            results.append(step_result)
            step_index += 1

        return results

    async def run_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillStepResult:
        """
        Run a single step based on its type.

        - PROMPT: call generator.generate() with rendered prompt → output is response text
        - READ: read file content → output is file contents
        - WRITE: write content to file (verified by read-back) → output is write confirmation
        - EXEC: run code via verifier.execute() → output is execution result
        - VERIFY: run code + test harness via verifier.verify_code() → output is test results
        - BRANCH: evaluate condition → output is "true" or "false"
        """
        step_type = step.get("type", "").lower()
        step_id = step.get("id", "unknown")

        try:
            if step_type == "prompt":
                return await self._run_prompt_step(step, context)
            elif step_type == "read":
                return await self._run_read_step(step, context)
            elif step_type == "write":
                return await self._run_write_step(step, context)
            elif step_type == "exec":
                return await self._run_exec_step(step, context)
            elif step_type == "verify":
                return await self._run_verify_step(step, context)
            elif step_type == "branch":
                return await self._run_branch_step(step, context, [])
            else:
                return SkillStepResult(
                    step_id=step_id,
                    status=VerificationStatus.ERROR,
                    output="",
                    error=f"Unknown step type: {step_type}",
                )
        except Exception as e:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error=str(e),
            )

    async def _run_prompt_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillStepResult:
        """Execute a PROMPT step."""
        step_id = step.get("id", "unknown")
        prompt_template = step.get("prompt", "")

        # Render template with context
        rendered_prompt = self._render_template(prompt_template, context)

        result = self.generator.generate(rendered_prompt)

        if result.error:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error=result.error,
            )

        return SkillStepResult(
            step_id=step_id,
            status=VerificationStatus.PASS,
            output=result.content,
        )

    async def _run_read_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillStepResult:
        """Execute a READ step — read a file and return its contents."""
        step_id = step.get("id", "unknown")
        file_path = self._render_template(step.get("file_path", ""), context)

        if not file_path:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error="READ step missing file_path",
            )

        try:
            # Update context with file content for subsequent steps
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.PASS,
                output=content,
            )
        except FileNotFoundError:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error=f"File not found: {file_path}",
            )
        except Exception as e:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error=f"Error reading {file_path}: {e}",
            )

    async def _run_write_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillStepResult:
        """Execute a WRITE step — write content to a file, verified by read-back."""
        step_id = step.get("id", "unknown")
        file_path = self._render_template(step.get("file_path", ""), context)
        content = self._render_template(step.get("content", ""), context)

        if not file_path:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error="WRITE step missing file_path",
            )

        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)

            # Write content
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Verify by reading back
            with open(file_path, "r", encoding="utf-8") as f:
                verified = f.read()

            if verified != content:
                return SkillStepResult(
                    step_id=step_id,
                    status=VerificationStatus.FAIL,
                    output="",
                    error="Write verification failed: content mismatch on read-back",
                )

            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.PASS,
                output=f"Wrote {len(content)} bytes to {file_path}",
            )
        except Exception as e:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error=f"Error writing {file_path}: {e}",
            )

    async def _run_exec_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillStepResult:
        """Execute an EXEC step — run code via verifier, output is execution result."""
        step_id = step.get("id", "unknown")
        command = self._render_template(step.get("command", ""), context)
        language = step.get("language", "python")
        timeout = step.get("timeout", 30)

        if not command:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error="EXEC step missing command",
            )

        result = await self.verifier.execute_async(command, language=language, timeout=timeout)

        return SkillStepResult(
            step_id=step_id,
            status=result.status,
            output=result.output,
            error=result.error,
        )

    async def _run_verify_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> SkillStepResult:
        """Execute a VERIFY step — run code + test harness, output is test results."""
        step_id = step.get("id", "unknown")
        command = self._render_template(step.get("command", ""), context)
        language = step.get("language", "python")
        timeout = step.get("timeout", 60)

        # Build test cases from verification rules
        tests = self._build_tests_from_step(step, context)

        if not command:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error="VERIFY step missing command",
            )

        result = await self.verifier.verify_code_async(
            command, tests=tests, language=language, timeout=timeout
        )

        return SkillStepResult(
            step_id=step_id,
            status=result.status,
            output=result.output,
            error=result.error,
        )

    async def _run_branch_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
        results: List[SkillStepResult],
    ) -> SkillStepResult:
        """Execute a BRANCH step — evaluate condition, return 'true' or 'false'."""
        step_id = step.get("id", "unknown")
        condition = step.get("condition", "")

        if not condition:
            return SkillStepResult(
                step_id=step_id,
                status=VerificationStatus.ERROR,
                output="",
                error="BRANCH step missing condition",
            )

        # Render condition template
        rendered_condition = self._render_template(condition, context)

        # Evaluate the condition expression
        try:
            # Use eval with a safe globals dict for simple expressions
            # Allow access to context and previous results
            safe_globals = {"context": context, "results": results}
            outcome = eval(rendered_condition, {"__builtins__": {}}, safe_globals)
            outcome_str = str(bool(outcome)).lower()
        except Exception as e:
            outcome_str = f"false (error: {e})"

        return SkillStepResult(
            step_id=step_id,
            status=VerificationStatus.PASS,
            output=outcome_str,
        )

    async def _verify_step(
        self,
        step: Dict[str, Any],
        output: str,
    ) -> VerificationStatus:
        """
        Run step-specific verification if defined.

        Checks the step's `verification` dict for rules:
        - must_contain: list of strings that must appear in output
        - must_not_contain: list of strings that must NOT appear
        - expected: exact string expected in output
        - exit_code: expected exit code (for EXEC steps)
        """
        verification = step.get("verification")
        if not verification:
            return VerificationStatus.PASS

        rules = verification if isinstance(verification, list) else [verification]

        for rule in rules:
            rule_type = rule.get("type", "")

            if rule_type == "must_contain":
                must_contain = rule.get("must_contain", [])
                for substr in must_contain:
                    if substr not in output:
                        return VerificationStatus.FAIL

            elif rule_type == "must_not_contain":
                must_not = rule.get("must_not_contain", [])
                for substr in must_not:
                    if substr in output:
                        return VerificationStatus.FAIL

            elif rule_type == "expected":
                expected = rule.get("expected")
                if expected is not None and output != expected:
                    return VerificationStatus.FAIL

            elif rule_type == "output":
                # General output match
                expr = rule.get("expression")
                if expr:
                    try:
                        outcome = eval(expr, {"output": output})
                        if not outcome:
                            return VerificationStatus.FAIL
                    except Exception:
                        return VerificationStatus.ERROR

        return VerificationStatus.PASS

    def _render_template(self, template: str, context: Dict[str, Any]) -> str:
        """
        Render a template with {placeholder} syntax.

        Also handles {context.key} dot-notation for nested access.
        """
        if not template:
            return template

        result = template
        # Replace {key} patterns
        for key, value in context.items():
            result = result.replace(f"{{{key}}}", str(value))

        # Handle nested {context.key} patterns
        nested_pattern = re.compile(r"\{context\.([^}]+)\}")
        for match in nested_pattern.finditer(result):
            path = match.group(1)
            parts = path.split(".")
            value = context
            for part in parts:
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    value = None
                    break
            result = result.replace(match.group(0), str(value) if value is not None else "")

        return result

    def _build_tests_from_step(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> List[TestCase]:
        """Build TestCase objects from a step's verification rules."""
        verification = step.get("verification")
        if not verification:
            return []

        rules = verification if isinstance(verification, list) else [verification]
        tests = []

        for i, rule in enumerate(rules):
            rule_type = rule.get("type", "test")

            if rule_type in ("assertion", "test"):
                tests.append(TestCase(
                    name=rule.get("name", f"assertion_{i}"),
                    input_data=rule.get("input"),
                    expected=rule.get("expected"),
                    code=rule.get("expression"),
                ))

        return tests

    def _find_step_index(
        self,
        steps: List[Dict[str, Any]],
        target_id: str,
        start: int = 0,
    ) -> int:
        """Find the index of a step by its id, starting from a given position."""
        for i in range(start, len(steps)):
            if steps[i].get("id") == target_id:
                return i
        return len(steps)  # Default: end of steps

    async def _sleep(self, attempt: int):
        """Exponential backoff sleep between retries."""
        import asyncio
        await asyncio.sleep(0.1 * (2 ** attempt))

    # =========================================================================
    # Skill nudge — detect reusable patterns and create skills
    # =========================================================================

    async def trigger_skill_review(
        self,
        session_id: str,
        session_db,
    ) -> Optional[str]:
        """
        After a successful complex task, trigger skill creation.

        Called by the agent after _skill_nudge_interval iterations.
        Analyzes recent successful task patterns and writes a SKILL.md
        to ~/.hermes/skills/ if a reusable pattern is detected.

        Args:
            session_id: Current session ID
            session_db: SessionDB instance for accessing conversation history

        Returns:
            Skill name if one was created, None otherwise
        """
        import hashlib
        import json
        import os
        import re

        try:
            # Get recent messages from session
            if session_db is None:
                return None

            messages = session_db.get_messages(session_id)
            if not messages:
                return None

            # Extract tool call patterns from recent successful turns
            tool_patterns = []
            for msg in messages[-20:]:  # Look at last 20 messages
                if msg.get("role") != "tool":
                    continue
                try:
                    content = json.loads(msg.get("content", "{}"))
                except (json.JSONDecodeError, TypeError):
                    continue

                tool_name = content.get("tool_name", "")
                args = content.get("args", {})
                if tool_name and args:
                    tool_patterns.append({
                        "tool": tool_name,
                        "args": {k: v for k, v in args.items() if k in ("path", "command", "query", "url")}
                    })

            if len(tool_patterns) < 3:
                # Too few steps to suggest a skill
                return None

            # Detect if there's a repeating pattern
            pattern_key = self._detect_pattern(tool_patterns)
            if not pattern_key:
                return None

            # Build a skill name from the pattern
            skill_name = self._suggest_skill_name(tool_patterns)
            if not skill_name:
                return None

            # Check if skill already exists
            skill_path = self._get_skill_path(skill_name)
            if skill_path.exists():
                return None

            # Create the skill
            skill_content = self._build_skill_md(skill_name, tool_patterns, pattern_key)
            self._write_skill(skill_name, skill_content)

            return skill_name

        except Exception as e:
            import logging
            logging.getLogger(__name__).debug(
                "trigger_skill_review failed: %s", e
            )
            return None

    def _detect_pattern(self, tool_patterns: List[Dict[str, Any]]) -> Optional[str]:
        """Detect if there's a repeating sequence of tool calls."""
        if len(tool_patterns) < 3:
            return None

        # Look for repeated subsequence of at least 3 steps
        pattern_map: Dict[str, int] = {}
        for i in range(len(tool_patterns) - 2):
            key = self._pattern_key(tool_patterns[i:i+3])
            pattern_map[key] = pattern_map.get(key, 0) + 1

        # If any pattern appears at least twice, it's a candidate
        for key, count in pattern_map.items():
            if count >= 2:
                return key
        return None

    def _pattern_key(self, steps: List[Dict[str, Any]]) -> str:
        """Build a hash key for a sequence of steps."""
        parts = []
        for step in steps:
            tool = step.get("tool", "")
            args = step.get("args", {})
            args_str = json.dumps(args, sort_keys=True, default=str)
            parts.append(f"{tool}:{args_str[:50]}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def _suggest_skill_name(self, tool_patterns: List[Dict[str, Any]]) -> Optional[str]:
        """Suggest a skill name based on the dominant tool pattern."""
        tool_counts: Dict[str, int] = {}
        for pattern in tool_patterns:
            tool = pattern.get("tool", "")
            if tool:
                tool_counts[tool] = tool_counts.get(tool, 0) + 1

        if not tool_counts:
            return None

        dominant_tool = max(tool_counts, key=tool_counts.get)
        suffix = ""

        # Map common tools to skill suffixes
        tool_suffix_map = {
            "read": "reader",
            "write": "writer",
            "terminal": "command",
            "execute": "executor",
            "search": "searcher",
            "analyze": "analyzer",
            "build": "builder",
            "test": "tester",
            "deploy": "deployer",
        }
        suffix = tool_suffix_map.get(dominant_tool, dominant_tool)

        # Clean the suffix
        suffix = re.sub(r"[^a-z0-9_]", "", suffix.lower())
        if not suffix:
            suffix = "workflow"

        # Prepend a meaningful prefix based on file paths seen
        paths_seen = set()
        for pattern in tool_patterns:
            path = pattern.get("args", {}).get("path", "")
            if path:
                paths_seen.add(os.path.basename(path))
        prefix = "file"
        if paths_seen:
            prefixes = {"py": "python", "js": "javascript", "md": "doc", "json": "config"}
            for path in paths_seen:
                ext = os.path.splitext(path)[-1].lstrip(".")
                if ext in prefixes:
                    prefix = prefixes[ext]
                    break

        return f"{prefix}_{suffix}"

    def _build_skill_md(
        self,
        skill_name: str,
        tool_patterns: List[Dict[str, Any]],
        pattern_key: str,
    ) -> str:
        """Build SKILL.md content from detected patterns."""
        lines = [
            f"# {skill_name}",
            "",
            f"Auto-generated skill from Ratchet skill nudge.",
            f"Pattern ID: {pattern_key}",
            "",
            "## When to Use",
            "",
            "Use this skill when you need to:",
            "",
        ]

        # Add tool sequence description
        unique_tools = []
        seen = set()
        for p in tool_patterns:
            tool = p.get("tool", "")
            if tool and tool not in seen:
                unique_tools.append(tool)
                seen.add(tool)

        for tool in unique_tools:
            lines.append(f"- Execute {tool} operations")

        lines.extend([
            "",
            "## Steps",
            "",
        ])

        for i, step in enumerate(tool_patterns[:6], 1):  # Max 6 steps in SKILL.md
            tool = step.get("tool", "unknown")
            args = step.get("args", {})
            args_str = json.dumps(args, sort_keys=True, indent=2, default=str)
            lines.extend([
                f"### Step {i}: {tool}",
                "",
                f"```json",
                f"{args_str}",
                f"```",
                "",
            ])

        lines.extend([
            "## Notes",
            "",
            "- This skill was auto-generated from successful execution patterns",
            "- Review and refine the steps as needed for your use case",
            "",
        ])

        return "\n".join(lines)

    def _get_skill_path(self, skill_name: str) -> Path:
        """Get the path where a skill should be written."""
        skills_dir = _hermes_home / "skills"
        skills_dir.mkdir(parents=True, exist_ok=True)
        # Convert skill_name to safe filename
        safe_name = re.sub(r"[^a-z0-9_]", "_", skill_name.lower())
        return skills_dir / f"{safe_name}.md"

    def _write_skill(self, skill_name: str, content: str) -> bool:
        """Write a SKILL.md file to the skills directory."""
        try:
            skill_path = self._get_skill_path(skill_name)
            skill_path.write_text(content, encoding="utf-8")
            return True
        except Exception:
            return False
