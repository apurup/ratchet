"""
Agent - Main agent loop with verify-fix cycles
"""

import time
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from ratchet.skill import Skill, Step, StepType
from ratchet.generator import Generator
from ratchet.verifier import Verifier, VerificationResult
from ratchet.reflector import Reflector
from ratchet.curator import Curator


@dataclass
class AgentConfig:
    max_iterations: int = 10
    max_cost_per_step: float = 5.0
    improvement_threshold: float = 0.8
    verbose: bool = True


@dataclass
class StepResult:
    step_id: str
    step_type: StepType
    passed: bool
    output: str = ""
    error: Optional[str] = None
    cost: float = 0.0
    latency_ms: float = 0.0
    verification: Optional[VerificationResult] = None


@dataclass
class ExecutionResult:
    skill_name: str
    passed: bool
    steps: List[StepResult] = field(default_factory=list)
    total_cost: float = 0.0
    total_time_ms: float = 0.0
    final_output: str = ""
    error: Optional[str] = None


class Agent:
    """Main agent that executes skills with verification and self-improvement."""

    def __init__(
        self,
        generator: Optional[Generator] = None,
        verifier: Optional[Verifier] = None,
        reflector: Optional[Reflector] = None,
        curator: Optional[Curator] = None,
        config: Optional[AgentConfig] = None,
    ):
        self.generator = generator or Generator()
        self.verifier = verifier or Verifier()
        self.reflector = reflector or Reflector()
        self.curator = curator or Curator()
        self.config = config or AgentConfig()

    def run(self, skill: Skill, context: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        """Execute a skill end-to-end with verification."""
        context = context or {}
        result = ExecutionResult(skill_name=skill.name)
        start_time = time.time()

        if self.config.verbose:
            print(f"[Agent] Starting skill: {skill.name}")

        for iteration in range(self.config.max_iterations):
            if self.config.verbose:
                print(f"[Agent] Iteration {iteration + 1}/{self.config.max_iterations}")

            step_outputs: Dict[str, str] = {}
            all_passed = True

            for step in skill.steps:
                step_result = self._execute_step(step, context, step_outputs)
                result.steps.append(step_result)
                step_outputs[step.id] = step_result.output
                result.total_cost += step_result.cost
                result.total_time_ms += step_result.latency_ms

                if not step_result.passed:
                    all_passed = False
                    if self.config.verbose:
                        print(f"[Agent] Step {step.id} failed: {step_result.error}")

                    # Attempt self-improvement if enabled
                    if skill.self_improve and iteration < self.config.max_iterations - 1:
                        if self.config.verbose:
                            print(f"[Agent] Attempting fix for step {step.id}...")
                        fix_result = self._attempt_fix(skill, step, step_result, context)
                        if fix_result:
                            # Retry this step
                            retry_result = self._execute_step(
                                step, context, step_outputs
                            )
                            result.steps.append(retry_result)
                            step_outputs[step.id] = retry_result.output
                            if not retry_result.passed:
                                break
                        else:
                            break
                    else:
                        break

            if all_passed:
                result.passed = True
                result.final_output = step_outputs.get(skill.steps[-1].id, "")
                if self.config.verbose:
                    print(f"[Agent] Skill '{skill.name}' completed successfully")
                break

        if not result.passed and not result.error:
            result.error = "Max iterations reached without passing"
            if self.config.verbose:
                print(f"[Agent] {result.error}")

        result.total_time_ms = (time.time() - start_time) * 1000

        # Update curator stats
        self.curator.update_skill_stats(skill.name, result.passed, result.total_cost)

        return result

    def _execute_step(
        self,
        step: Step,
        context: Dict[str, Any],
        prior_outputs: Dict[str, str],
    ) -> StepResult:
        """Execute a single step."""
        result = StepResult(step_id=step.id, step_type=step.type, passed=False)

        if step.type == StepType.PROMPT:
            # Build prompt with context
            prompt = self._build_step_prompt(step, context, prior_outputs)
            resp = self.generator.generate(prompt, model=step.model)

            result.output = resp.content
            result.cost = resp.cost
            result.latency_ms = resp.latency_ms
            result.error = resp.error

            if resp.error:
                return result

            # Verify if rule exists
            if step.verification:
                result.verification = self.verifier.verify(
                    step.verification, resp.content, context
                )
                result.passed = result.verification.passed
                if not result.passed:
                    result.error = result.verification.message
            else:
                result.passed = True

        elif step.type == StepType.EXEC:
            result.verification = self.verifier.verify(
                step.verification or self._default_exec_rule(step),
                step.command or "",
            )
            result.passed = result.verification.passed
            result.output = str(result.verification.details or {})

        elif step.type == StepType.READ:
            try:
                with open(step.file_path) as f:
                    result.output = f.read()
                result.passed = True
            except Exception as e:
                result.error = str(e)

        elif step.type == StepType.WRITE:
            try:
                with open(step.file_path, "w") as f:
                    f.write(step.content or "")
                result.passed = True
                result.output = f"Wrote to {step.file_path}"
            except Exception as e:
                result.error = str(e)

        elif step.type == StepType.BRANCH:
            # Evaluate condition
            condition = self._evaluate_condition(step.condition, context, prior_outputs)
            result.passed = True
            result.output = f"branch={'true' if condition else 'false'}"

        elif step.type == StepType.VERIFY:
            if step.verification:
                result.verification = self.verifier.verify(step.verification, "")
                result.passed = result.verification.passed
                result.error = result.verification.message
            else:
                result.passed = True

        return result

    def _build_step_prompt(
        self,
        step: Step,
        context: Dict[str, Any],
        prior_outputs: Dict[str, str],
    ) -> str:
        """Build the prompt for a step."""
        prompt_parts = []

        if step.description:
            prompt_parts.append(f"Task: {step.description}")

        if prior_outputs:
            prompt_parts.append("Previous steps:")
            for step_id, output in prior_outputs.items():
                prompt_parts.append(f"  [{step_id}]: {output[:200]}...")

        if context:
            prompt_parts.append("Context:")
            for key, value in context.items():
                prompt_parts.append(f"  {key}: {value}")

        prompt_parts.append(f"Current instruction: {step.prompt}")

        return "\n\n".join(prompt_parts)

    def _evaluate_condition(
        self,
        condition: Optional[str],
        context: Dict[str, Any],
        prior_outputs: Dict[str, str],
    ) -> bool:
        """Evaluate a branch condition."""
        if not condition:
            return False

        # Simple string-based conditions
        if "success" in condition.lower():
            return True
        return condition in str(context) or condition in str(prior_outputs)

    def _default_exec_rule(self, step: Step):
        """Create default verification rule for exec steps."""
        from ratchet.skill import VerificationRule, VerificationType

        return VerificationRule(
            type=VerificationType.EXIT_CODE,
            expected_code=0,
        )

    def _attempt_fix(
        self,
        skill: Skill,
        failed_step: Step,
        step_result: StepResult,
        context: Dict[str, Any],
    ) -> bool:
        """Attempt to fix a failed step using reflection."""
        # Record the failure
        failure = self.reflector.record_failure(
            skill=skill,
            step_id=failed_step.id,
            error=Exception(step_result.error or "Unknown error"),
            context=context,
        )

        # Get reflection
        reflection = self.reflector.reflect(failure)

        if self.config.verbose:
            print(f"[Agent] Reflection: {reflection.root_cause}")
            print(f"[Agent] Suggestion: {reflection.suggested_fix}")

        # Generate improved prompt
        fix_prompt = f"""
The following step failed:
Step ID: {failed_step.id}
Error: {step_result.error}
Root cause: {reflection.root_cause}

Original prompt:
{failed_step.prompt}

Please generate an improved version of this step that addresses the failure.
Focus on: {reflection.suggested_fix}
"""

        resp = self.generator.generate(fix_prompt)
        if resp.error:
            return False

        # Try to update the step prompt
        new_prompt = self.generator.extract_code(resp.content) or resp.content
        if new_prompt and len(new_prompt) > len(failed_step.prompt or ""):
            # Only update if we got something more substantial
            failed_step.prompt = new_prompt
            return True

        return False
