"""
Curator - Knowledge base and skill management
"""

import os
import json
import hashlib
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from ratchet.skill import Skill, Step


@dataclass
class KnowledgeEntry:
    id: str
    skill_name: str
    content: str
    created_at: str
    tags: List[str] = field(default_factory=list)
    success_rate: float = 0.0
    usage_count: int = 0
    verified: bool = False


class Curator:
    """Knowledge base for learned patterns and successful solutions."""

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = data_dir
        self.entries: Dict[str, KnowledgeEntry] = {}
        self.skills: Dict[str, Skill] = {}
        self._ensure_data_dir()
        self._load()

    def _ensure_data_dir(self):
        """Ensure data directory exists."""
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.data_dir, "knowledge").mkdir(parents=True, exist_ok=True)

    def _load(self):
        """Load knowledge base from disk."""
        kb_path = Path(self.data_dir) / "knowledge" / "base.json"
        if kb_path.exists():
            with open(kb_path) as f:
                data = json.load(f)
                self.entries = {e["id"]: KnowledgeEntry(**e) for e in data}

        skills_path = Path(self.data_dir) / "skills.json"
        if skills_path.exists():
            with open(skills_path) as f:
                data = json.load(f)
                for name, skill_data in data.items():
                    self.skills[name] = Skill(**skill_data)

    def _save(self):
        """Persist knowledge base to disk."""
        kb_path = Path(self.data_dir) / "knowledge" / "base.json"
        with open(kb_path, "w") as f:
            json.dump([vars(e) for e in self.entries.values()], f, indent=2)

        skills_path = Path(self.data_dir) / "skills.json"
        with open(skills_path, "w") as f:
            json.dump({name: vars(s) for name, s in self.skills.items()}, f, indent=2)

    def _compute_id(self, content: str) -> str:
        """Generate a content ID."""
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def store(
        self,
        skill_name: str,
        content: str,
        tags: Optional[List[str]] = None,
    ) -> KnowledgeEntry:
        """Store a new knowledge entry."""
        entry = KnowledgeEntry(
            id=self._compute_id(content),
            skill_name=skill_name,
            content=content,
            created_at=datetime.utcnow().isoformat(),
            tags=tags or [],
        )
        self.entries[entry.id] = entry
        self._save()
        return entry

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        tags: Optional[List[str]] = None,
    ) -> List[KnowledgeEntry]:
        """Retrieve relevant knowledge entries."""
        results = []

        for entry in self.entries.values():
            if tags and not any(t in entry.tags for t in tags):
                continue

            # Simple keyword matching score
            query_words = set(query.lower().split())
            content_words = set(entry.content.lower().split())
            overlap = len(query_words & content_words)

            if overlap > 0:
                results.append((overlap, entry))

        results.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in results[:top_k]]

    def register_skill(self, skill: Skill) -> Skill:
        """Register a skill for tracking and improvement."""
        self.skills[skill.name] = skill
        self._save()
        return skill

    def get_skill(self, name: str) -> Optional[Skill]:
        """Get a registered skill by name."""
        return self.skills.get(name)

    def list_skills(self) -> List[Skill]:
        """List all registered skills."""
        return list(self.skills.values())

    def update_skill_stats(
        self,
        skill_name: str,
        success: bool,
        cost: float,
    ):
        """Update skill statistics after execution."""
        skill = self.skills.get(skill_name)
        if skill:
            if success:
                skill.record_success(cost)
            else:
                skill.record_failure(cost)
            self._save()

    def get_best_skill(self, trigger: str) -> Optional[Skill]:
        """Get the best-performing skill for a trigger pattern."""
        candidates = [
            s for s in self.skills.values()
            if s.trigger_pattern and trigger in s.trigger_pattern
        ]
        if not candidates:
            return None

        return max(candidates, key=lambda s: s.success_rate)

    def export_knowledge(
        self,
        output_path: str,
        format: str = "json",
    ):
        """Export knowledge base."""
        if format == "json":
            with open(output_path, "w") as f:
                json.dump([vars(e) for e in self.entries.values()], f, indent=2)
        elif format == "markdown":
            with open(output_path, "w") as f:
                for entry in self.entries.values():
                    f.write(f"## {entry.id}\n")
                    f.write(f"**Skill:** {entry.skill_name}\n")
                    f.write(f"**Tags:** {', '.join(entry.tags)}\n")
                    f.write(f"**Created:** {entry.created_at}\n\n")
                    f.write(f"```\n{entry.content}\n```\n\n")
