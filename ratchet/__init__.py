"""
Ratchet - Deterministic self-improving AI agent framework
"""

from ratchet.models import ModelClient, ModelResponse, get_client
from ratchet.skill import Skill, Step, VerificationRule, StepType, VerificationType
from ratchet.generator import Generator
from ratchet.verifier import Verifier, ExecutionResult, TestCase, VerificationStatus
from ratchet.reflector import Reflector, FailureAnalysis
from ratchet.curator import Curator, RepairLesson
from ratchet.agent import RatchetAgent, AgentConfig, AgentMode, ExecutionTrace

__version__ = "0.1.0"
__all__ = [
    "ModelClient",
    "ModelResponse",
    "get_client",
    "Skill",
    "Step",
    "VerificationRule",
    "StepType",
    "VerificationType",
    "Generator",
    "Verifier",
    "ExecutionResult",
    "TestCase",
    "VerificationStatus",
    "Reflector",
    "FailureAnalysis",
    "Curator",
    "RepairLesson",
    "RatchetAgent",
    "AgentConfig",
    "AgentMode",
    "ExecutionTrace",
]

# Core exports
from ratchet.models import ModelResponse, ModelClient, get_client
from ratchet.skill import Skill, Step, StepType, VerificationRule, VerificationType
from ratchet.generator import Generator, GenerationResult
from ratchet.verifier import Verifier, ExecutionResult
from ratchet.reflector import Reflector, FailureAnalysis
from ratchet.curator import Curator, KnowledgeEntry
from ratchet.agent import Agent, AgentConfig, StepResult, ExecutionResult

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
    # Reflector
    "Reflector",
    "FailureAnalysis",
    # Curator
    "Curator",
    "KnowledgeEntry",
    # Agent
    "Agent",
    "AgentConfig",
    "StepResult",
    "ExecutionResult",
]
