"""
Skill Schema — Pydantic models for skill definitions.

Compatible with both Ratchet's Step schema and Ratchet's SKILL.md format.
"""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum


class StepType(str, Enum):
    """Supported step types for deterministic skill workflows."""
    PROMPT = "prompt"
    READ = "read"
    WRITE = "write"
    EXEC = "exec"
    VERIFY = "verify"
    BRANCH = "branch"


class VerificationRule(BaseModel):
    """
    Verification rule for a step.

    Types:
    - assertion: run code expression as test
    - test: structured test with expected output
    - output: check output string patterns
    - exit_code: check execution exit code
    """
    type: str = Field(..., description="Type: assertion, test, output, exit_code")
    expression: Optional[str] = Field(None, description="Code expression to evaluate")
    expected: Optional[str] = Field(None, description="Expected output value")
    must_contain: Optional[List[str]] = Field(None, description="Strings that must appear in output")
    must_not_contain: Optional[List[str]] = Field(None, description="Strings that must NOT appear")
    input: Optional[Any] = Field(None, description="Test input data")
    name: Optional[str] = Field(None, description="Name of this verification rule")
    exit_code: Optional[int] = Field(None, description="Expected exit code (0 for success)")


class SkillStep(BaseModel):
    """
    A single step in a skill workflow.

    Fields by type:
    - PROMPT: prompt (str) — template prompt string
    - READ: file_path (str) — path to file to read
    - WRITE: file_path (str), content (str) — path and content to write
    - EXEC: command (str), language (str, default python), timeout (int)
    - VERIFY: command (str), language (str), verification (VerificationRule)
    - BRANCH: condition (str), if_true (List[str]), if_false (List[str])

    Common fields:
    - id: unique identifier for this step
    - type: StepType enum value
    - verification: optional VerificationRule for output validation
    """
    id: str = Field(..., description="Unique step identifier")
    type: StepType = Field(..., description="Step type")
    prompt: Optional[str] = Field(None, description="PROMPT: template prompt")
    file_path: Optional[str] = Field(None, description="READ/WRITE: file path")
    content: Optional[str] = Field(None, description="WRITE: content to write")
    command: Optional[str] = Field(None, description="EXEC/VERIFY: code to run")
    language: Optional[str] = Field("python", description="EXEC/VERIFY: language (python, javascript, etc.)")
    timeout: Optional[int] = Field(30, description="EXEC/VERIFY: timeout in seconds")
    verification: Optional[VerificationRule] = Field(None, description="Optional verification rule")
    condition: Optional[str] = Field(None, description="BRANCH: Python expression to evaluate")
    if_true: Optional[List[str]] = Field(None, description="BRANCH: step ids if condition is true")
    if_false: Optional[List[str]] = Field(None, description="BRANCH: step ids if condition is false")
    description: Optional[str] = Field(None, description="Human-readable step description")
    # Allow extra fields for forward compatibility
    class Config:
        extra = "allow"


class Skill(BaseModel):
    """
    A deterministic skill definition.

    Skills are versioned, self-improving workflows composed of verified steps.
    """
    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")
    version: str = Field("0.1.0", description="Semantic version")
    steps: List[SkillStep] = Field(..., description="Ordered list of skill steps")
    self_improve: bool = Field(True, description="Whether to evolve skill from successes/failures")
    learn_from_failures: bool = Field(True, description="Whether to record failures in curator")
    author: Optional[str] = Field(None, description="Skill author")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    # Allow extra fields
    class Config:
        extra = "allow"

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict, compatible with Ratchet's step format."""
        return self.model_dump()

    @classmethod
    def from_ratchet_steps(cls, name: str, description: str, ratchet_steps: List[Any]) -> "Skill":
        """
        Construct a Skill from Ratchet's Step objects.

        Ratchet steps have: id, type (str), and type-specific attributes.
        Maps Ratchet types to StepType enum.
        """
        steps = []
        for rs in ratchet_steps:
            step_type_str = getattr(rs, "type", "prompt")
            try:
                step_type = StepType(step_type_str.lower())
            except ValueError:
                step_type = StepType.PROMPT

            steps.append(SkillStep(
                id=getattr(rs, "id", f"step_{len(steps)}"),
                type=step_type,
                prompt=getattr(rs, "prompt", None),
                file_path=getattr(rs, "file_path", None),
                content=getattr(rs, "content", None),
                command=getattr(rs, "command", getattr(rs, "code", None)),
                language=getattr(rs, "language", "python"),
                timeout=getattr(rs, "timeout", 30),
                condition=getattr(rs, "condition", None),
                if_true=getattr(rs, "if_true", None),
                if_false=getattr(rs, "if_false", None),
            ))

        return cls(
            name=name,
            description=description,
            steps=steps,
        )

    def to_ratchet_format(self) -> Dict[str, Any]:
        """
        Serialize in a format compatible with Ratchet's skill/step schema.

        Returns a dict with 'steps' as list of dicts that Ratchet can parse.
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "steps": [
                {
                    "id": s.id,
                    "type": s.type.value,
                    **{k: v for k, v in s.model_dump().items()
                       if k not in ("id", "type") and v is not None},
                }
                for s in self.steps
            ],
        }

    def get_step(self, step_id: str) -> Optional[SkillStep]:
        """Get a step by its id."""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def step_ids(self) -> List[str]:
        """Return ordered list of step ids."""
        return [s.id for s in self.steps]
