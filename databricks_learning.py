#!/usr/bin/env python3
import sys
import json
sys.path.insert(0, '/workspace/ratchet')

from ratchet.curator import Curator, RepairLesson
from ratchet.models import MiniMaxClient
import uuid

# Step 1: Fresh curator
curator = Curator(storage_path="/workspace/ratchet/data/databricks_curator.json")
curator.lessons = []
curator._save()
print(f"Curator initialized with {len(curator.lessons)} lessons (should be 0)")

# Step 2: Ask WITHOUT learning
print("="*60)
print("BEFORE LEARNING - Asking Databricks question")
print("="*60)

client = MiniMaxClient()
prompt = "Explain how to set up Unity Catalog for a new Databricks workspace. Include steps for metastore creation and entitlement."
response = client.complete(prompt, max_tokens=2000)
before_answer = response.content
print(f"Answer:\n{before_answer[:800]}")

# Step 3: Learn from docs (manually create lessons based on fetched doc content)
print("\n" + "="*60)
print("LEARNING - Storing Databricks lessons")
print("="*60)

lessons_data = [
    {
        "topic": "unity_catalog_setup",
        "pattern": "unity catalog metastore creation workspace setup",
        "strategy": "1. Create metastore in account console (Account Admin) 2. Link metastore to workspace 3. Create storage credential (cloud IAM role) 4. Create external location referencing the storage credential 5. Grant ENTITLEMENT 'workspace_access' to users and 'USE_CATALOG' on metastore. Use Catalog Explorer or SQL: CREATE METASTORE, CREATE CATALOG, GRANT.",
        "context": "Unity Catalog setup for new Databricks workspace — metastore creation and entitlements",
    },
    {
        "topic": "delta_lake",
        "pattern": "delta lake acid transactions time travel optimization",
        "strategy": "Delta Lake provides ACID transactions via transaction log. Use DESCRIBE HISTORY for time travel queries. OPTIMIZE command for file compaction. Z-ORDER BY for multi-dimensional data skipping. VACUUM to remove unused files. Liquid clustering replaces Z-ORDER in newer versions. Default format for all Databricks tables.",
        "context": "Delta Lake transactions, time travel, and query optimization",
    },
    {
        "topic": "dbx_cli",
        "pattern": "databricks cli deployment workflow",
        "strategy": "Use 'databricks workspace import' to deploy notebooks. 'databricks jobs create --json' for job creation with JSON payload. 'databricks clusters get <id>' to inspect clusters. 'databricks bundles' for project-level deployments. CLI wraps REST API 2.0 endpoints. Install via: pip install databricks-cli",
        "context": "Databricks CLI deployment workflows and common commands",
    },
    {
        "topic": "unity_catalog_object_model",
        "pattern": "unity catalog securable objects metastore catalog schema",
        "strategy": "Unity Catalog hierarchy: Metastore → Catalog → Schema → Table/View/Volume/Function/Model. Admin roles: Account Admin (create metastores), Workspace Admin (workspace mgmt), Metastore Admin (data governance per region). Use ANSI SQL GRANT/REVOKE. Default: least privilege, Workspace catalog for new users.",
        "context": "Unity Catalog object model, securable objects, and admin roles",
    },
]

for ld in lessons_data:
    lesson = RepairLesson(
        id=str(uuid.uuid4()),
        failure_pattern=ld["pattern"],
        error_signature=ld["topic"],
        context=ld["context"],
        repair_strategy=ld["strategy"],
        model_used="databricks-docs-v2",
    )
    curator.add_lesson(lesson)
    print(f"  Stored: {ld['topic']}")

print(f"\nCurator now has {len(curator.lessons)} lessons")

# Step 4: Ask AFTER learning
print("\n" + "="*60)
print("AFTER LEARNING - Asking same question")
print("="*60)

learned_context = "\n".join([
    f"- {l.repair_strategy}" 
    for l in curator.lessons
])
enhanced_prompt = f"""Based on Databricks best practices:

{learned_context}

Now explain how to set up Unity Catalog for a new Databricks workspace. Include steps for metastore creation and entitlement."""

response = client.complete(enhanced_prompt, max_tokens=2000)
after_answer = response.content
print(f"Answer:\n{after_answer[:800]}")

# Step 5: Compare
print("\n" + "="*60)
print("COMPARISON")
print("="*60)
print(f"BEFORE (first 300 chars): {before_answer[:300]}")
print(f"\nAFTER (first 300 chars): {after_answer[:300]}")

# Save results
results = {
    "lessons_learned": len(lessons_data),
    "lesson_topics": [l["topic"] for l in lessons_data],
    "before_answer": before_answer,
    "after_answer": after_answer,
    "before_length": len(before_answer),
    "after_length": len(after_answer),
    "doc_sources": [
        "https://docs.databricks.com/en/index.html",
        "https://docs.databricks.com/en/unity-catalog/index.html (redirected to data-governance/unity-catalog)",
        "https://docs.databricks.com/en/delta/index.html",
        "https://docs.databricks.com/en/dev-tools/cli/index.html"
    ]
}

with open("/workspace/ratchet/databricks_learning_results.json", "w") as f:
    json.dump(results, f, indent=2)

print(f"\nResults saved to databricks_learning_results.json")
print(f"Total lessons stored: {len(lessons_data)}")
