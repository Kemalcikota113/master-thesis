"""APR agent for compile-error repair and diagnosis of translated Rust files."""

from typing import Any

from agno.agent import Agent

from c2rust.utils.code_cleaning import clean_llm_output


APR_INSTRUCTIONS = """You are an expert Rust compiler-error repair assistant.

Goal:
- Fix Rust compile errors in the provided target file.
- Apply minimal edits that address the current compiler error.

Rules:
1. Output only the complete updated target Rust file content.
2. Do not output markdown fences or explanations.
3. Preserve existing function names and structure unless required by the fix.
4. Do not insert placeholders (TODO, unimplemented!, panic!(\"TODO\")).
5. Use stable Rust only.
6. Keep edits focused on the target file.
"""


DIAGNOSE_INSTRUCTIONS = """You are an expert Rust compiler-error analyst.
Your role is to reason about *why* code fails to compile and propose a concrete fix plan.

Rules:
1. Output structured analysis text only — three sections: ROOT CAUSE, TARGET SYMBOLS, FIX PLAN.
2. Do NOT output any Rust code.
3. Be specific: name the exact functions, types, macros, or variables that must change.
4. Keep the fix plan ordered and actionable.
"""


def create_apr_agent(model) -> Agent:
    """Create APR agent for target-file repair (code output)."""
    return Agent(model=model, instructions=APR_INSTRUCTIONS, markdown=False)


def create_diagnose_agent(model) -> Agent:
    """Create diagnosis agent for root-cause analysis (text output, no code)."""
    return Agent(model=model, instructions=DIAGNOSE_INSTRUCTIONS, markdown=False)


def repair_target_file(agent: Agent, prompt: str) -> tuple[str, Any]:
    """Run APR model and return cleaned file content + raw response."""
    response = agent.run(prompt)
    if hasattr(response, "content"):
        text = response.content
    else:
        text = str(response)
    return clean_llm_output(text), response


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
