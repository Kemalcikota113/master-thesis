"""Configuration for c2rust translation pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv
from agno.models.google import Gemini
from agno.models.openai import OpenAIChat


project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")


MODEL_PROVIDER = "openai"
MODEL_ID = "gpt-4o"

# Minimum strict symbol coverage required to consider translation faithful.
FIDELITY_MIN_STRICT_COVERAGE = 0.95
# Minimum relaxed symbol coverage (underscore/case-insensitive) for baseline gate.
FIDELITY_MIN_RELAXED_COVERAGE = 0.95
# Gate mode: "strict" or "relaxed".
FIDELITY_GATE_MODE = "relaxed"


def get_model():
    """Return the configured LLM model instance."""
    if MODEL_PROVIDER == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("OPENAI_API_KEY not found in environment")
        return OpenAIChat(id=MODEL_ID, api_key=api_key)

    if MODEL_PROVIDER == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError("GOOGLE_API_KEY not found in environment")
        return Gemini(id=MODEL_ID, api_key=api_key)

    raise ValueError("MODEL_PROVIDER must be 'openai' or 'gemini'")


def get_provider_name() -> str:
    return MODEL_PROVIDER


def get_model_id() -> str:
    return MODEL_ID


def get_fidelity_min_strict_coverage() -> float:
    return FIDELITY_MIN_STRICT_COVERAGE


def get_fidelity_min_relaxed_coverage() -> float:
    return FIDELITY_MIN_RELAXED_COVERAGE


def get_fidelity_gate_mode() -> str:
    if FIDELITY_GATE_MODE not in {"strict", "relaxed"}:
        raise ValueError("FIDELITY_GATE_MODE must be 'strict' or 'relaxed'")
    return FIDELITY_GATE_MODE
