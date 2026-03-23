"""
Curator - Knowledge base for storing and retrieving repair lessons
"""

import json
import os
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime
from dataclasses import dataclass, field, asdict


@dataclass
class RepairLesson:
    id: str
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    failure_pattern: str = ""
    error_signature: str = ""
    context: str = ""
    repair_strategy: str = ""
    fix_code: Optional[str] = None
    prompt_adjustment: Optional[str] = None
    model_used: str = ""
    attempts: int = 1
    success_rate: float = 1.0
    times_applied: int = 0
    times_succeeded: int = 0
    times_failed: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


class Curator:
    """Knowledge base for storing and retrieving repair lessons."""
    def __init__(self, storage_path: str = "./data/curator.json"):
        self.storage_path = storage_path
        self.lessons: List[RepairLesson] = []
        os.makedirs(os.path.dirname(storage_path) or "./data", exist_ok=True)
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.lessons = [RepairLesson(**d) for d in data]
            except: self.lessons = []

    def _save(self):
        with open(self.storage_path, "w") as f:
            json.dump([l.to_dict() for l in self.lessons], f, indent=2)

    def add_lesson(self, lesson: RepairLesson):
        existing = self.find_similar(lesson.failure_pattern, lesson.error_signature)
        if existing:
            existing.attempts += 1
            if lesson.success_rate > 0.5: existing.success_rate = (existing.success_rate * (existing.attempts-1) + lesson.success_rate) / existing.attempts
        else:
            self.lessons.append(lesson)
        self._save()

    def find_similar(self, failure_pattern: str, error_signature: str, limit: int = 5) -> Optional[RepairLesson]:
        matches = []
        for l in self.lessons:
            if failure_pattern.lower() in l.failure_pattern.lower() or l.failure_pattern.lower() in failure_pattern.lower():
                matches.append((l, l.success_rate))
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches[0][0] if matches else None

    def record_application(self, lesson_id: str, succeeded: bool):
        for l in self.lessons:
            if l.id == lesson_id:
                l.times_applied += 1
                if succeeded: l.times_succeeded += 1
                else: l.times_failed += 1
                l.success_rate = l.times_succeeded / l.times_applied if l.times_applied > 0 else 0
                self._save()
                return

    def get_stats(self) -> Dict[str, Any]:
        total = len(self.lessons)
        if total == 0: return {"total_lessons": 0}
        return {
            "total_lessons": total,
            "total_applications": sum(l.times_applied for l in self.lessons),
            "average_success_rate": sum(l.success_rate for l in self.lessons) / total,
        }


# Hermes compatibility — import and re-export HermesCurator from deterministic
from ratchet.deterministic.curator import HermesCurator
