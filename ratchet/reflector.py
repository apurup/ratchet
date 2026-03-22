"""
Reflector - Failure analysis and self-improvement
"""

import hashlib
import json
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from ratchet.skill import Skill


@dataclass
class FailureRecord:
    timestamp: str
    skill_name: str
    step_id: str
    error_type: str
    error_message: str
    context: Dict[str, Any]
    fix_attempted: bool = False
    fix_succeeded: bool = False
    fix_description: Optional[str] = None


@dataclass
class Reflection:
    root_cause: str
    category: str  # "syntax", "logic", "api", "environment", "verification"
    suggested_fix: str
    confidence: float  # 0.0 - 1.0
    similar_failures: int = 0


class Reflector:
    """Analyzes failures and extracts patterns for self-improvement."""

    def __init__(self, history_path: str = "./data/reflection_history.json"):
        self.history_path = history_path
        self.failures: List[FailureRecord] = []
        self._load_history()

    def _load_history(self):
        """Load failure history from disk."""
        try:
            with open(self.history_path) as f:
                data = json.load(f)
                self.failures = [FailureRecord(**r) for r in data]
        except FileNotFoundError:
            self.failures = []

    def _save_history(self):
        """Persist failure history to disk."""
        import os
        os.makedirs(os.path.dirname(self.history_path) or ".", exist_ok=True)
        with open(self.history_path, "w") as f:
            json.dump([vars(r) for r in self.failures], f, indent=2)

    def record_failure(
        self,
        skill: Skill,
        step_id: str,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
    ) -> FailureRecord:
        """Record a failure for analysis."""
        record = FailureRecord(
            timestamp=datetime.utcnow().isoformat(),
            skill_name=skill.name,
            step_id=step_id,
            error_type=type(error).__name__,
            error_message=str(error),
            context=context or {},
        )
        self.failures.append(record)
        self._save_history()
        return record

    def reflect(
        self,
        failure: FailureRecord,
    ) -> Reflection:
        """Analyze a failure and generate insights."""
        error_msg = failure.error_message.lower()
        error_type = failure.error_type.lower()

        # Categorize the failure
        if "syntax" in error_msg or error_type == "syntaxerror":
            category = "syntax"
            root_cause = "Code contains syntax errors"
            suggested_fix = "Review the generated code for syntax errors"
        elif "import" in error_msg or "modulenotfound" in error_msg:
            category = "import"
            root_cause = "Missing or incorrect import"
            suggested_fix = "Check required dependencies and module paths"
        elif "timeout" in error_msg or "timed out" in error_msg:
            category = "environment"
            root_cause = "Operation timed out"
            suggested_fix = "Increase timeout or optimize the operation"
        elif "assertion" in error_msg or "test" in error_msg:
            category = "verification"
            root_cause = "Verification failed"
            suggested_fix = "Review test assertions and expected outputs"
        elif "api" in error_msg or "request" in error_msg:
            category = "api"
            root_cause = "API request failed"
            suggested_fix = "Check API keys, endpoints, and request format"
        else:
            category = "logic"
            root_cause = "Code logic error"
            suggested_fix = "Review generated code logic"

        # Check for similar failures
        similar = sum(
            1
            for f in self.failures
            if f.skill_name == failure.skill_name
            and f.error_type == failure.error_type
        )

        # Confidence based on history
        confidence = min(0.5 + (similar * 0.1), 0.95)

        return Reflection(
            root_cause=root_cause,
            category=category,
            suggested_fix=suggested_fix,
            confidence=confidence,
            similar_failures=similar,
        )

    def suggest_improvement(
        self,
        skill: Skill,
        failures: List[FailureRecord],
    ) -> Dict[str, Any]:
        """Suggest improvements to a skill based on failure patterns."""
        if not failures:
            return {"action": "none", "reason": "No failures recorded"}

        # Group by step
        step_failures: Dict[str, int] = {}
        for f in failures:
            step_id = f.step_id
            step_failures[step_id] = step_failures.get(step_id, 0) + 1

        # Find weakest step
        weakest_step = max(step_failures, key=step_failures.get)

        return {
            "action": "add_verification",
            "target_step": weakest_step,
            "reason": f"Most failures ({step_failures[weakest_step]}) occur at this step",
            "suggestion": "Add more specific verification rules",
        }

    def get_failure_stats(self) -> Dict[str, Any]:
        """Get aggregate failure statistics."""
        if not self.failures:
            return {"total": 0, "by_category": {}, "by_skill": {}}

        by_category: Dict[str, int] = {}
        by_skill: Dict[str, int] = {}

        for f in self.failures:
            reflection = self.reflect(f)
            by_category[reflection.category] = by_category.get(reflection.category, 0) + 1
            by_skill[f.skill_name] = by_skill.get(f.skill_name, 0) + 1

        return {
            "total": len(self.failures),
            "by_category": by_category,
            "by_skill": by_skill,
        }
