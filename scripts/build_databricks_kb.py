#!/usr/bin/env python3
"""
Build Databricks Knowledge Base
Fetches Databricks docs and populates the KB with comprehensive knowledge.
"""

import os
import sys
import json
import uuid
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ratchet.knowledge_base import KnowledgeBase, KBEntry
from ratchet.models import MiniMaxClient
from datetime import datetime


DATABRICKS_TOPICS = {
    "unity-catalog": {
        "name": "Unity Catalog",
        "subtopics": [
            ("metastore-setup", "metastore creation and assignment"),
            ("catalogs-schemas", "catalogs and schemas hierarchy"),
            ("tables-views", "managed and external tables"),
            ("permissions", "GRANT statements and privileges"),
            ("lineage", "data lineage tracking"),
            ("governance", "governance policies and classification"),
        ]
    },
    "delta-lake": {
        "name": "Delta Lake",
        "subtopics": [
            ("acid-transactions", "ACID transaction support"),
            ("time-travel", "DESCRIBE HISTORY and time travel queries"),
            ("optimize-compaction", "OPTIMIZE command and file compaction"),
            ("z-order", "Z-ORDER BY for data skipping"),
            ("schema-evolution", "schema enforcement and evolution"),
            ("merge-upsert", "MERGE command for upserts"),
        ]
    },
    "spark": {
        "name": "Apache Spark",
        "subtopics": [
            ("dataframes", "DataFrame creation and operations"),
            ("transformations", "lazy evaluation and transformation types"),
            ("actions", "action types that trigger computation"),
            ("broadcast-join", "broadcast joins and shuffle optimization"),
            ("partitioning", "data partitioning strategies"),
        ]
    },
    "mlflow": {
        "name": "MLflow",
        "subtopics": [
            ("tracking", "experiment tracking and logging"),
            ("models-registry", "model registry and versioning"),
            ("autologging", "automatic logging with autolog"),
            ("deployment", "model serving and deployment"),
        ]
    },
    "databricks-cli": {
        "name": "Databricks CLI",
        "subtopics": [
            ("installation", "CLI installation and setup"),
            ("authentication", "token and OAuth authentication"),
            ("workspace-commands", "workspace file operations"),
            ("jobs-commands", "job creation and management"),
        ]
    },
    "jobs": {
        "name": "Jobs & Workflows",
        "subtopics": [
            ("job-types", "notebook, Python, JAR job types"),
            ("scheduling", "cron scheduling and triggers"),
            ("multi-task", "multi-task workflows and dependencies"),
            ("monitoring", "job monitoring and alerting"),
        ]
    },
    "clusters": {
        "name": "Clusters & Compute",
        "subtopics": [
            ("cluster-types", "all-purpose vs job clusters"),
            ("autoscaling", "autoscaling configuration and behavior"),
            ("photon-accelerator", "Photon vectorized engine"),
            ("spot-instances", "spot instance and preemptible VMs"),
        ]
    },
    "networking": {
        "name": "Networking & Security",
        "subtopics": [
            ("vpc-peering", "VPC peering configuration"),
            ("private-link", "Azure/AWS Private Link setup"),
            ("ip-access-lists", "IP allowlisting"),
        ]
    },
    "optimization": {
        "name": "Performance Optimization",
        "subtopics": [
            ("query-optimization", "query execution and optimization"),
            ("caching", "Result caching and Tungsten engine"),
            ("liquid-clustering", "liquid clustering replacement for Z-ORDER"),
        ]
    },
    "integration": {
        "name": "Integrations",
        "subtopics": [
            ("delta-sharing", "Delta Sharing for data collaboration"),
            ("airflow", "Airflow DAG integration"),
            ("terraform", "Terraform provider for Databricks"),
        ]
    },
}


async def generate_content(model: MiniMaxClient, topic_name: str, subtopic_key: str, subtopic_desc: str) -> dict:
    """Generate comprehensive content for a topic using MiniMax."""
    prompt = f"""Write a comprehensive technical guide on Databricks {subtopic_key} within the {topic_name} domain.

Cover: what it is, how to use it (with code examples), best practices, common pitfalls, configuration options.

Return ONLY valid JSON matching this schema:
{{
    "title": "Descriptive title",
    "content": "Detailed markdown content (800+ words)",
    "summary": "2-3 sentence summary",
    "tags": ["tag1", "tag2", "tag3"]
}}
JSON:"""

    response = model.complete(prompt, max_tokens=4000)
    text = response.content.strip()

    # Extract JSON
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    return json.loads(text.strip())


async def build_kb():
    kb = KnowledgeBase(storage_path="/workspace/ratchet/data/databricks_kb.json")
    model = MiniMaxClient()

    print("=" * 60)
    print("Building Databricks Knowledge Base")
    print("=" * 60)

    stats = kb.stats()
    print(f"Current KB: {stats['total_entries']} entries, {stats['topics']} topics")
    print(f"Target topics: {len(DATABRICKS_TOPICS)}")
    print()

    total_entries = 0
    for topic_key, topic_data in DATABRICKS_TOPICS.items():
        print(f"\n{'='*50}")
        print(f"Topic: {topic_data['name']}")
        print(f"{'='*50}")

        for subtopic_key, subtopic_desc in topic_data["subtopics"]:
            print(f"  Building: {subtopic_key}...", end=" ", flush=True)

            # Skip if already exists
            existing = kb.lookup_by_topic(topic_key)
            if any(e.subtopic == subtopic_key for e in existing):
                print("SKIPPED (exists)")
                continue

            try:
                data = await generate_content(model, topic_data["name"], subtopic_key, subtopic_desc)

                entry = KBEntry(
                    id=str(uuid.uuid4()),
                    topic=topic_key,
                    subtopic=subtopic_key,
                    title=data["title"],
                    content=data["content"],
                    summary=data["summary"],
                    tags=data.get("tags", []),
                    sources=[f"https://docs.databricks.com/{topic_key}/{subtopic_key}.html"],
                    created_at=datetime.utcnow().isoformat(),
                    version="1.0",
                )

                kb.add(entry)
                total_entries += 1
                print(f"✅ Added ({len(data['content'])} chars)")

                await asyncio.sleep(1)

            except Exception as e:
                print(f"❌ Error: {e}")

    print(f"\n{'='*60}")
    print("KB BUILD COMPLETE")
    print(f"{'='*60}")
    print(f"Total entries: {len(kb.entries)}")
    print(f"Topics: {kb.get_all_topics()}")
    print(f"New entries added: {total_entries}")


if __name__ == "__main__":
    asyncio.run(build_kb())
