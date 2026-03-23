# Hermes-Ratchet Implementation Summary

Hermes-Ratchet adds deterministic replay, verified execution, and self-improvement to the Hermes AIAgent framework using the Ratchet methodology: **Generator → Verifier → Reflector → Curator** loop.

## Files Created/Modified

### Core Determinism (`hermes_determinism.py`)

| Symbol | Description |
|--------|-------------|
| `compute_seed(task, skill_name)` | Deterministic seed from task + skill hash |
| `DeterministicState` | Serializable state (seed, step_traces, random_state) |
| `DeterministicReplay` | Captures step outputs forward; replays in deterministic mode |
| `HermesDeterminismMixin` | Mixin for AIAgent with determinism methods |

### Deterministic Package (`deterministic/`)

| File | Class(es) | Role |
|------|-----------|------|
| `generator.py` | `HermesGenerator`, `GenerationResult` | Wraps model calls with deterministic seeding |
| `verifier.py` | `HermesVerifier`, `TestCase`, `ExecutionResult` | Sandboxed code execution + test harness |
| `reflector.py` | `HermesReflector`, `FailureCategory`, `FailureAnalysis` | Rule-based failure classification + LLM deep analysis |
| `curator.py` | `HermesCurator`, `RepairLesson` | RepairLesson KB with SQLite FTS5 (Phase 2b) |
| `skill_schema.py` | `SkillStep`, `Skill`, `VerificationRule` | Structured skill definition schema |
| `skill_runner.py` | `SkillRunner`, `SkillStepResult` | Runs skill steps with deterministic replay |
| `memory_verifier.py` | `MemoryVerifier`, `VerificationResult` | Long-term memory consistency verification |
| `scheduler.py` | `NaturalLanguageScheduler`, `ScheduledTask` | Natural language → cron schedule parser |
| `subagent_manager.py` | `SubagentManager`, `SubagentResult`, `compute_subagent_seed` | Deterministic verified subagent spawning |
| `rpc_protocol.py` | `RPC*` message classes, `InMemoryChannel`, `RPCAggregator` | RPC message types for parent↔subagent communication |
| `trajectory_pipeline.py` | `TrajectoryPipeline`, `Trajectory`, `TrajectoryStep` | Batch trajectory generation for RL training |

### Tool Integration

| File | Role |
|------|------|
| `tools/verify_code_tool.py` | `verify_code` tool registered in `tools.registry` — delegates to `HermesVerifier` |
| `model_tools.py` | `_discover_tools()` includes `verify_code_tool`; `handle_function_call()` checks `_determinism_state` for replay |
| `run_agent.py` | `deterministic_seed` parameter; `replay_from_trace()`; natural language scheduling; trajectory pipeline |
| `hermes_state.py` | `execution_traces` table (v6) and `repair_lessons` table (v7) with FTS5 in `SessionDB` |

### Database Schema Additions (v6, v7)

- **`execution_traces`** — stores serialized `DeterministicReplay`, seed, task, traces JSON, duration, success flag
- **`repair_lessons`** — stores failure patterns, error signatures, repair strategies, fix code, with FTS5 index across all text fields
- FTS5 triggers for automatic index maintenance on insert/update/delete

## Architecture

```
User Task
    │
    ▼
HermesGenerator ──► HermesVerifier (sandboxed execution)
    │                    │
    │              ┌──────┴──────┐
    │              ▼              ▼
    │         PASS             FAIL
    │              │              │
    │              ▼              ▼
    │        (record step)   HermesReflector
    │                              │
    │                              ▼
    │                        HermesCurator
    │                        (RepairLesson KB)
    │                              │
    └──────────────────────────────┘
                    │
                    ▼
              Tool Output → capture()
```

**Deterministic Replay Flow:**
1. `run_agent.py` takes `deterministic_seed` or `replay_data` (serialized `DeterministicReplay`)
2. `model_tools.py`'s `handle_function_call()` checks `_determinism_state` before dispatch
3. In replay mode: returns cached result; in forward mode: captures result after dispatch
4. Traces stored in `SessionDB.execution_traces` for later replay via `find_matching_trace()`

## How to Run a Simple Test

```python
import sys
sys.path.insert(0, '/workspace/hermes_code')

from hermes_determinism import compute_seed, DeterministicReplay, DeterministicState

# 1. Generate a deterministic seed
seed = compute_seed("Write a hello world function", skill_name="python")
print(f"Seed: {seed}")

# 2. Create a replay object (forward pass)
replay = DeterministicReplay(seed=seed)

# 3. Simulate capturing a tool call
step_key = "execute_code:abc123"
replay.capture(step_key, '{"status": "pass", "output": "hello world\\n"}', success=True)
print(f"Captured steps: {list(replay._traces.keys())}")

# 4. Serialize and restore for replay
data = replay.serialize()
restored = DeterministicReplay.deserialize(data)
print(f"Replayed result: {restored.replay(step_key)}")
print(f"Is replay mode: {restored.is_replay}")

# 5. Full AIAgent with deterministic seed
# In run_agent.py:
# agent = AIAgent(deterministic_seed=seed)  # or
# agent = AIAgent(replay_data=serialized_bytes)
```

## Gateway Integration

The gateway passes `deterministic_seed` to `AIAgent.__init__()`, enabling:
- Verified subagents with deterministic seeds (`SubagentManager`)
- RPC message types for parent↔subagent communication (`RPCProtocol`)
- Trajectory saving for RL training (`TrajectoryPipeline`)
- Persistent repair lessons across sessions (`HermesCurator` → `SessionDB`)

## Requirements

- Python 3.10+
- `hermes_code` package (already present in workspace)
- `hermes_cli` (for gateway integration)
- Standard library: `sqlite3`, `hashlib`, `threading`, `json`
