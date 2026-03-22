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
        steps_log = []
        for iteration in range(self.config.max_iterations):
            iteration_log = {"iteration": iteration}
            steps_log.append(iteration_log)
            if skill:
                result = await self._execute_skill(task, skill)
            else:
                output = await self._execute_basic(task)
                result = {"steps": [{"output": output}], "success": True, "output": output}
            if result["success"]:
                return {"steps": steps_log, "success": True, "output": result.get("output"), "iterations": iteration + 1}
            error = result.get("error", "Unknown")
            code = result.get("steps", [{}])[-1].get("output", "")
            analysis = self.reflector.analyze_failure(code=code, error=error, verification_output=error)
            iteration_log["failure_analysis"] = analysis.to_dict()
            lesson = RepairLesson(
                id=str(uuid.uuid4()), failure_pattern=analysis.category,
                error_signature=error[:100], context=task,
                repair_strategy=analysis.suggested_fix, model_used=self.config.model,
            )
            self.curator.add_lesson(lesson)
            iteration_log["lesson_id"] = lesson.id
        return {"steps": steps_log, "success": False, "error": "Max iterations reached"}

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