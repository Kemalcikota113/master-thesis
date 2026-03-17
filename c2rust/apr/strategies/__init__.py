"""APR v2 strategy implementations.

Four strategies that differ in *how* the LLM interaction is structured
(not just how much context is provided):

    BASELINE          — raw terminal compiler dump → single LLM call
    STRUCTURED        — cargo JSON errors → structured numbered list → single LLM call
    DIAGNOSE_THEN_PATCH — 2-call CoT: (1) diagnose, (2) patch
    MEMORY_REFLEXION  — 2-call CoT + structured attempt-memory block
"""

from c2rust.apr.strategies.base import (
    AprStrategyV2,
    CargoJsonError,
    MemoryEntry,
    StrategyRunResult,
    run_cargo_check_json,
)
from c2rust.apr.strategies import baseline, structured, diagnose_patch, memory_reflexion

# Dispatch map: strategy enum → strategy module
STRATEGY_MODULES = {
    AprStrategyV2.BASELINE: baseline,
    AprStrategyV2.STRUCTURED: structured,
    AprStrategyV2.DIAGNOSE_THEN_PATCH: diagnose_patch,
    AprStrategyV2.MEMORY_REFLEXION: memory_reflexion,
}

__all__ = [
    "AprStrategyV2",
    "CargoJsonError",
    "MemoryEntry",
    "StrategyRunResult",
    "run_cargo_check_json",
    "STRATEGY_MODULES",
    "baseline",
    "structured",
    "diagnose_patch",
    "memory_reflexion",
]
