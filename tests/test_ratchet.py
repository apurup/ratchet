"""
Tests for Ratchet framework
"""

import pytest
from ratchet import Skill, Step, StepType, VerificationRule, VerificationType
from ratchet.generator import Generator, GenerationResult
from ratchet.verifier import Verifier, VerificationResult, Sandbox
from ratchet.reflector import Reflector, FailureRecord
from ratchet.curator import Curator, KnowledgeEntry
from ratchet.agent import Agent, AgentConfig, ExecutionResult


class TestVerifier:
    def test_verification_output_pass(self):
        verifier = Verifier()
        rule = VerificationRule(
            type=VerificationType.OUTPUT,
            must_contain=["def hello"],
        )
        result = verifier.verify(rule, "def hello():\n    return 'hi'")
        assert result.passed is True

    def test_verification_output_fail_missing(self):
        verifier = Verifier()
        rule = VerificationRule(
            type=VerificationType.OUTPUT,
            must_contain=["def hello"],
        )
        result = verifier.verify(rule, "def goodbye():\n    return 'bye'")
        assert result.passed is False

    def test_verification_output_must_not_contain(self):
        verifier = Verifier()
        rule = VerificationRule(
            type=VerificationType.OUTPUT,
            must_not_contain=["traceback", "error"],
        )
        result = verifier.verify(rule, "def hello():\n    return 'hi'")
        assert result.passed is True

    def test_verification_exit_code(self):
        verifier = Verifier()
        rule = VerificationRule(
            type=VerificationType.EXIT_CODE,
            expected_code=0,
        )
        result = verifier.verify(rule, "0")
        assert result.passed is True


class TestSandbox:
    def test_sandbox_python_success(self):
        sandbox = Sandbox()
        result = sandbox.execute("print('hello')", language="python")
        assert result.passed is True
        assert "hello" in result.details.get("stdout", "")

    def test_sandbox_python_syntax_error(self):
        sandbox = Sandbox()
        result = sandbox.execute("print('hello'", language="python")
        assert result.passed is False

    def test_sandbox_bash(self):
        sandbox = Sandbox()
        result = sandbox.execute("echo 'test'", language="bash")
        assert result.passed is True
        assert "test" in result.details.get("stdout", "")


class TestReflector:
    def test_record_failure(self):
        reflector = Reflector(history_path="/tmp/test_reflections.json")
        failure = reflector.record_failure(
            skill=Skill(name="test", description="test"),
            step_id="step1",
            error=Exception("SyntaxError: bad syntax"),
        )
        assert failure.error_type == "SyntaxError"
        assert reflector.reflect(failure).category == "syntax"

    def test_reflect_on_timeout(self):
        reflector = Reflector(history_path="/tmp/test_reflections2.json")
        failure = FailureRecord(
            timestamp="2024-01-01T00:00:00",
            skill_name="test",
            step_id="step1",
            error_type="TimeoutError",
            error_message="Operation timed out",
            context={},
        )
        reflection = reflector.reflect(failure)
        assert reflection.category == "environment"
        assert "timeout" in reflection.root_cause.lower()

    def test_failure_stats(self):
        reflector = Reflector(history_path="/tmp/test_reflections3.json")
        stats = reflector.get_failure_stats()
        assert "total" in stats
        assert "by_category" in stats


class TestCurator:
    def test_store_and_retrieve(self):
        curator = Curator(data_dir="/tmp/test_kb")
        entry = curator.store(
            skill_name="test_skill",
            content="def hello(): return 'hi'",
            tags=["python", "utility"],
        )
        assert entry.id is not None

        results = curator.retrieve("hello", tags=["python"])
        assert len(results) >= 1

    def test_register_skill(self):
        curator = Curator(data_dir="/tmp/test_kb2")
        skill = Skill(name="test", description="test")
        registered = curator.register_skill(skill)
        assert registered.name == "test"

        retrieved = curator.get_skill("test")
        assert retrieved is not None
        assert retrieved.name == "test"


class TestSkill:
    def test_get_step(self):
        skill = Skill(
            name="test",
            description="test",
            steps=[
                Step(id="step1", type=StepType.PROMPT, prompt="test"),
                Step(id="step2", type=StepType.EXEC, command="ls"),
            ],
        )
        step = skill.get_step("step2")
        assert step is not None
        assert step.id == "step2"
        assert step.command == "ls"

    def test_get_next_steps(self):
        skill = Skill(
            name="test",
            description="test",
            steps=[
                Step(id="step1", type=StepType.PROMPT, prompt="test"),
                Step(id="step2", type=StepType.EXEC, command="ls"),
                Step(id="step3", type=StepType.PROMPT, prompt="done"),
            ],
        )
        next_steps = skill.get_next_steps("step1")
        assert "step2" in next_steps

    def test_record_success_failure(self):
        skill = Skill(name="test", description="test")
        skill.record_success(0.5)
        skill.record_success(0.5)
        skill.record_failure(0.25)
        assert skill.success_count == 2
        assert skill.failure_count == 1
        assert skill.total_cost == 1.25
        assert skill.success_rate == 2 / 3


class TestAgent:
    def test_agent_config_defaults(self):
        config = AgentConfig()
        assert config.max_iterations == 10
        assert config.max_cost_per_step == 5.0
        assert config.verbose is True

    def test_simple_skill_execution(self):
        agent = Agent(
            generator=Generator(provider="minimax"),
            verifier=Verifier(),
        )

        # Simple skill that doesn't call LLM (verification-only)
        skill = Skill(
            name="verify_only",
            description="Test skill",
            steps=[
                Step(
                    id="check",
                    type=StepType.EXEC,
                    command="echo 'hello'",
                    verification=VerificationRule(
                        type=VerificationType.OUTPUT,
                        must_contain=["hello"],
                    ),
                ),
            ],
        )

        result = agent.run(skill)
        assert len(result.steps) >= 1


class TestGenerator:
    def test_generate_returns_result(self):
        gen = Generator(provider="minimax")
        # Test that it returns a GenerationResult structure
        result = gen.generate("Say hello", model="MiniMax-M2.7")
        assert isinstance(result, GenerationResult)
        assert hasattr(result, "content")
        assert hasattr(result, "cost")
        assert hasattr(result, "latency_ms")

    def test_extract_code(self):
        gen = Generator(provider="minimax")
        content = "Here is the code:\n```python\ndef hello():\n    return 'hi'\n```"
        code = gen.extract_code(content, "python")
        assert "def hello" in code
        assert "```" not in code
