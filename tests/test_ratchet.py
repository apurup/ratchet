"""
Tests for Ratchet framework
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.skill import Skill, Step, StepType
from ratchet.curator import Curator, RepairLesson
from ratchet.reflector import Reflector, FailureAnalysis
from ratchet.verifier import Verifier, VerificationStatus


class TestSkill:
    def test_skill_creation(self):
        skill = Skill(name="test", description="A test skill", steps=[Step(id="s1", type=StepType.PROMPT)])
        assert skill.name == "test"
        assert len(skill.steps) == 1

    def test_get_step(self):
        skill = Skill(name="test", description="test", steps=[Step(id="a", type=StepType.PROMPT), Step(id="b", type=StepType.EXEC)])
        assert skill.get_step("a").id == "a"
        assert skill.get_step("c") is None

    def test_success_tracking(self):
        skill = Skill(name="test", description="test", steps=[Step(id="s1", type=StepType.PROMPT)])
        assert skill.success_rate == 0.0
        skill.record_success(0.01)
        assert skill.success_count == 1


class TestCurator:
    def test_add_and_find(self, tmp_path):
        db = str(tmp_path / "curator.json")
        curator = Curator(storage_path=db)
        lesson = RepairLesson(id="t1", failure_pattern="syntax", error_signature="SyntaxError", context="test", repair_strategy="fix it", model_used="test")
        curator.add_lesson(lesson)
        assert len(curator.lessons) == 1
        found = curator.find_similar("syntax", "SyntaxError")
        assert found is not None


class TestReflector:
    def test_heuristic_analysis(self):
        r = Reflector()
        a = r.analyze_failure(code="def foo:\n  return 1", error="SyntaxError", verification_output="")
        assert a.category == "syntax"
        assert a.confidence > 0


class TestVerifier:
    def test_simple_execution(self):
        v = Verifier()
        result = v.execute("print('hello')", language="python")
        assert result.status == VerificationStatus.PASS

    def test_failing_code(self):
        v = Verifier()
        result = v.execute("raise ValueError('test')", language="python")
        assert result.status == VerificationStatus.FAIL


if __name__ == "__main__":
    pytest.main([__file__, "-v"])