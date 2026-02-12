"""
APRA (Automatic Program Repair Agent): Fixes broken Vue SFCs based on error analysis.

This agent receives structured error information from the Runner Agent and applies
targeted fixes to Vue Single-File Components. It has access to:
- Current broken code
- Error details and repair strategies
- Original JavaScript code (for context)
- Previous repair attempts (to avoid repeating failed approaches)
"""

import re
from pathlib import Path
from typing import Optional, List
from agno.agent import Agent

from js2vue.agents.runner_agent import ErrorEntry
from js2vue.utils.metrics import RepairAttempt


def create_healer_agent(model):
    """
    Factory function to create APRA agent.

    Args:
        model: LLM model instance (OpenAIChat or Gemini)

    Returns:
        Agent configured for automatic program repair
    """
    return Agent(
        model=model,
        instructions="""You are an expert Vue 3 TypeScript debugger specializing in fixing translated code.

Your expertise:
- Fixing TypeScript type inference errors
- Resolving template-script binding issues
- Adding missing imports (especially Vue imports like ref, reactive, computed)
- Correcting Vue 3 Composition API usage
- Fixing reactivity issues (ref, reactive, computed)
- Fixing Vite compilation errors (especially <script setup> export issues)
- Resolving component registration and prop passing errors

When fixing errors:
1. Understand the root cause from the error message and repair strategy
2. Apply minimal, targeted fixes (don't rewrite entire files unless necessary)
3. Preserve existing code structure and style
4. Add TypeScript types where needed
5. Follow Vue 3 Composition API best practices
6. If previous attempts failed, try a different approach
7. CRITICAL: <script setup> components should NEVER export anything via export default or export {}

Common patterns:
- Missing Vue imports: Add `import { ref, reactive, computed } from 'vue'` at top
- Vite compile error "export is not defined": Remove export statements from <script setup>
- Template binding errors: Variables must be refs (use .value in script, not in template)
- Type errors: Add proper TypeScript annotations for refs and props
- Component registration: Use PascalCase in template, import at top of script

Return ONLY the complete fixed Vue SFC. No explanations, no markdown code blocks, just the raw Vue file content.""",
        markdown=False
    )


def repair_vue_file(
    healer_agent: Agent,
    broken_code: str,
    error_entry: ErrorEntry,
    file_path: str,
    original_js_code: Optional[str] = None,
    previous_attempts: Optional[List[RepairAttempt]] = None
) -> str:
    """
    Repair a single Vue file based on error analysis.

    Args:
        healer_agent: The APRA agent instance
        broken_code: Current broken Vue SFC code
        error_entry: ErrorEntry with error details and repair strategy
        file_path: Relative path to the file (for context)
        original_js_code: Original JavaScript code (for reference)
        previous_attempts: History of previous repair attempts for this file

    Returns:
        Fixed Vue SFC code

    Raises:
        Exception: If repair fails or agent returns invalid output
    """
    # Build context-rich prompt
    prompt = build_repair_prompt(
        broken_code, error_entry, file_path, original_js_code, previous_attempts
    )

    # Run APRA agent
    response = healer_agent.run(prompt)

    # Extract fixed code
    if hasattr(response, 'content'):
        fixed_code = response.content
    else:
        fixed_code = str(response)

    # Clean LLM output (remove markdown wrappers if present)
    fixed_code = clean_llm_output(fixed_code)

    return fixed_code


def build_repair_prompt(
    broken_code: str,
    error_entry: ErrorEntry,
    file_path: str,
    original_js_code: Optional[str],
    previous_attempts: Optional[List[RepairAttempt]]
) -> str:
    """
    Build comprehensive repair prompt with all available context.

    Args:
        broken_code: Current broken Vue SFC
        error_entry: Error analysis from Runner Agent
        file_path: Relative file path
        original_js_code: Original JS code (optional)
        previous_attempts: Previous repair attempts (optional)

    Returns:
        Complete prompt for APRA agent
    """
    lines = []

    # Header
    lines.append("# Fix Vue 3 Component Error")
    lines.append("")

    # Current error details
    lines.append("## CURRENT ERROR")
    lines.append(f"**File:** {file_path}")
    lines.append(f"**Line:** {error_entry.source_error.line}")
    lines.append(f"**Priority:** {error_entry.priority}")
    lines.append(f"**Category:** {error_entry.category}")
    lines.append(f"**Root Cause:** {'Yes' if error_entry.root_cause else 'No'}")
    lines.append(f"**Message:** {error_entry.source_error.message}")
    lines.append("")

    # Repair strategy from Runner Agent
    lines.append("## SUGGESTED REPAIR STRATEGY")
    lines.append(error_entry.repair_strategy)
    lines.append("")

    # Dependencies (what this error blocks)
    if error_entry.blocks:
        lines.append("## DEPENDENCIES")
        lines.append(f"Fixing this error will unblock: {', '.join(error_entry.blocks)}")
        lines.append("")

    # Current broken code
    lines.append("## CURRENT CODE (BROKEN)")
    lines.append("```vue")
    lines.append(broken_code)
    lines.append("```")
    lines.append("")

    # Original JavaScript (if available)
    if original_js_code:
        lines.append("## ORIGINAL JAVASCRIPT (for reference)")
        lines.append("This was the original JavaScript code before translation to Vue.")
        lines.append("Use this to understand the intended behavior.")
        lines.append("```javascript")
        lines.append(original_js_code)
        lines.append("```")
        lines.append("")

    # Previous attempts (if any)
    if previous_attempts and len(previous_attempts) > 0:
        lines.append("## PREVIOUS REPAIR ATTEMPTS")
        lines.append("These approaches have already been tried and did not fully resolve the error:")
        for i, attempt in enumerate(previous_attempts, 1):
            lines.append(f"\n**Attempt {attempt.iteration}:**")
            lines.append(f"- Strategy: {attempt.repair_strategy}")
            lines.append(f"- Result: {'Success' if attempt.success else 'Failed'}")
            lines.append(f"- Errors before: {attempt.errors_before}, after: {attempt.errors_after}")
        lines.append("")
        lines.append("**Try a different approach this time!**")
        lines.append("")

    # Task instructions
    lines.append("## YOUR TASK")
    lines.append("1. Analyze the error in context of the suggested repair strategy")
    lines.append("2. If previous attempts failed, try a different approach")
    lines.append("3. Apply the minimal fix needed to resolve the error")
    lines.append("4. Return the complete fixed Vue SFC")
    lines.append("")
    lines.append("**IMPORTANT:** Return ONLY the fixed Vue code. No explanations, no markdown code blocks, just the raw .vue file content.")
    lines.append("")

    return '\n'.join(lines)


def load_original_js(
    datasets_root: Path,
    dataset_name: str,
    vue_file_path: str
) -> Optional[str]:
    """
    Try to find and load the original JavaScript file corresponding to a Vue file.

    Args:
        datasets_root: Root directory containing datasets
        dataset_name: Name of the dataset (e.g., "todomvc-es6")
        vue_file_path: Relative path to Vue file (e.g., "src/helpers.vue")

    Returns:
        Original JavaScript code if found, None otherwise

    Example:
        vue_file_path = "src/components/TodoItem.vue"
        → Look for datasets/todomvc-es6/src/components/TodoItem.js
    """
    if not datasets_root.exists():
        return None

    dataset_path = datasets_root / dataset_name

    # Remove .vue extension, add .js
    # Try both with and without src/ prefix
    possible_paths = []

    # Extract base name
    vue_path = Path(vue_file_path)
    base_name = vue_path.stem  # Remove .vue
    parent_dirs = vue_path.parent

    # Try with full path structure
    js_path_1 = dataset_path / parent_dirs / f"{base_name}.js"
    possible_paths.append(js_path_1)

    # Try without src/ prefix
    if str(parent_dirs).startswith("src"):
        relative_to_src = Path(str(parent_dirs).replace("src/", "", 1))
        js_path_2 = dataset_path / relative_to_src / f"{base_name}.js"
        possible_paths.append(js_path_2)

    # Try just the filename in dataset root
    js_path_3 = dataset_path / f"{base_name}.js"
    possible_paths.append(js_path_3)

    # Try to read from any of the possible paths
    for js_path in possible_paths:
        if js_path.exists():
            try:
                with open(js_path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception as e:
                print(f"      ⚠️  Failed to read {js_path}: {e}")
                continue

    return None


def clean_llm_output(code: str) -> str:
    """
    Clean LLM output to extract pure Vue SFC code.

    Removes:
    - Markdown code blocks (```vue, ```, etc.)
    - Explanatory text before/after code
    - Extra whitespace

    Args:
        code: Raw LLM output

    Returns:
        Clean Vue SFC code
    """
    # Remove markdown code blocks
    if '```vue' in code:
        code = code.split('```vue')[1].split('```')[0]
    elif '```' in code:
        code = code.split('```')[1].split('```')[0]

    # Ensure it starts with <template> or <script>
    # Find the first occurrence of <template or <script
    match = re.search(r'<(template|script)', code, re.IGNORECASE)
    if match:
        code = code[match.start():]

    # Clean up trailing content after closing tags
    # Vue SFCs should end with </template>, </script>, or </style>
    last_closing_tag = max(
        code.rfind('</template>'),
        code.rfind('</script>'),
        code.rfind('</style>')
    )

    if last_closing_tag != -1:
        # Include the closing tag itself (add length of tag)
        if '</template>' in code[last_closing_tag:last_closing_tag + 15]:
            code = code[:last_closing_tag + len('</template>')]
        elif '</script>' in code[last_closing_tag:last_closing_tag + 15]:
            code = code[:last_closing_tag + len('</script>')]
        elif '</style>' in code[last_closing_tag:last_closing_tag + 15]:
            code = code[:last_closing_tag + len('</style>')]

    return code.strip()
