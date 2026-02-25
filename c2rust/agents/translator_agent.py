"""Translator agent: converts C files to rough Rust code."""

from typing import Any

from agno.agent import Agent

from c2rust.utils.code_cleaning import clean_llm_output


TRANSLATOR_INSTRUCTIONS = """You are an expert C to Rust translator.

Goal:
- Produce a faithful file-level translation from C to Rust.
- Preserve full function-level coverage and API intent first, even if output has compiler errors.

Requirements:
1. Output Rust source code only.
2. Do not output markdown fences or explanations.
3. Preserve function names from the C source whenever possible.
4. Do not omit C functions just to make the output compile.
5. Do not use placeholders or stubs: no TODO, no unimplemented!, no empty/dummy bodies.
6. If uncertain, still provide best-effort concrete logic instead of a placeholder.
7. Prefer explicit types and small helper structs over macro-heavy translations.
8. Keep external dependencies minimal (std only).

Important:
- This is file-level translation, not full-project redesign.
- Use the provided header context to infer function signatures and shared types.
- Output one complete Rust file that contains all required functions.
"""


def create_translator_agent(model) -> Agent:
    """Create C->Rust translator agent."""
    return Agent(model=model, instructions=TRANSLATOR_INSTRUCTIONS, markdown=False)


def translate_c_to_rust(
    agent: Agent,
    c_code: str,
    file_path: str,
    header_context: str,
    required_functions: list[str] | None = None,
) -> tuple[str, Any]:
    """Translate one C file into Rust and return code plus raw response."""
    required_list = ", ".join(required_functions or [])
    prompt = f"""Translate this C source file to Rust in one shot.

Source file: {file_path}

Header context (reference only):
```c
{header_context}
```

C source code:
```c
{c_code}
```

Functions that should appear in this translation (do not omit):
{required_list if required_list else "(not provided)"}

Rules:
- Keep C function names when possible.
- Do not omit required functions.
- Do not use TODO, unimplemented!, panic!("TODO"), or placeholder bodies.
- Forbidden tokens: unimplemented!(, todo!(, TODO, panic!("TODO").
- If behavior is unclear, implement best-effort concrete logic anyway.
- Do not output explanations or markdown.

Output only Rust code for this file.
"""

    response = agent.run(prompt)
    if hasattr(response, "content"):
        rust_code = response.content
    elif isinstance(response, str):
        rust_code = response
    else:
        rust_code = str(response)

    return clean_llm_output(rust_code), response


def get_token_usage(response) -> tuple[int, int]:
    """Extract prompt/completion token counts from response when present."""
    prompt_tokens = 0
    completion_tokens = 0

    if hasattr(response, "usage"):
        usage = response.usage
        if hasattr(usage, "prompt_tokens"):
            prompt_tokens = usage.prompt_tokens
        if hasattr(usage, "completion_tokens"):
            completion_tokens = usage.completion_tokens
    elif hasattr(response, "model_dump"):
        try:
            data = response.model_dump()
            usage = data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)

            if prompt_tokens == 0 and completion_tokens == 0:
                metrics = data.get("metrics", {})
                prompt_tokens = metrics.get("input_tokens", 0)
                completion_tokens = metrics.get("output_tokens", 0)
        except Exception:
            pass

    elif hasattr(response, "metrics"):
        metrics = response.metrics
        prompt_tokens = getattr(metrics, "input_tokens", 0) or 0
        completion_tokens = getattr(metrics, "output_tokens", 0) or 0

    return prompt_tokens, completion_tokens


def get_response_diagnostics(response) -> dict[str, object]:
    """Extract generic response diagnostics for research logging."""
    diagnostics: dict[str, object] = {
        "finish_reason": "unknown",
        "model": "unknown",
        "response_id": "",
    }

    if hasattr(response, "model"):
        diagnostics["model"] = getattr(response, "model", "unknown")
    if hasattr(response, "id"):
        diagnostics["response_id"] = getattr(response, "id", "")

    if hasattr(response, "stop_reason"):
        diagnostics["finish_reason"] = getattr(response, "stop_reason") or "unknown"

    if hasattr(response, "model_dump"):
        try:
            data = response.model_dump()
            diagnostics["model"] = data.get("model", diagnostics["model"])
            diagnostics["response_id"] = data.get("id", diagnostics["response_id"])
            diagnostics["finish_reason"] = (
                data.get("finish_reason")
                or data.get("stop_reason")
                or diagnostics["finish_reason"]
            )
            if "usage" in data:
                diagnostics["usage"] = data["usage"]
        except Exception:
            pass

    return diagnostics
