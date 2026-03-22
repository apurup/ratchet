"""
Reflector - Analyzes failures and generates improvement hypotheses
"""

from typing import Optional, Dict, Any, List
from dataclasses import dataclass


class FailureCategory:
    SYNTAX = "syntax"
    LOGIC = "logic"
    EDGE_CASE = "edge_case"
    FORMAT = "format"
    TIMEOUT = "timeout"
    VERIFICATION = "verification"
    UNKNOWN = "unknown"


@dataclass
class FailureAnalysis:
    category: str
    description: str
    root_cause: str
    hypothesis: str
    suggested_fix: str
    confidence: float
    examples: List[str] = None

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "description": self.description,
            "root_cause": self.root_cause,
            "hypothesis": self.hypothesis,
            "suggested_fix": self.suggested_fix,
            "confidence": self.confidence,
            "examples": self.examples or [],
        }


class Reflector:
    """Analyzes execution failures and generates improvement hypotheses."""
    def __init__(self, model=None):
        self.model = model

    def analyze_failure(self, code: str, error: str, verification_output: str, context: Optional[Dict[str, Any]] = None) -> FailureAnalysis:
        combined = f"{error} {verification_output}".lower()
        if any(x in combined for x in ["syntaxerror", "parseerror", "indentation"]):
            cat, cause, fix = "syntax", "Python syntax error", "Fix indentation and syntax"
        elif any(x in combined for x in ["assertionerror", "assert", "expected", "got"]):
            cat, cause, fix = "verification", "Output mismatch", "Review expected vs actual output"
        elif "timeout" in combined:
            cat, cause, fix = "timeout", "Execution exceeded limit", "Optimize or increase timeout"
        elif any(x in combined for x in ["indexerror", "keyerror", "attributeerror"]):
            cat, cause, fix = "logic", "Missing data access", "Add None checks"
        elif any(x in combined for x in ["valueerror", "typeerror"]):
            cat, cause, fix = "logic", "Wrong type or value", "Add input validation"
        else:
            cat, cause, fix = "unknown", "Unknown error", "Review code and error message"
        return FailureAnalysis(
            category=cat, description=f"Failed: {error[:80]}", root_cause=cause,
            hypothesis=f"Failure due to {cause}", suggested_fix=fix, confidence=0.6,
            examples=[error[:200]] if error else [],
        )

    def generate_hypothesis(self, past_failures: List[FailureAnalysis], current_task: str) -> str:
        if not past_failures: return f"First attempt at: {current_task}"
        cats = {}
        for f in past_failures:
            cats[f.category] = cats.get(f.category, 0) + 1
        most_common = max(cats.items(), key=lambda x: x[1])
        return f"Task has failed {most_common[1]}x with {most_common[0]} errors. {past_failures[-1].hypothesis}"
