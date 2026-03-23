"""
Main Agent - Self-improving agent loop with deterministic execution
"""

import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from ratchet.models import ModelClient, get_client
from ratchet.skill import Skill, Step, StepType
from ratchet.generator import Generator
from ratchet.verifier import Verifier, ExecutionResult, TestCase, VerificationStatus
from ratchet.reflector import Reflector, FailureAnalysis
from ratchet.curator import Curator, RepairLesson


class AgentMode(str, Enum):
    BASIC = "basic"
    SKILL = "skill"
    SELF_IMPROVE = "self_improve"


@dataclass
class ExecutionTrace:
    id: str
    task: str
    mode: str
    skill_name: Optional[str]
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: float = 0
    total_cost: float = 0
    steps: List[Dict[str, Any]] = field(default_factory=list)
    success: bool = False
    output: Optional[str] = None
    error: Optional[str] = None
    failure_analysis: Optional[Dict] = None
    lesson_id: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v if not hasattr(v, 'to_dict') else v.to_dict() for k, v in self.__dict__.items()}


@dataclass
class AgentConfig:
    provider: str = "minimax"
    model: str = "MiniMax-M2.7"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    mode: AgentMode = AgentMode.SELF_IMPROVE
    max_iterations: int = 3
    temperature: float = 0.3
    verify_all: bool = True
    sandbox_dir: Optional[str] = None
    learn_from_failures: bool = True
    curator_path: str = "./data/curator.json"


class RatchetAgent:
    """
    Self-improving AI agent with deterministic skill execution.
    """
    def __init__(self, config: Optional[AgentConfig] = None):
        self.config = config or AgentConfig()
        self.model_client = get_client(
            provider=self.config.provider,
            api_key=self.config.api_key,
            base_url=self.config.api_base,
        )
        self.generator = Generator(
            client=self.model_client,
            model=self.config.model,
        )
        self.verifier = Verifier(sandbox_dir=self.config.sandbox_dir)
        self.reflector = Reflector(model=self.generator)
        self.curator = Curator(storage_path=self.config.curator_path)
        self.current_trace: Optional[ExecutionTrace] = None
        self.execution_history: List[ExecutionTrace] = []

    async def execute_task(self, task: str, skill: Optional[Skill] = None, mode: Optional[AgentMode] = None) -> ExecutionTrace:
        from datetime import datetime
        import time
        mode = mode or self.config.mode
        trace = ExecutionTrace(
            id=str(uuid.uuid4()), task=task, mode=mode.value,
            skill_name=skill.name if skill else None,
            started_at=datetime.utcnow().isoformat(),
        )
        self.current_trace = trace
        start = time.time()
        try:
            if mode == AgentMode.BASIC:
                output = await self._execute_basic(task)
                trace.success = True
                trace.output = output
            elif mode == AgentMode.SKILL:
                if not skill: raise ValueError("Skill required for SKILL mode")
                result = await self._execute_skill(task, skill)
                trace.steps = result["steps"]
                trace.success = result["success"]
                trace.output = result.get("output")
                trace.error = result.get("error")
            elif mode == AgentMode.SELF_IMPROVE:
                result = await self._execute_self_improve(task, skill)
                trace.steps = result["steps"]
                trace.success = result["success"]
                trace.output = result.get("output")
                trace.error = result.get("error")
                trace.failure_analysis = result.get("failure_analysis")
                trace.lesson_id = result.get("lesson_id")
        except Exception as e:
            trace.success = False
            trace.error = str(e)
        trace.duration_ms = (time.time() - start) * 1000
        trace.total_cost = self.generator.total_cost
        trace.completed_at = datetime.utcnow().isoformat()
        self.execution_history.append(trace)
        return trace

    async def _execute_basic(self, task: str) -> str:
        response = self.generator.generate(prompt=task)
        return response.content

    async def _extract_and_execute(self, content: str) -> tuple:
        """
        Extract code from model response and execute it via Verifier.

        Returns (success, output, error, verification_output)
        - success: True if code executed without errors
        - output: the execution output (stdout)
        - error: error message if execution failed
        - verification_output: full verification result for reflection
        """
        import json, re

        # Try to find tool call in response
        code = None

        # 1. Look for execute_code tool call JSON
        try:
            match = re.search(r'\{[^{}]*"name"\s*:\s*"execute_code"[^{}]*\}', content, re.DOTALL)
            if match:
                tool_call = json.loads(match.group())
                args = tool_call.get("parameters", {})
                if "input_code" in args:
                    code = args["input_code"]
                elif "code" in args:
                    code = args["code"]
        except (json.JSONDecodeError, re.error):
            pass

        # 2. Look for code blocks
        if not code:
            for lang in ("python", "py", ""):
                pattern = f"```{lang}[^```]*```" if lang else "```[^```]*```"
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    code = match.group()
                    # Strip markdown
                    for marker in (f"```{lang}", "```"):
                        code = code.replace(marker, "").strip()
                    break

        # 3. If still no code, treat the whole response as code
        if not code:
            code = content.strip()

        # Execute the code
        if not code or len(code) < 3:
            return True, content, None, "No code to execute"

        try:
            result = await self.verifier.execute_async(code, language="python", timeout=30)
            return (
                result.status == VerificationStatus.PASS,
                result.output,
                result.error,
                result.to_dict(),
            )
        except Exception as e:
            return False, "", str(e), {"error": str(e)}

    async def _execute_skill(self, task: str, skill: Skill) -> Dict[str, Any]:
        steps_log = []
        context = {"task": task}
        current_step_id = skill.steps[0].id if skill.steps else None
        while current_step_id:
            step = skill.get_step(current_step_id)
            if not step: break
            step_log = {"step_id": step.id, "type": step.type.value}
            steps_log.append(step_log)
            if step.type == StepType.PROMPT:
                prompt = step.prompt.format(**context) if step.prompt else f"Complete: {task}"
                response = self.generator.generate(prompt=prompt)
                context["last_output"] = response.content
                step_log["output"] = response.content
                step_log["cost"] = response.cost
            current_step_id = skill.get_next_steps(current_step_id)[0] if skill.get_next_steps(current_step_id) else None
        return {"steps": steps_log, "success": True, "output": context.get("last_output")}

    async def _execute_self_improve(self, task: str, skill: Optional[Skill] = None) -> Dict[str, Any]:
        """
        Self-improvement loop: generate code, verify it, reflect on failure, retry.

        1. Generate code from model
        2. Extract code and execute via Verifier
        3. On failure: analyze with Reflector, learn with Curator, retry
        4. Returns with verified output or final failure
        """
        steps_log: List[Dict[str, Any]] = []
        last_failure = None

        for iteration in range(self.config.max_iterations):
            iteration_log: Dict[str, Any] = {"iteration": iteration}

            # Generate
            if skill:
                result = await self._execute_skill(task, skill)
                raw_output = result.get("output", "")
            else:
                raw_output = await self._execute_basic(task)

            # Extract code and execute
            verified, exec_output, exec_error, verification_output = await self._extract_and_execute(raw_output)
            iteration_log["verification"] = verification_output

            if verified:
                iteration_log["status"] = "pass"
                iteration_log["output"] = exec_output or raw_output
                steps_log.append(iteration_log)
                return {
                    "steps": steps_log,
                    "success": True,
                    "output": exec_output or raw_output,
                    "iterations": iteration + 1,
                }

            # Verification failed — reflect and learn
            iteration_log["status"] = "fail"
            iteration_log["exec_error"] = exec_error

            # Extract code for analysis
            code = self.generator.extract_code(raw_output) or raw_output

            # Analyze failure
            analysis = self.reflector.analyze_failure(
                code=code,
                error=exec_error or "Verification failed",
                verification_output=str(verification_output),
                context={"task": task},
            )
            iteration_log["failure_analysis"] = analysis.to_dict()

            # Learn from failure
            if self.config.learn_from_failures:
                lesson = RepairLesson(
                    id=str(uuid.uuid4()),
                    failure_pattern=analysis.category,
                    error_signature=analysis.root_cause[:100],
                    context=task,
                    repair_strategy=analysis.suggested_fix,
                    model_used=self.config.model,
                    fix_code=analysis.suggested_fix,
                )
                self.curator.add_lesson(lesson)
                iteration_log["lesson_id"] = lesson.id

            # Check for similar past lessons
            similar = self.curator.find_similar(
                failure_pattern=analysis.category,
                error_signature=analysis.root_cause[:100],
            )
            if similar:
                iteration_log["similar_lesson"] = similar.repair_strategy[:200]

            # Build improved prompt for next iteration
            improvement_hint = (
                f"Previous attempt failed: {analysis.hypothesis}\n"
                f"Suggested fix: {analysis.suggested_fix}"
            )
            if similar:
                improvement_hint += f"\nPast successful fix: {similar.repair_strategy}"

            # Retry with improvement hint
            retry_prompt = f"""{task}

{improvement_hint}

Generate corrected code that addresses the failure. Return only the code with minimal explanation."""
            retry_response = self.generator.generate(prompt=retry_prompt)
            retry_verified, retry_output, retry_error, retry_verification = await self._extract_and_execute(
                retry_response.content
            )
            iteration_log["retry_verification"] = retry_verification

            if retry_verified:
                iteration_log["status"] = "pass_after_retry"
                iteration_log["output"] = retry_output or retry_response.content
                steps_log.append(iteration_log)
                return {
                    "steps": steps_log,
                    "success": True,
                    "output": retry_output or retry_response.content,
                    "iterations": iteration + 1,
                }

            # Still failing — log and continue to next iteration
            last_failure = {
                "error": retry_error or exec_error,
                "analysis": analysis.to_dict(),
            }
            steps_log.append(iteration_log)

        return {
            "steps": steps_log,
            "success": False,
            "error": f"Max iterations ({self.config.max_iterations}) reached. Last error: {last_failure.get('error') if last_failure else 'unknown'}",
            "failure_analysis": last_failure.get("analysis") if last_failure else None,
            "output": "",
        }

    def execute_task_sync(self, task: str, skill: Optional[Skill] = None, mode: Optional[AgentMode] = None) -> ExecutionTrace:
        import asyncio
        return asyncio.run(self.execute_task(task, skill, mode))

    def get_stats(self) -> Dict[str, Any]:
        total = len(self.execution_history)
        successes = sum(1 for t in self.execution_history if t.success)
        return {
            "total_executions": total,
            "successes": successes,
            "success_rate": successes / total if total > 0 else 0,
            "total_cost": sum(t.total_cost for t in self.execution_history),
        }