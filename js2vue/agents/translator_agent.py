"""
Translator agent: Converts JavaScript code to Vue 3 SFC with TypeScript.
"""

from agno.agent import Agent
from js2vue.utils.code_cleaning import clean_llm_output


# System instructions for the translator agent
TRANSLATOR_INSTRUCTIONS = """You are an expert JavaScript to Vue 3 translator. Your task is to convert JavaScript code into a Vue 3 Single File Component (SFC) with TypeScript.

## Requirements

### 1. Composition API with <script setup>
- Use `<script setup lang="ts">` syntax
- Import Vue APIs: `ref`, `reactive`, `computed`, `watch`, etc.
- Define props with `defineProps<Props>()`
- Define emits with `defineEmits<Emits>()`

### 2. Reactive State Management
- Use `ref()` for primitive values
- Use `reactive()` for objects and arrays
- Use `computed()` for derived state
- Properly type all reactive state

### 3. TypeScript Types
- Define interfaces for props, emits, and complex state
- Add type annotations to functions and variables
- Ensure type safety throughout

### 4. Vue 3 Template Syntax
- Use proper Vue directives: `v-if`, `v-for`, `v-bind`, `v-on`
- Use shorthand syntax: `:attr`, `@event`
- Bind data from `<script setup>` to template correctly
- Handle events with proper TypeScript typing

### 5. Component Structure
```vue
<template>
  <!-- HTML template with Vue directives -->
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

// Interfaces/Types
interface Props {
  // ...
}

// Props and Emits
const props = defineProps<Props>()
const emit = defineEmits<{
  eventName: [payload: Type]
}>()

// State
const state = ref<Type>(initialValue)

// Methods
const handleAction = () => {
  // ...
}
</script>

<style scoped>
/* Component-specific styles */
</style>
```

### 6. Common Patterns to Handle

**Event Handling:**
```vue
<!-- Template -->
<button @click="handleClick">Click</button>

<!-- Script -->
const handleClick = (event: MouseEvent) => {
  // ...
}
```

**Conditional Rendering:**
```vue
<div v-if="condition">...</div>
<div v-else>...</div>
```

**List Rendering:**
```vue
<div v-for="item in items" :key="item.id">
  {{ item.name }}
</div>
```

**Two-way Binding:**
```vue
<input v-model="value" />
```

### 7. Important Notes
- Output ONLY the Vue SFC code, no explanations
- Do not include markdown code fences (```)
- Ensure all template bindings have corresponding script declarations
- Make reasonable assumptions for missing type information
- Preserve the original functionality and logic
"""


def create_translator_agent(model) -> Agent:
    """
    Creates a translator agent with the specified model.

    Args:
        model: LLM model instance (from config.get_model())

    Returns:
        Configured Agno Agent
    """
    return Agent(
        model=model,
        instructions=TRANSLATOR_INSTRUCTIONS,
        markdown=False  # We want raw code output
    )


def translate_js_to_vue(
    agent: Agent,
    js_code: str,
    component_name: str,
    file_path: str = ""
) -> str:
    """
    Translates JavaScript code to Vue 3 SFC using the agent.

    Args:
        agent: Translator agent instance
        js_code: JavaScript source code
        component_name: Name of the component (PascalCase)
        file_path: Original file path (for context)

    Returns:
        Vue 3 SFC code (cleaned)

    Example:
        >>> agent = create_translator_agent(model)
        >>> vue_code = translate_js_to_vue(
        ...     agent,
        ...     "const hello = 'world';",
        ...     "HelloWorld",
        ...     "src/components/HelloWorld.js"
        ... )
    """
    # Build the translation prompt
    prompt = f"""Translate the following JavaScript code to a Vue 3 SFC component.

Component Name: {component_name}
Original File: {file_path}

JavaScript Code:
```javascript
{js_code}
```

Output the complete Vue 3 SFC with TypeScript. Include <template>, <script setup lang="ts">, and <style scoped> sections."""

    # Run the agent
    response = agent.run(prompt)

    # Extract content from response
    if hasattr(response, 'content'):
        vue_code = response.content
    elif isinstance(response, str):
        vue_code = response
    else:
        vue_code = str(response)

    # Clean the output
    vue_code = clean_llm_output(vue_code)

    return vue_code


def get_token_usage(response) -> tuple[int, int]:
    """
    Extracts token usage from agent response.

    Args:
        response: Agent response object

    Returns:
        Tuple of (prompt_tokens, completion_tokens)
    """
    # Try to extract token usage from response
    # Different providers may have different response structures

    prompt_tokens = 0
    completion_tokens = 0

    if hasattr(response, 'usage'):
        usage = response.usage
        if hasattr(usage, 'prompt_tokens'):
            prompt_tokens = usage.prompt_tokens
        if hasattr(usage, 'completion_tokens'):
            completion_tokens = usage.completion_tokens

    elif hasattr(response, 'model_dump'):
        # Try model_dump for Pydantic models
        try:
            data = response.model_dump()
            if 'usage' in data:
                prompt_tokens = data['usage'].get('prompt_tokens', 0)
                completion_tokens = data['usage'].get('completion_tokens', 0)
        except:
            pass

    return prompt_tokens, completion_tokens
