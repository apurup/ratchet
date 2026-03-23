"""
Ratchet-compatible Curator — repair lesson KB with Ratchet knowledge_base integration.
"""

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ratchet.deterministic.reflector import FailureAnalysis

try:
    from hermes.knowledge_base import HermesKnowledgeBase
except ImportError:
    HermesKnowledgeBase = None


@dataclass
class RepairLesson:
    """
    A learned repair lesson from a failed execution.

    Matches Ratchet's RepairLesson for compatibility.
    Stored in curator.json (file-backed, simple) and optionally in Ratchet's KB.
    """
    id: str
    created_at: str
    failure_pattern: str
    error_signature: str
    context: str
    repair_strategy: str
    fix_code: Optional[str] = None
    prompt_adjustment: Optional[str] = None
    model_used: str = ""
    attempts: int = 1
    success_rate: float = 1.0
    times_applied: int = 0
    times_succeeded: int = 0
    times_failed: int = 0
    skill_name: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "failure_pattern": self.failure_pattern,
            "error_signature": self.error_signature,
            "context": self.context,
            "repair_strategy": self.repair_strategy,
            "fix_code": self.fix_code,
            "prompt_adjustment": self.prompt_adjustment,
            "model_used": self.model_used,
            "attempts": self.attempts,
            "success_rate": self.success_rate,
            "times_applied": self.times_applied,
            "times_succeeded": self.times_succeeded,
            "times_failed": self.times_failed,
            "skill_name": self.skill_name,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RepairLesson":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class RatchetCurator:
    """
    Knowledge base for repair lessons with Ratchet integration.

    File-backed (curator.json) for simplicity and portability.
    Optionally indexes into Ratchet's FTS5 KnowledgeBase for cross-session recall.
    """

    def __init__(
        self,
        storage_path: str = None,
        kb: Any = None,  # HermesKnowledgeBase — optional
    ):
        self.storage_path = storage_path or os.path.join(
            os.getenv("HERMES_HOME", os.path.expanduser("~/.hermes")),
            "data", "curator.json"
        )
        self._kb = kb
        self.lessons: List[RepairLesson] = []

        os.makedirs(os.path.dirname(self.storage_path) or "./data", exist_ok=True)
        self._load()

    def _load(self):
        """Load lessons from JSON file."""
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.lessons = [RepairLesson.from_dict(d) for d in data]
            except (json.JSONDecodeError, TypeError):
                self.lessons = []

    def _save(self):
        """Persist lessons to JSON file."""
        with open(self.storage_path, "w") as f:
            json.dump([l.to_dict() for l in self.lessons], f, indent=2)

    def add_lesson(
        self,
        failure_pattern: str,
        error_signature: str,
        context: str,
        repair_strategy: str,
        model_used: str = "",
        fix_code: Optional[str] = None,
        prompt_adjustment: Optional[str] = None,
        skill_name: Optional[str] = None,
    ) -> RepairLesson:
        """
        Add a new lesson or update an existing similar one.

        If a lesson with the same failure_pattern + error_signature exists,
        increment attempts and update success_rate. Otherwise create new.
        """
        existing = self.find_similar(failure_pattern, error_signature, limit=1)
        now = datetime.utcnow().isoformat()

        if existing:
            existing.attempts += 1
            if existing.success_rate > 0:
                existing.success_rate = (
                    existing.success_rate * (existing.attempts - 1)
                ) / existing.attempts
            # Update if new info is richer
            if repair_strategy and not existing.repair_strategy:
                existing.repair_strategy = repair_strategy
            if fix_code:
                existing.fix_code = fix_code
            self._save()
            return existing
        else:
            lesson = RepairLesson(
                id=str(uuid.uuid4()),
                created_at=now,
                failure_pattern=failure_pattern,
                error_signature=error_signature,
                context=context,
                repair_strategy=repair_strategy,
                fix_code=fix_code,
                prompt_adjustment=prompt_adjustment,
                model_used=model_used,
                skill_name=skill_name,
            )
            self.lessons.append(lesson)
            self._save()

            # Also index in Ratchet KB if available
            if self._kb and HermesKnowledgeBase:
                self._index_in_kb(lesson)

            return lesson

    def find_similar(
        self,
        failure_pattern: str,
        error_signature: str,
        limit: int = 5,
    ) -> Optional[RepairLesson]:
        """
        Find lessons matching failure_pattern or error_signature.

        Returns the highest-success-rate match.
        """
        matches = []
        fp_lower = failure_pattern.lower()
        es_lower = error_signature.lower()

        for lesson in self.lessons:
            if fp_lower and fp_lower in lesson.failure_pattern.lower():
                matches.append((lesson, lesson.success_rate))
            elif es_lower and es_lower in lesson.error_signature.lower():
                matches.append((lesson, lesson.success_rate))
            elif self._pattern_overlap(fp_lower, lesson.failure_pattern.lower()):
                matches.append((lesson, lesson.success_rate * 0.8))

        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0] if matches else None

    def _pattern_overlap(self, a: str, b: str) -> bool:
        """Check if two patterns share significant overlap."""
        if not a or not b:
            return False
        # Check for shared significant tokens (length >= 4)
        a_words = set(w for w in a.split() if len(w) >= 4)
        b_words = set(w for w in b.split() if len(w) >= 4)
        return bool(a_words & b_words)

    def find_for_task(
        self,
        task: str,
        skill_name: Optional[str] = None,
        limit: int = 5,
    ) -> List[RepairLesson]:
        """
        Find all lessons relevant to a task.

        Considers skill_name for scoped matching.
        """
        matches = []
        task_lower = task.lower()

        for lesson in self.lessons:
            score = 0
            if skill_name and lesson.skill_name == skill_name:
                score += 10
            if lesson.failure_pattern.lower() in task_lower:
                score += 5
            if lesson.context and lesson.context.lower() in task_lower:
                score += 3
            if any(w in task_lower for w in lesson.failure_pattern.lower().split() if len(w) >= 4):
                score += 1

            if score > 0:
                matches.append((lesson, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return [m for m, _ in matches[:limit]]

    def record_application(
        self,
        lesson_id: str,
        succeeded: bool,
    ):
        """
        Record that a lesson was applied to a task.

        Updates times_applied, times_succeeded/times_failed, and recomputes success_rate.
        """
        for lesson in self.lessons:
            if lesson.id == lesson_id:
                lesson.times_applied += 1
                if succeeded:
                    lesson.times_succeeded += 1
                else:
                    lesson.times_failed += 1

                total = lesson.times_succeeded + lesson.times_failed
                lesson.success_rate = (
                    lesson.times_succeeded / total if total > 0 else 0.0
                )
                self._save()
                return

    def _index_in_kb(self, lesson: RepairLesson):
        """Index a lesson in Ratchet's FTS5 knowledge base."""
        try:
            self._kb.add_repair_lesson(lesson)
        except Exception:
            pass  # Non-fatal — KB indexing is best-effort

    def get_stats(self) -> Dict[str, Any]:
        """Return curator statistics."""
        total = len(self.lessons)
        if total == 0:
            return {"total_lessons": 0}

        return {
            "total_lessons": total,
            "total_applications": sum(l.times_applied for l in self.lessons),
            "total_succeeded": sum(l.times_succeeded for l in self.lessons),
            "average_success_rate": sum(l.success_rate for l in self.lessons) / total,
            "by_category": self._by_category(),
        }

    def _by_category(self) -> Dict[str, int]:
        """Count lessons by failure pattern category (first word before underscore)."""
        cats: Dict[str, int] = {}
        for lesson in self.lessons:
            cat = lesson.failure_pattern.split("_")[0] or "unknown"
            cats[cat] = cats.get(cat, 0) + 1
        return cats
