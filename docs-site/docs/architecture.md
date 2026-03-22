---
sidebar_position: 3
---

# Architecture

## Overview

Ratchet uses a multi-component architecture for self-improving AI agents:

```
┌─────────────────────────────────────────────────────────────┐
│                        RATCHET                               │
│                                                             │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐               │
│  │ Generator│──▶│ Verifier │──▶│ Reflector │               │
│  │ (Model)  │   │  (Test)  │   │(Analysis)│               │
│  └──────────┘   └──────────┘   └────┬─────┘               │
│        ▲                           │                       │
│        │                    ┌──────▼──────┐               │
│        │                    │  Curator    │               │
│        │                    │  (KB/Playbook)│              │
│        └────────────────────┴─────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

## Components

### Generator
Model interaction layer - handles prompts, structured outputs, code generation.

### Verifier
Sandboxed code execution and test runner - runs code safely and verifies outputs.

### Reflector
Failure analysis - extracts hypotheses from execution failures.

### Curator
Knowledge base - stores repair lessons and suggests fixes for similar failures.
