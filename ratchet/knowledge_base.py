"""
Knowledge Base - Structured storage for domain knowledge
"""

import json
import os
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class KBEntry:
    id: str
    topic: str
    subtopic: str
    title: str
    content: str
    summary: str
    tags: List[str]
    sources: List[str]
    created_at: str
    version: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "topic": self.topic,
            "subtopic": self.subtopic,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "tags": self.tags,
            "sources": self.sources,
            "created_at": self.created_at,
            "version": self.version,
        }


class KnowledgeBase:
    """Local KB for Ratchet agents - no external calls needed."""

    def __init__(self, storage_path: str = "./data/knowledge_base.json"):
        self.storage_path = storage_path
        self.entries: List[KBEntry] = []
        self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r") as f:
                    data = json.load(f)
                    self.entries = [KBEntry(**e) for e in data]
            except:
                self.entries = []

    def _save(self):
        os.makedirs(os.path.dirname(self.storage_path) or "./data", exist_ok=True)
        with open(self.storage_path, "w") as f:
            json.dump([e.to_dict() for e in self.entries], f, indent=2)

    def add(self, entry: KBEntry):
        existing = [e for e in self.entries if e.topic == entry.topic and e.subtopic == entry.subtopic]
        if existing:
            existing[0].content = entry.content
            existing[0].summary = entry.summary
            existing[0].version = entry.version
        else:
            self.entries.append(entry)
        self._save()

    def lookup(self, query: str, limit: int = 5) -> List[KBEntry]:
        q = query.lower()
        scored = []
        for e in self.entries:
            score = 0
            if q in e.topic.lower(): score += 10
            if q in e.title.lower(): score += 5
            if q in e.summary.lower(): score += 3
            if q in e.content.lower(): score += 1
            if score > 0:
                scored.append((e, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [e for e, _ in scored[:limit]]

    def lookup_by_topic(self, topic: str) -> List[KBEntry]:
        return [e for e in self.entries if e.topic.lower() == topic.lower()]

    def get_all_topics(self) -> List[str]:
        return sorted(set(e.topic for e in self.entries))

    def stats(self) -> dict:
        return {
            "total_entries": len(self.entries),
            "topics": len(self.get_all_topics()),
            "topic_list": self.get_all_topics(),
        }
