"""
Ratchet - Deterministic self-improving AI agent framework
"""

from ratchet.models import ModelClient, ModelResponse, get_client
from ratchet.skill import Skill, Step, VerificationRule, StepType, VerificationType
from ratchet.generator import Generator, GenerationResult
from ratchet.verifier import Verifier, ExecutionResult, TestCase, VerificationStatus
from ratchet.reflector import Reflector, FailureAnalysis
from ratchet.curator import Curator, RepairLesson
from ratchet.agent import RatchetAgent, AgentConfig, AgentMode, ExecutionTrace
from ratchet.mcp_client import MCPClient, get_mcp_client

# Hermes deterministic exports
from ratchet.hermes_determinism import (
    compute_seed,
    DeterministicReplay,
    DeterministicState,
    StepTrace,
    HermesDeterminismMixin,
)
from ratchet.deterministic import (
    HermesGenerator,
    HermesVerifier,
    HermesReflector,
    HermesCurator,
    SubagentManager,
    SubagentResult,
    compute_subagent_seed,
    RPCMessage,
    RPCResult,
    RPCProgress,
    RPCLesson,
    RPCInterrupt,
    RPCChannel,
    InMemoryChannel,
    RPCAggregator,
    TrajectoryPipeline,
    TrajectoryStep,
    Trajectory,
    NaturalLanguageScheduler,
    ScheduledTask,
)

__version__ = "0.2.0"
__all__ = [
    # Version
    "__version__",
    # Models
    "ModelResponse",
    "ModelClient",
    "get_client",
    # Skill schema
    "Skill",
    "Step",
    "StepType",
    "VerificationRule",
    "VerificationType",
    # Generator
    "Generator",
    "GenerationResult",
    # Verifier
    "Verifier",
    "ExecutionResult",
    "TestCase",
    "VerificationStatus",
    # Reflector
    "Reflector",
    "FailureAnalysis",
    # Curator
    "Curator",
    "RepairLesson",
    # Agent
    "RatchetAgent",
    "AgentConfig",
    "AgentMode",
    "ExecutionTrace",
    # MCP
    "MCPClient",
    "get_mcp_client",
    # Deterministic / Hermes
    "compute_seed",
    "DeterministicReplay",
    "DeterministicState",
    "StepTrace",
    "HermesDeterminismMixin",
    "HermesGenerator",
    "HermesVerifier",
    "HermesReflector",
    "HermesCurator",
    "SubagentManager",
    "SubagentResult",
    "compute_subagent_seed",
    "RPCMessage",
    "RPCResult",
    "RPCProgress",
    "RPCLesson",
    "RPCInterrupt",
    "RPCChannel",
    "InMemoryChannel",
    "RPCAggregator",
    "TrajectoryPipeline",
    "TrajectoryStep",
    "Trajectory",
    "NaturalLanguageScheduler",
    "ScheduledTask",
]
