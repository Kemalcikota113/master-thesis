"""Runtime error capture using Playwright + Vite dev server."""

import asyncio
import subprocess
import time
import signal
import re
import threading
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from playwright.async_api import async_playwright, Page, ConsoleMessage, Error as PlaywrightError
import aiohttp


@dataclass
class RuntimeError:
    """Structured runtime error from browser."""
    file: str              # Source file (from stack trace)
    line: int              # Line number
    message: str           # Error message
    error_type: str        # 'console' | 'exception' | 'vue' | 'network'
    stack: str = ""        # Full stack trace
    timestamp: str = ""    # ISO timestamp
    component: str = ""    # Vue component name (if available)
    severity: str = "error"  # 'error' | 'warning'


def parse_vite_error(error_text: str, debug: bool = False) -> Optional[RuntimeError]:
    """
    Parse Vite compilation error from server output.

    Args:
        error_text: Error text from Vite stdout/stderr
        debug: If True, print debug information

    Returns:
        RuntimeError if parsable, None otherwise
    """
    if debug:
        print(f"\n[DEBUG] Parsing error text ({len(error_text)} chars):")
        print("=" * 70)
        print(error_text[:500])
        print("=" * 70)
    # Vite error patterns:
    # [@vue/compiler-sfc] <script setup> cannot contain ES module exports...
    # /path/to/file.vue
    # line |  code
    #
    # Failed to resolve import "./view" from "src/src/app.vue"
    # Plugin: vite:import-analysis
    # File: /path/to/file.vue:line:col

    # Pattern 1: [@vue/compiler-sfc] errors
    vue_compiler_pattern = r'\[@vue/compiler-sfc\]\s+(.+?)(?:\n\n|$)'
    match = re.search(vue_compiler_pattern, error_text, re.DOTALL)
    if match:
        message = match.group(1).split('\n')[0].strip()

        # Extract file path - try multiple patterns
        file_path = "unknown"
        line_num = 0

        # Pattern 1: Full path on its own line (/home/user/.../file.vue)
        # Allow optional whitespace around the path
        full_path_pattern = r'^\s*(/[^\s]+\.vue)\s*$'
        path_match = re.search(full_path_pattern, error_text, re.MULTILINE)
        if path_match:
            file_path = path_match.group(1)
            # Make relative - look for /src/ in path
            if '/src/' in file_path:
                file_path = 'src/' + file_path.split('/src/')[-1]

        # Pattern 2: File in "File: /path/to/file.vue" format
        if file_path == "unknown":
            file_in_error = r'File:\s*(/[^\s]+\.vue)'
            path_match = re.search(file_in_error, error_text)
            if path_match:
                file_path = path_match.group(1)
                if '/src/' in file_path:
                    file_path = 'src/' + file_path.split('/src/')[-1]

        # Pattern 3: Look for any .vue file path in the error
        if file_path == "unknown":
            any_vue_pattern = r'([^\s]+/src/[^\s]+\.vue)'
            path_match = re.search(any_vue_pattern, error_text)
            if path_match:
                full = path_match.group(1)
                if '/src/' in full:
                    file_path = 'src/' + full.split('/src/')[-1]

        # Extract line number - look for the line with the most ^ markers
        # That's the actual error line
        line_with_most_markers = 0
        max_markers = 0

        lines = error_text.split('\n')
        for i, line in enumerate(lines):
            # Look for lines with | marker followed by a line with ^
            match = re.match(r'^\s*(\d+)\s*\|', line)
            if match and i + 1 < len(lines):
                next_line = lines[i + 1]
                marker_count = next_line.count('^')
                if marker_count > max_markers:
                    max_markers = marker_count
                    line_with_most_markers = int(match.group(1))

        if line_with_most_markers > 0:
            line_num = line_with_most_markers
        else:
            # Fallback: any line with | marker
            line_pattern_simple = r'^\s*(\d+)\s*\|'
            line_match = re.search(line_pattern_simple, error_text, re.MULTILINE)
            if line_match:
                line_num = int(line_match.group(1))

        # Clean message - keep it concise
        # Remove URLs from message for cleaner display
        clean_message = message.split('. If you are using')[0]
        clean_message = clean_message.split('. Does the file exist')[0]

        return RuntimeError(
            file=file_path,
            line=line_num,
            message=f"[Vite] {clean_message}",
            error_type='vite-compile',
            stack=error_text[:500],  # Truncate long errors
            timestamp=datetime.now().isoformat(),
            severity='error'
        )

    # Pattern 2: Failed to resolve import
    import_pattern = r'Failed to resolve import "([^"]+)" from "([^"]+)"'
    match = re.search(import_pattern, error_text)
    if match:
        import_path = match.group(1)
        from_file = match.group(2)

        # Extract line if available - try multiple patterns
        line_num = 0

        # Pattern 1: File: /path/to/file.vue:line:col
        line_pattern_full = r'File:\s*[^\s]+:(\d+):\d+'
        line_match = re.search(line_pattern_full, error_text)
        if line_match:
            line_num = int(line_match.group(1))
        else:
            # Pattern 2: Line with | and ^ marker
            line_pattern_marker = r'^\s*(\d+)\s*\|[^\n]*\n[^\n]*\^'
            line_match = re.search(line_pattern_marker, error_text, re.MULTILINE)
            if line_match:
                line_num = int(line_match.group(1))

        return RuntimeError(
            file=from_file,
            line=line_num,
            message=f'[Vite] Failed to resolve import "{import_path}"',
            error_type='vite-compile',
            stack=error_text[:500],
            timestamp=datetime.now().isoformat(),
            severity='error'
        )

    # Pattern 3: Internal server error (generic)
    if 'Internal server error' in error_text:
        # Try to extract file from error
        file_pattern = r'File: ([^\s]+\.vue)'
        file_match = re.search(file_pattern, error_text)
        file_path = file_match.group(1) if file_match else "unknown"

        # Get first meaningful line as message
        lines = [l.strip() for l in error_text.split('\n') if l.strip()]
        message = lines[0] if lines else "Internal server error"

        # Clean up message
        if 'Internal server error:' in message:
            message = message.split('Internal server error:')[-1].strip()

        return RuntimeError(
            file=file_path,
            line=0,
            message=f"[Vite] {message}",
            error_type='vite-compile',
            stack=error_text[:500],
            timestamp=datetime.now().isoformat(),
            severity='error'
        )

    return None


def parse_stack_trace(stack: str) -> tuple[str, int]:
    """
    Extract file path and line number from JavaScript stack trace.

    Args:
        stack: JavaScript stack trace string

    Returns:
        Tuple of (file_path, line_number)
    """
    # Common stack trace patterns:
    # at file:///path/to/file.vue:42:10
    # at Object.<anonymous> (file.js:10:5)
    # at http://localhost:5173/src/App.vue:15:20

    patterns = [
        r'(?:at\s+)?(?:.*?\()?(?:https?://[^/]+)?(/[^:)]+):(\d+):\d+',
        r'(?:at\s+)?(?:file://)?([^:)]+):(\d+):\d+',
    ]

    for pattern in patterns:
        match = re.search(pattern, stack)
        if match:
            file_path = match.group(1)
            line_num = int(match.group(2))

            # Clean up file path
            file_path = file_path.strip()
            if file_path.startswith('/src/'):
                file_path = file_path[1:]  # Remove leading /
            elif '/@fs/' in file_path:
                # Vite serves local files with /@fs/ prefix
                file_path = file_path.split('/@fs/')[-1]

            return file_path, line_num

    # Fallback
    return "unknown", 0


def monitor_vite_output(process: subprocess.Popen, errors: List[RuntimeError], stop_event: threading.Event):
    """
    Monitor Vite server output in a background thread.

    Args:
        process: Vite server process
        errors: List to append parsed errors to
        stop_event: Event to signal when to stop monitoring
    """
    import select

    # Read from both stdout and stderr
    outputs = []
    if process.stdout:
        outputs.append(process.stdout)
    if process.stderr:
        outputs.append(process.stderr)

    if not outputs:
        return

    current_error_lines = []
    in_error_block = False

    # Read until stop event or process ends
    while not stop_event.is_set() and process.poll() is None:
        # Check if there's data to read (with timeout)
        try:
            # Use select on Unix-like systems, simple read on Windows
            import sys
            if sys.platform != 'win32':
                ready, _, _ = select.select(outputs, [], [], 0.1)
                if not ready:
                    continue
                stream = ready[0]
            else:
                stream = process.stderr if process.stderr else process.stdout

            line = stream.readline()
            if not line:
                continue

            # Check for error indicators
            error_indicators = [
                '[vite] Pre-transform error:',
                '[vite] Internal server error:',
                'Error:',
                'Plugin:',
                'File:'
            ]

            if any(indicator in line for indicator in error_indicators):
                # Start of error block
                if in_error_block and current_error_lines:
                    # Previous error complete, parse it
                    error_text = ''.join(current_error_lines)
                    parsed_error = parse_vite_error(error_text)
                    if parsed_error:
                        errors.append(parsed_error)

                # Start new error block
                in_error_block = True
                current_error_lines = [line]
            elif in_error_block:
                current_error_lines.append(line)

                # Check if error block is complete
                # Error blocks end with NEW timestamp line (e.g., "3:38:24 PM [vite]")
                # NOT just any blank line (file paths come after blank lines!)
                is_new_log_entry = (
                    not line.startswith('  ') and
                    ':' in line and
                    ('PM' in line or 'AM' in line) and
                    '[vite]' in line
                )

                # Also end on "at " lines (stack traces are at the end)
                is_stack_trace_end = line.strip().startswith('at async') or line.strip().startswith('at process.')

                if is_new_log_entry or (is_stack_trace_end and len(current_error_lines) > 10):
                    # Parse the complete error
                    error_text = ''.join(current_error_lines)
                    parsed_error = parse_vite_error(error_text, debug=False)  # Set to True for debugging
                    if parsed_error:
                        errors.append(parsed_error)
                        print(f"   [Captured] {parsed_error.file}:{parsed_error.line} - {parsed_error.message[:60]}")
                    else:
                        print(f"   [WARNING] Failed to parse error block ({len(error_text)} chars)")

                    current_error_lines = []
                    in_error_block = False

        except Exception as e:
            # Continue on read errors
            continue

    # Parse any remaining error
    if in_error_block and current_error_lines:
        error_text = ''.join(current_error_lines)
        parsed_error = parse_vite_error(error_text, debug=False)
        if parsed_error:
            errors.append(parsed_error)
            print(f"   [Captured] {parsed_error.file}:{parsed_error.line} - {parsed_error.message[:60]}")
        else:
            print(f"   [WARNING] Failed to parse remaining error block")


async def start_vite_server(project_dir: Path, port: int = 5173) -> subprocess.Popen:
    """
    Start Vite dev server as a subprocess.

    Args:
        project_dir: Path to Vue project root
        port: Port to run server on (default: 5173)

    Returns:
        Popen process object
    """
    import os

    # Start Vite dev server in its own process group so we can kill all children
    process = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(port)],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        preexec_fn=os.setsid  # Create new process group
    )

    return process


async def wait_for_server(port: int = 5173, timeout: int = 60) -> bool:
    """
    Poll server until it responds or timeout.

    Args:
        port: Port to check
        timeout: Maximum wait time in seconds

    Returns:
        True if server is ready, False if timeout
    """
    url = f"http://localhost:{port}"
    start_time = time.time()

    async with aiohttp.ClientSession() as session:
        while time.time() - start_time < timeout:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                    if response.status == 200:
                        print(f"   Vite server ready at {url}")
                        return True
            except (aiohttp.ClientError, asyncio.TimeoutError):
                # Server not ready yet
                await asyncio.sleep(1)
                continue

    return False


async def setup_error_listeners(page: Page, errors: List[RuntimeError]):
    """
    Configure Playwright event handlers to capture errors.

    Args:
        page: Playwright page object
        errors: List to append captured errors to
    """

    # Capture console errors and warnings
    def on_console(msg: ConsoleMessage):
        if msg.type in ['error', 'warning']:
            timestamp = datetime.now().isoformat()
            text = msg.text

            # Try to extract location from console message
            location = msg.location
            file_path = location.get('url', 'unknown')
            line_num = location.get('lineNumber', 0)

            # Parse file path
            if file_path.startswith('http://localhost:'):
                file_path = file_path.split('localhost:' + str(5173))[-1]
                if file_path.startswith('/'):
                    file_path = file_path[1:]

            errors.append(RuntimeError(
                file=file_path or 'unknown',
                line=line_num,
                message=text,
                error_type='console',
                timestamp=timestamp,
                severity=msg.type
            ))

    # Capture uncaught exceptions
    def on_page_error(error: PlaywrightError):
        timestamp = datetime.now().isoformat()
        error_str = str(error)

        # Extract file and line from error
        file_path, line_num = parse_stack_trace(error_str)

        errors.append(RuntimeError(
            file=file_path,
            line=line_num,
            message=error_str.split('\n')[0],  # First line is usually the error message
            error_type='exception',
            stack=error_str,
            timestamp=timestamp,
            severity='error'
        ))

    page.on('console', on_console)
    page.on('pageerror', on_page_error)


async def inject_vue_error_handler(page: Page, errors: List[RuntimeError]):
    """
    Inject global Vue error handler to capture Vue-specific errors.

    Args:
        page: Playwright page object
        errors: List to append captured errors to
    """
    await page.evaluate("""
        () => {
            // Wait for Vue app to be available
            const checkVue = setInterval(() => {
                if (window.__VUE_DEVTOOLS_GLOBAL_HOOK__) {
                    clearInterval(checkVue);

                    // Try to access Vue app instance
                    const apps = window.__VUE_DEVTOOLS_GLOBAL_HOOK__.apps;
                    if (apps && apps.length > 0) {
                        const app = apps[0];

                        // Set global error handler
                        app.config.errorHandler = (err, instance, info) => {
                            console.error('[Vue Error]', err.message, 'in', info);
                            console.error(err.stack);
                        };

                        // Set warning handler
                        app.config.warnHandler = (msg, instance, trace) => {
                            console.warn('[Vue Warning]', msg);
                        };
                    }
                }
            }, 100);

            // Cleanup after 5 seconds if Vue not found
            setTimeout(() => clearInterval(checkVue), 5000);
        }
    """)


def cleanup_server(process: subprocess.Popen):
    """
    Gracefully terminate Vite server process and all children.

    Args:
        process: Vite server process
    """
    import os

    try:
        # Kill the entire process group (parent + all children)
        # This ensures Vite and all its child processes (esbuild, etc.) are killed
        pgid = os.getpgid(process.pid)
        os.killpg(pgid, signal.SIGTERM)

        # Wait for graceful shutdown
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill if graceful shutdown fails
            os.killpg(pgid, signal.SIGKILL)
            process.wait()

    except (ProcessLookupError, OSError):
        # Process already dead, that's fine
        pass


async def capture_runtime_errors(
    project_dir: Path,
    port: int = 5173,
    capture_duration_seconds: int = 30
) -> List[RuntimeError]:
    """
    Start Vite dev server, launch browser, capture all runtime errors.

    Captures:
    - Vite compilation errors (from server stdout/stderr)
    - Browser console errors
    - Uncaught exceptions
    - Vue lifecycle errors

    Args:
        project_dir: Path to Vue project root
        port: Port for Vite dev server (default: 5173)
        capture_duration_seconds: How long to capture errors (default: 30)

    Returns:
        List of RuntimeError objects (both compilation and runtime errors)
    """
    errors: List[RuntimeError] = []
    vite_process: Optional[subprocess.Popen] = None
    monitor_thread: Optional[threading.Thread] = None
    stop_monitoring = threading.Event()

    try:
        # Step 1: Start Vite dev server
        print(f"   Starting Vite dev server on port {port}...")
        vite_process = await start_vite_server(project_dir, port)

        # Step 2: Start monitoring Vite output for compilation errors
        monitor_thread = threading.Thread(
            target=monitor_vite_output,
            args=(vite_process, errors, stop_monitoring),
            daemon=True
        )
        monitor_thread.start()

        # Step 3: Give Vite a moment to log any immediate compilation errors
        await asyncio.sleep(3)

        # Step 4: Wait for server to be ready (or fail with compilation errors)
        server_ready = await wait_for_server(port, timeout=60)

        if not server_ready:
            print(f"   ⚠️  Vite server failed to start within 60 seconds")
            # Still return compilation errors we captured
            await asyncio.sleep(2)  # Give monitor thread time to capture errors
            return errors

        # Step 5: Launch headless browser (only if server is ready)
        print(f"   Launching headless browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Step 6: Setup error listeners
            await setup_error_listeners(page, errors)

            # Step 7: Navigate to app
            url = f"http://localhost:{port}"
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception as e:
                print(f"   ⚠️  Navigation error: {e}")
                # Continue anyway - we might still capture errors

            # Step 8: Inject Vue error handler
            try:
                await inject_vue_error_handler(page, errors)
            except Exception as e:
                print(f"   ⚠️  Could not inject Vue error handler: {e}")

            # Step 9: Wait and capture errors
            print(f"   Capturing errors for {capture_duration_seconds}s...")
            await asyncio.sleep(capture_duration_seconds)

            # Cleanup
            await browser.close()

    except Exception as e:
        print(f"   ⚠️  Runtime capture failed: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # Give monitor thread a bit more time to capture final errors
        await asyncio.sleep(1)

        # Stop monitoring thread
        stop_monitoring.set()
        if monitor_thread and monitor_thread.is_alive():
            monitor_thread.join(timeout=3)

        # Always cleanup Vite server
        if vite_process:
            print(f"   Stopping Vite server...")
            cleanup_server(vite_process)
            # Give the OS time to release the port
            await asyncio.sleep(1)

        print(f"   Total errors captured: {len(errors)}")

    # Deduplicate errors (same file + line + message)
    seen = set()
    unique_errors = []
    for error in errors:
        key = (error.file, error.line, error.message[:100])  # First 100 chars of message
        if key not in seen:
            seen.add(key)
            unique_errors.append(error)

    return unique_errors
