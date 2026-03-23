"""
Skill schema - deterministic workflow definitions
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class StepType(str, Enum):
    PROMPT = "prompt"
    READ = "read"
    WRITE = "write"
    EXEC = "exec"
    VERIFY = "verify"
    BRANCH = "branch"


class VerificationType(str, Enum):
    ASSERTION = "assertion"
    TEST = "test"
    OUTPUT = "output"
    EXIT_CODE = "exit_code"


class VerificationRule(BaseModel):
    type: VerificationType
    description: Optional[str] = None
    expression: Optional[str] = None
    test_file: Optional[str] = None
    test_command: Optional[str] = None
    expected: Optional[str] = None
    must_contain: Optional[List[str]] = None
    must_not_contain: Optional[List[str]] = None
    expected_code: Optional[int] = None


class Step(BaseModel):
    id: str
    type: StepType
    description: Optional[str] = None
    prompt: Optional[str] = None
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    file_path: Optional[str] = None
    content: Optional[str] = None
    command: Optional[str] = None
    cwd: Optional[str] = None
    timeout: Optional[int] = 30
    verification: Optional[VerificationRule] = None
    condition: Optional[str] = None
    if_true: Optional[List[str]] = None
    if_false: Optional[List[str]] = None


class Skill(BaseModel):
    name: str
    description: str
    version: str = "0.1.0"
    trigger_pattern: Optional[str] = None
    trigger_type: str = "pattern"
    steps: List[Step] = Field(default_factory=list)
    self_improve: bool = True
    learn_from_failures: bool = True
    author: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    examples: List[Dict[str, Any]] = Field(default_factory=list)
    success_count: int = 0
    failure_count: int = 0
    total_cost: float = 0.0

    def get_step(self, step_id: str) -> Optional[Step]:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def get_next_steps(self, current_step_id: str, condition_result: Optional[bool] = None) -> List[str]:
        current = self.get_step(current_step_id)
        if not current:
            return []
        if current.type == StepType.BRANCH and current.if_true and current.if_false:
            return current.if_true if condition_result else current.if_false
        for i, step in enumerate(self.steps):
            if step.id == current_step_id and i + 1 < len(self.steps):
                return [self.steps[i + 1].id]
        return []

    def record_success(self, cost: float):
        self.success_count += 1
        self.total_cost += cost

    def record_failure(self, cost: float):
        self.failure_count += 1
        self.total_cost += cost

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0


# Hermes compatibility — re-export SkillStep and SkillSchema from deterministic/skill_schema
from ratchet.deterministic.skill_schema import SkillStep, Skill as SkillSchema
