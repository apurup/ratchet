"""
Hermes-compatible Reflector — failure analysis + improvement hypotheses.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ratchet.deterministic.generator import HermesGenerator


class FailureCategory:
    SYNTAX = "syntax"
    LOGIC = "logic"
    EDGE_CASE = "edge_case"
    FORMAT = "format"
    TIMEOUT = "timeout"
    VERIFICATION = "verification"
    MEMORY = "memory"
    SKILL = "skill"
    UNKNOWN = "unknown"


CATEGORY_KEYWORDS = {
    FailureCategory.SYNTAX: ["syntaxerror", "parseerror", "indentation", "expected token", "invalid syntax"],
    FailureCategory.LOGIC: ["indexerror", "keyerror", "attributeerror", "valueerror", "typeerror",
                             "none has no", "is not defined", "unsupported operand"],
    FailureCategory.EDGE_CASE: ["index out of range", "empty", "division by zero", "keyerror",
                                  "list index out of range", "tuple index out of range"],
    FailureCategory.FORMAT: ["expected output", "mismatch", "wrong format", "incorrect format"],
    FailureCategory.TIMEOUT: ["timeout", "timed out", "took too long", "deadline exceeded"],
    FailureCategory.VERIFICATION: ["assertionerror", "assert", "expected", "got", "test failed",
                                    "verification failed", "not a valid"],
    FailureCategory.MEMORY: ["memory", "memories", "recall", "forgot", "remember"],
    FailureCategory.SKILL: ["skill", "workflow", "step", "skill not found", "invalid skill"],
}


@dataclass
class FailureAnalysis:
    """Matches Ratchet's FailureAnalysis for compatibility."""
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



class HermesReflector:
    """
    Analyzes execution failures and generates improvement hypotheses.

    Uses rule-based classification by default (fast, deterministic).
    Optionally uses LLM for deeper analysis when the model is available.
    """

    def __init__(self, generator: Optional["HermesGenerator"] = None):
        self._generator = generator

    def analyze_failure(
        self,
        code: str,
        error: str,
        verification_output: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> FailureAnalysis:
        """
        Classify a failure and generate a repair hypothesis.

        Uses keyword matching against FailureCategory patterns.
        Falls back to UNKNOWN with medium confidence.
        """
        combined = f"{error} {verification_output}".lower()
        context = context or {}

        # Find matching category
        category = FailureCategory.UNKNOWN
        for cat, keywords in CATEGORY_KEYWORDS.items():
            if any(kw.lower() in combined for kw in keywords):
                category = cat
                break

        # Build specific diagnosis
        root_cause, suggested_fix = self._diagnose(category, error, combined, context)

        # Build hypothesis
        hypothesis = self._build_hypothesis(category, error, context)

        # Estimate confidence based on category match strength
        confidence = 0.5 + 0.1 * sum(
            1 for kw in CATEGORY_KEYWORDS.get(category, [])
            if kw.lower() in combined
        )
        confidence = min(confidence, 0.95)

        return FailureAnalysis(
            category=category,
            description=f"Failed ({category}): {error[:100]}",
            root_cause=root_cause,
            hypothesis=hypothesis,
            suggested_fix=suggested_fix,
            confidence=confidence,
            examples=[error[:200]] if error else [],
        )

    def _diagnose(
        self,
        category: str,
        error: str,
        combined: str,
        context: Dict[str, Any],
    ) -> tuple:
        """Map category + error to root cause and suggested fix."""
        fixes = {
            FailureCategory.SYNTAX: (
                "Python syntax or indentation error",
                "Check indentation (use 4 spaces), closing brackets, and colons. "
                "Review the error line and preceding lines for missing or extra characters."
            ),
            FailureCategory.LOGIC: (
                "Runtime error accessing missing data or wrong type",
                "Add None checks, validate input types, and handle missing keys with .get() "
                "or explicit conditional checks before access."
            ),
            FailureCategory.EDGE_CASE: (
                "Edge case not handled (empty input, zero division, out-of-range)",
                "Add guards for empty collections, zero values, and boundary conditions. "
                "Test with edge inputs: [], {}, 0, None, negative numbers."
            ),
            FailureCategory.FORMAT: (
                "Output format doesn't match expected specification",
                "Review the expected format exactly. Check whitespace, case, and data structure shape."
            ),
            FailureCategory.TIMEOUT: (
                "Execution exceeded the time limit",
                "Optimize the algorithm, reduce data size, or increase timeout. "
                "Add early exit conditions to loops."
            ),
            FailureCategory.VERIFICATION: (
                "Output doesn't match expected result",
                "Trace the actual vs expected values. Add debug prints to understand "
                "the intermediate state. Review the logic against the spec."
            ),
            FailureCategory.MEMORY: (
                "Failure related to memory or context retrieval",
                "Check that the memory tool is returning correct data. "
                "Verify context injection and that session search results are relevant."
            ),
            FailureCategory.SKILL: (
                "Skill execution or workflow step failure",
                "Verify the skill steps are in the correct order and each step's "
                "verification passed. Check for missing skill files or broken references."
            ),
            FailureCategory.UNKNOWN: (
                "Unknown error",
                "Review the full error message and traceback. Simplify the code to isolate "
                "the failing component. Add minimal test cases."
            ),
        }

        root_cause, suggested_fix = fixes.get(category, fixes[FailureCategory.UNKNOWN])

        # Specific error refinements
        if "indentation" in combined:
            root_cause = "Indentation error in Python code"
            suggested_fix = "Use consistent 4-space indentation. Check for mixed tabs/spaces."

        elif "timeout" in combined:
            root_cause = "Execution timeout exceeded"
            suggested_fix = "Optimize performance, add early returns, or increase timeout setting."

        return root_cause, suggested_fix

    def _build_hypothesis(
        self,
        category: str,
        error: str,
        context: Dict[str, Any],
    ) -> str:
        """Generate a human-readable hypothesis sentence."""
        task = context.get("task", "the task")
        skill_name = context.get("skill_name")

        skill_str = f" in skill '{skill_name}'" if skill_name else ""

        category_hints = {
            FailureCategory.SYNTAX: f"The code{skill_str} has a syntax error preventing execution.",
            FailureCategory.LOGIC: f"The code{skill_str} crashes at runtime due to a logic error.",
            FailureCategory.EDGE_CASE: f"The code{skill_str} doesn't handle an edge case in the input.",
            FailureCategory.FORMAT: f"The output format doesn't match what was expected.",
            FailureCategory.TIMEOUT: f"The code{skill_str} ran too long and was terminated.",
            FailureCategory.VERIFICATION: f"The code{skill_str} produces incorrect output.",
            FailureCategory.MEMORY: f"The memory/retrieval step failed for {task}.",
            FailureCategory.SKILL: f"The skill workflow failed at a step for {task}.",
            FailureCategory.UNKNOWN: f"Execution failed for unknown reasons during {task}.",
        }

        return category_hints.get(category, category_hints[FailureCategory.UNKNOWN])

    def generate_hypothesis(
        self,
        past_failures: List[FailureAnalysis],
        current_task: str,
    ) -> str:
        """
        Generate a contextual hypothesis based on historical failure patterns.

        Looks at the most common failure category across past failures
        and generates a targeted hint.
        """
        if not past_failures:
            return f"First attempt at: {current_task}"

        category_counts: Dict[str, int] = {}
        for f in past_failures:
            category_counts[f.category] = category_counts.get(f.category, 0) + 1

        most_common_cat = max(category_counts.items(), key=lambda x: x[1])
        cat_name = most_common_cat[0].replace("_", " ")

        return (
            f"Task has failed {most_common_cat[1]}x with {cat_name} errors. "
            f"{past_failures[-1].hypothesis}"
        )
