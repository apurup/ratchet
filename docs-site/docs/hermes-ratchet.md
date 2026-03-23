# Hermes-Ratchet: Deterministic Self-Improving Agent

## Vision

Combine Hermes's rich agentic features (cross-session memory, evolving skills, multi-platform gateway, cron/scheduling, subagents) with Ratchet's deterministic execution-first philosophy (verify before trust, seeded randomness, deterministic replay).

**Core thesis:** Strong infrastructure + deterministic verification > raw model intelligence.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HERMES-RATCHET                                │
│                                                                       │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐                  │
│  │  Gateway   │───▶│   Agent    │───▶│  Verifier  │                  │
│  │(Telegram,  │    │  (Loop)    │    │ (Sandboxed)│                  │
│  │ Discord,   │    └─────┬──────┘    └─────┬──────┘                  │
│  │  etc.)     │          │                   │                         │
│  └────────────┘    ┌─────▼──────┐    ┌──────▼──────┐                │
│                    │ Reflector   │───▶│  Curator     │                │
│                    │(Analysis)   │    │  (KB+Skills) │                │
│                    └────────────┘    └──────┬───────┘                │
│                                              │                         │
│                    ┌─────────────────────────┼───────────────────┐   │
│                    │                  Memory Layer                   │   │
│                    │  ┌─────────┐  ┌─────────┐  ┌─────────────┐    │   │
│                    │  │ Session │  │  FTS5   │  │  UserModel  │    │   │
│                    │  │  Store  │  │  Index  │  │  (Honcho)   │    │   │
│                    │  └─────────┘  └─────────┘  └─────────────┘    │   │
│                    └──────────────────────────────────────────────┘   │
│                                                                       │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐            │
│  │   Scheduler  │    │  Subagents   │    │   Skills     │            │
│  │    (Cron)    │    │  (Isolated)  │    │  (Evolved)   │            │
│  └──────────────┘    └──────────────┘    └──────────────┘            │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Core Loops

### 1. Execution Loop (deterministic)

```
Task → Generator → Verifier ──pass──→ Success + Learn
                  │
                  └──fail──→ Reflector → Curator.learn() → Retry (N attempts)
```

### 2. Skill Evolution Loop

```
Skill.run() → Verifier ──fail──→ Reflector.analyze() → Skill.update()
                                              └──→ Curator.store_failure()
Skill.run() ──pass──→ Curator.record_success() → Skill.evolve()
```

### 3. Memory Loop

```
Experience → Memory.write() ──verify──▶ FTS5 Index + KB
                                    └──▶ UserModel (Honcho)
Memory.read() ──retrieve──▶ Relevant context for next task
```

---

## Components

### Gateway
- **Inherited from Hermes**: Telegram, Discord, Slack, WhatsApp, Signal, Email, CLI
- Unified session management across platforms
- Message → Task routing to agent

### Agent (main loop)
- Three modes: `BASIC`, `SKILL`, `SELF_IMPROVE` (from Ratchet)
- Maintains `ExecutionTrace` for every task
- Seeding for deterministic replay: `seed = hash(task + skill_name)`

### Generator
- Model abstraction: MiniMax, Qwen, OpenRouter (200+ models), LM Studio, OpenAI-compatible
- Prompt templating from skills
- Code extraction from markdown

### Verifier
- Sandboxed execution (temp dir, no network, timeout)
- Test harness generation (Python, JS)
- `VerificationStatus`: PASS, FAIL, ERROR, SKIP
- **NEW**: Verification of non-code outputs (memory writes, skill updates)

### Reflector
- Failure classification: syntax, logic, edge_case, timeout, verification, memory, unknown
- Root cause analysis + suggested fix
- Hypothesis generation from failure history

### Curator
- **KB**: Repair lessons from Ratchet (failure_pattern, error_signature, repair_strategy)
- **Skills**: Evolved skill versions, improvement history
- **Memory**: FTS5-indexed session store
- **UserModel**: Honcho dialectic user profiles

### Memory Layer
- **SessionStore**: Per-session message history (SQLite or JSON)
- **FTS5Index**: Full-text search across all sessions with LLM summarization
- **UserModel**: Who the user is, preferences, dialect, patterns

### Scheduler
- Natural language cron: "every day at 9am", "nightly backups"
- Delivers to any gateway platform
- Autonomous — runs without user present

### Subagents
- Spawn isolated workstreams via RPC
- Zero context cost to parent
- Parallel execution for multi-step pipelines

### Skills (deterministic + evolving)
- YAML/JSON workflow definitions (from Ratchet)
- Step types: PROMPT, READ, WRITE, EXEC, VERIFY, BRANCH
- **Evolved from Hermes**: Skills auto-create from complex tasks, evolve after successes/failures
- Verification at every step
- Version history with rollback

---

## Model Support

| Provider | Example Models | Notes |
|----------|---------------|-------|
| MiniMax | MiniMax-M2.7 | Default |
| OpenRouter | 200+ models | Any model via OpenRouter |
| Nous Portal | Nous-specific models | Built-in |
| Qwen | qwen3.5-32b | DashScope API |
| LM Studio | local models | No API cost |
| OpenAI | GPT-4o, GPT-4o-mini | OpenAI API |

Switch via: `hermes model provider:model`

---

## Deployment

| Backend | Use Case | Persistence |
|---------|----------|-------------|
| Local | Development | Local filesystem |
| Docker | Production | Volume mounts |
| SSH | Remote VPS | rsync + volume |
| Daytona | Managed dev environments | Daytona-managed |
| Singularity | GPU clusters | Shared filesystem |
| Modal | Serverless (hibernates) | S3/object store |

---

## Comparison: Hermes vs Ratchet vs Hermes-Ratchet

| Feature | Hermes | Ratchet | Hermes-Ratchet |
|---------|--------|---------|----------------|
| Execution model | Probabilistic | Deterministic | **Deterministic + Verified** |
| Skills | Evolving | Static YAML | **Evolved + Versioned + Verified** |
| Memory | FTS5 + Honcho | Curator KB | **All of Hermes + Verified Writes** |
| Verification | None | Code only | **All outputs verified** |
| Failure learning | Implicit | Curator | **Curator + Skill Evolution** |
| Platforms | Multi | CLI | **All Hermes platforms** |
| Scheduling | Cron | None | **Built-in natural language cron** |
| Subagents | Yes | No | **Yes + Verified** |
| Model-agnostic | Yes | Yes | **Yes + OpenRouter 200+** |
| Deployment | Local + cloud | Local | **All Hermes backends** |
| Deterministic replay | No | Yes | **Yes, seeded** |

---

## Implementation Phases

### Phase 1: Foundation

**Goal:** Bring Ratchet's deterministic execution core into Hermes with zero breaking changes.

#### 1.1 File Inventory

**✅ Built in Phase 1:**

| File | Status | Purpose |
|------|--------|---------|
| `hermes_determinism.py` | ✅ Done | DeterministicReplay + compute_seed + HermesDeterminismMixin |
| `deterministic/__init__.py` | ✅ Done | Package init — exports HermesGenerator, HermesVerifier, HermesReflector, HermesCurator |
| `deterministic/generator.py` | ✅ Done | Hermes-compatible Generator — wraps AIAgent model calls with Ratchet interface |
| `deterministic/verifier.py` | ✅ Done | Hermes-compatible Verifier — uses code_execution_tool sandbox |
| `deterministic/reflector.py` | ✅ Done | Hermes-compatible Reflector — rule-based + LLM failure analysis |
| `deterministic/curator.py` | ✅ Done | Hermes-compatible Curator — RepairLesson KB with Hermes KB integration |
| `tools/verify_code_tool.py` | ✅ Done | `verify_code` tool registered in tool registry |
| `hermes_state.py` | ✅ Done | Schema v6: `execution_traces` table + `save_execution_trace()` / `load_execution_trace()` methods |

**Files to modify (existing Hermes):**

| File | Status | Change |
|------|--------|--------|
| `run_agent.py` | ⬜ Pending | Import DeterministicMixin, add `seed` param to `AIAgent.__init__`, call `seeder.seed()` before model calls |
| `model_tools.py` | ⬜ Pending | Instrument `handle_function_call` to check replay cache |
| `tools/registry.py` | ⬜ Pending | `verify_code_tool.py` auto-registers via module-level `registry.register()` |

#### 1.2 Component Mapping (Ratchet → Hermes-Ratchet)

```
Ratchet Generator     →  deterministic/generator.py
                        Wraps AIAgent._make_api_call() with Ratchet GenerationResult interface
                        Adds: extract_code(), generate_with_steps()

Ratchet Verifier      →  deterministic/verifier.py
                        Delegates to code_execution_tool (UDS RPC sandbox)
                        New tool: verify_code(code, tests, language, timeout)

Ratchet Reflector     →  deterministic/reflector.py
                        FailureClassification: SYNTAX, LOGIC, EDGE_CASE,
                        TIMEOUT, VERIFICATION, MEMORY, SKILL, UNKNOWN
                        Rule-based by default; optionally uses LLM for deep analysis

Ratchet Curator       →  deterministic/curator.py
                        RepairLesson KB at ~/.hermes/data/curator.json
                        Integrates with Hermes KnowledgeBase when available
```

#### 1.3 Seeded Randomness

**Seed derivation (hermes_determinism.py):**
```python
def compute_seed(task: str, skill_name: Optional[str] = None) -> int:
    raw = f"{task}:{skill_name or ''}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:16], 16) % (2**63)
```

**DeterministicReplay** captures step outputs during forward pass, replays them on replay pass:
```python
dr = DeterministicReplay(seed=compute_seed(task, skill_name))
dr.capture(f"terminal:{args_hash}", result_json)
cached = dr.replay(f"terminal:{args_hash}")  # None if not cached
```

**HermesDeterminismMixin** adds to AIAgent:
- `init_determinism(seed=..., replay_data=bytes)` — init from seed or replay
- `compute_deterministic_seed(task, skill_name)` — derive + store seed
- `is_replay()` → bool
- `capture_step(key, output, ...)` / `replay_step(key)` → Optional[str]
- `serialize_deterministic_state()` → bytes (for SessionDB)

#### 1.4 Backward Compatibility Strategy

**Hermes users notice zero change** — Phase 1 is entirely additive:

1. **Existing tool calls work unchanged** — `verify_code` is a new tool, never called unless explicitly requested
2. **Skills remain compatible** — Skill schema unchanged; `verification` field is optional
3. **SessionDB schema migration** — v6 adds tables/indexes with `CREATE TABLE IF NOT EXISTS`
4. **Model providers unchanged** — Generator wraps existing model clients
5. **Gateway unchanged** — Telegram/Discord/CLI all work without modification
6. **Subagents unchanged** — `IterationBudget` and spawning logic untouched

**Opt-in determinism:**
```python
# Programmatically:
agent = AIAgent(deterministic_seed=compute_seed(task))
# Or enable replay from prior run:
agent.init_determinism(replay_data=session_db.load_execution_trace(trace_id)['serialized_replay'])
```

#### 1.5 Implementation Order

```
Step 1 ✅: Create deterministic/ package
         generator.py, verifier.py, reflector.py, curator.py + __init__.py

Step 2 ✅: Add verify_code tool
         tools/verify_code_tool.py (auto-registers via registry.register())

Step 3 ⬜: Integrate seeded randomness into AIAgent
         - Add DeterministicMixin to run_agent.py
         - Call seeder before model.generate() in BASIC/SKILL modes
         - Store seed in ExecutionTrace

Step 4 ✅: Connect ExecutionTrace to SessionDB
         - hermes_state.py v6 migration: execution_traces table
         - save_execution_trace() / load_execution_trace() methods

Step 5 ⬜: Merge Curator with Hermes knowledge base
         - Adapt RepairLesson to Hermes storage path (~/.hermes/data/curator.json)
         - Add find_similar() lookup to skills_tool.py

Step 6 ⬜: Integration test
         - Run determinism_test.py against Hermes agent
         - Verify same task + same seed → same output
         - Verify Hermes tools still work end-to-end
```

#### 1.6 Verification Checklist

- [x] `python -c "from deterministic import HermesGenerator, HermesVerifier, HermesReflector, HermesCurator"` — imports clean
- [x] `verify_code_tool.py` auto-registers via `registry.register()` at module load
- [x] `execution_traces` table schema added via v6 migration in `hermes_state.py`
- [x] `save_execution_trace()` / `load_execution_trace()` / `get_execution_traces()` methods added to `SessionDB`
- [x] `DeterministicReplay` + `compute_seed()` + `HermesDeterminismMixin` in `hermes_determinism.py`
- [ ] Instrument `handle_function_call` in `model_tools.py` to check replay cache
- [ ] AIAgent uses DeterministicMixin and seeds before model calls
- [ ] Same task + same seed produces bit-identical output across 3 runs
- [ ] Existing Hermes CLI session starts without errors
- [ ] SessionDB schema migration runs without errors on fresh DB

### Phase 2: Memory
- [ ] Integrate FTS5 session store with Curator KB
- [ ] Add Honcho user modeling
- [ ] Verified memory writes (write → verify → commit)

### Phase 3: Skills
- [ ] Migrate Hermes skill creation to Ratchet skill schema
- [ ] Skill version history with rollback
- [ ] Auto-evolve skills from success/failure feedback

### Phase 4: Gateway
- [ ] Integrate Hermes gateway (Telegram, Discord, etc.)
- [ ] Unified session across platforms
- [ ] Scheduled automations

### Phase 5: Subagents + Research
- [ ] Isolated subagent spawning with RPC
- [ ] Batch trajectory generation
- [ ] Atropos RL environment integration
