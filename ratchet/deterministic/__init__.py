"""
Deterministic execution package for Hermes-Ratchet.

Adapts Ratchet's Generator → Verifier → Reflector → Curator loop
for use within the Hermes AIAgent framework.

Modules:
- generator: Hermes-compatible Generator wrapping model calls
- verifier: Sandboxed code execution using Hermes's code_execution_tool
- reflector: Rule-based failure classification + LLM-powered deep analysis
- curator: RepairLesson KB with Hermes knowledge_base integration
- subagent_manager: Verified subagent spawning with deterministic seeds
- rpc_protocol: RPC message types for parent↔subagent communication
- trajectory_pipeline: Batch trajectory generation for RL training
- scheduler: Natural language cron scheduler for periodic task execution
"""

from ratchet.deterministic.generator import HermesGenerator
from ratchet.deterministic.verifier import HermesVerifier
from ratchet.deterministic.reflector import HermesReflector
from ratchet.deterministic.curator import HermesCurator
from ratchet.deterministic.subagent_manager import SubagentManager, SubagentResult, compute_subagent_seed
from ratchet.deterministic.rpc_protocol import (
    RPCMessage,
    RPCResult,
    RPCProgress,
    RPCLesson,
    RPCInterrupt,
    RPCChannel,
    InMemoryChannel,
    RPCAggregator,
)
from ratchet.deterministic.trajectory_pipeline import (
    TrajectoryPipeline,
    TrajectoryStep,
    Trajectory,
)
from ratchet.deterministic.scheduler import (
    NaturalLanguageScheduler,
    ScheduledTask,
)

__all__ = [
    # Core components
    "HermesGenerator",
    "HermesVerifier",
    "HermesReflector",
    "HermesCurator",
    # Subagent management
    "SubagentManager",
    "SubagentResult",
    "compute_subagent_seed",
    # RPC protocol
    "RPCMessage",
    "RPCResult",
    "RPCProgress",
    "RPCLesson",
    "RPCInterrupt",
    "RPCChannel",
    "InMemoryChannel",
    "RPCAggregator",
    # Trajectory pipeline
    "TrajectoryPipeline",
    "TrajectoryStep",
    "Trajectory",
    # Natural language scheduler
    "NaturalLanguageScheduler",
    "ScheduledTask",
]
