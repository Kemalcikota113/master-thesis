"""
Configuration for LLM provider, models, and global parameters.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Import from the installed agno library (not our local package)
from agno.agent import Agent
from agno.models.openai import OpenAIChat

# Import Gemini from Agno
from agno.models.google import Gemini

# Load environment variables from .env file in project root
project_root = Path(__file__).parent.parent
load_dotenv(project_root / ".env")

# ============================================================
# SWITCHABLE CONFIGURATION VARIABLES
# ============================================================

# Model provider: "openai" or "gemini"
MODEL_PROVIDER = "openai"

# Model ID for the selected provider
MODEL_ID = "gpt-4o"  # For OpenAI: gpt-4o, gpt-4-turbo, etc.
                      # For Gemini: gemini-2.0-flash-exp, gemini-1.5-pro, etc.

# Maximum repair iterations (internal validity constraint)
# Ensures performance gains come from agent reasoning, not brute-force repetition
MAX_REPAIR_ITERATIONS = 3

# Runtime capture configuration (NEW)
RUNTIME_CAPTURE_ENABLED = True       # Enable/disable runtime error capture
RUNTIME_CAPTURE_DURATION = 30        # How long to capture errors (seconds)
VITE_PORT = 5173                     # Port for Vite dev server


# ============================================================
# MODEL FACTORY
# ============================================================

def get_model():
    """
    Factory function that returns the configured LLM model instance.

    Returns:
        OpenAIChat or Gemini model instance based on MODEL_PROVIDER

    Raises:
        ValueError: If MODEL_PROVIDER is not recognized
        EnvironmentError: If required API keys are missing
    """
    if MODEL_PROVIDER == "openai":
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not found in environment variables. "
                "Please add it to your .env file."
            )

        return OpenAIChat(
            id=MODEL_ID,
            api_key=api_key
        )

    elif MODEL_PROVIDER == "gemini":
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GOOGLE_API_KEY not found in environment variables. "
                "Please add it to your .env file."
            )

        return Gemini(
            id=MODEL_ID,
            api_key=api_key
        )

    else:
        raise ValueError(
            f"Unknown MODEL_PROVIDER: {MODEL_PROVIDER}. "
            "Supported values: 'openai', 'gemini'"
        )


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def get_provider_name() -> str:
    """Returns the current provider name for display."""
    return MODEL_PROVIDER


def get_model_id() -> str:
    """Returns the current model ID for display."""
    return MODEL_ID


def get_max_iterations() -> int:
    """Returns the maximum repair iterations allowed."""
    return MAX_REPAIR_ITERATIONS


def get_runtime_capture_enabled() -> bool:
    """Returns whether runtime error capture is enabled."""
    return RUNTIME_CAPTURE_ENABLED


def get_runtime_capture_duration() -> int:
    """Returns the runtime error capture duration in seconds."""
    return RUNTIME_CAPTURE_DURATION


def get_vite_port() -> int:
    """Returns the Vite dev server port."""
    return VITE_PORT
