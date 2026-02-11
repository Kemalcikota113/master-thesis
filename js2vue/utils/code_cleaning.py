"""
Utility functions for cleaning LLM-generated code output.
"""

import re


def strip_markdown_fences(text: str) -> str:
    """
    Removes markdown code fence markers from LLM output.

    LLMs often wrap code in ```vue or ```typescript blocks.
    This function extracts just the code content.

    Args:
        text: Raw LLM output that may contain markdown fences

    Returns:
        Clean code without markdown fences

    Examples:
        >>> strip_markdown_fences("```vue\\n<template>...</template>\\n```")
        "<template>...</template>"
    """
    # Remove opening fence (```vue, ```typescript, ```javascript, or just ```)
    text = re.sub(r'^```(?:vue|typescript|javascript|ts|js)?\s*\n', '', text, flags=re.MULTILINE)

    # Remove closing fence
    text = re.sub(r'\n```\s*$', '', text, flags=re.MULTILINE)

    return text.strip()


def clean_llm_output(text: str) -> str:
    """
    Comprehensive cleaning of LLM output for code generation.

    Applies multiple cleaning strategies:
    - Strips markdown fences
    - Removes common LLM preamble text
    - Normalizes whitespace

    Args:
        text: Raw LLM output

    Returns:
        Cleaned code ready to write to file
    """
    # Strip markdown fences
    text = strip_markdown_fences(text)

    # Remove common LLM preamble patterns
    preamble_patterns = [
        r'^Here\'s the .*?:\s*\n',
        r'^Here is the .*?:\s*\n',
        r'^I\'ve .*?:\s*\n',
        r'^The .*? is:\s*\n',
    ]

    for pattern in preamble_patterns:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)

    # Normalize line endings
    text = text.replace('\r\n', '\n')

    # Remove trailing whitespace from each line
    lines = [line.rstrip() for line in text.split('\n')]
    text = '\n'.join(lines)

    return text.strip()
