"""Helpers for cleaning LLM-generated Rust output."""

import re


def strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences from model output."""
    text = re.sub(r"^```(?:rust|rs|c)?\s*\n", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def clean_llm_output(text: str) -> str:
    """Normalize line endings and remove common preambles/fences."""
    text = strip_markdown_fences(text)

    preamble_patterns = [
        r"^Here is the .*?:\s*\n",
        r"^Here's the .*?:\s*\n",
        r"^Rust translation:\s*\n",
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    text = text.replace("\r\n", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()
