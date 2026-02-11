"""Runtime error capture using Playwright + Vite dev server."""

import asyncio
import subprocess
import time
import signal
import re
from pathlib import Path
from typing import List, Optional
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


async def start_vite_server(project_dir: Path, port: int = 5173) -> subprocess.Popen:
    """
    Start Vite dev server as a subprocess.

    Args:
        project_dir: Path to Vue project root
        port: Port to run server on (default: 5173)

    Returns:
        Popen process object
    """
    # Start Vite dev server
    process = subprocess.Popen(
        ["npm", "run", "dev", "--", "--port", str(port)],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=None if not hasattr(signal, 'SIGTERM') else lambda: signal.signal(signal.SIGTERM, signal.SIG_DFL)
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
    Gracefully terminate Vite server process.

    Args:
        process: Vite server process
    """
    try:
        # Try graceful shutdown first
        process.terminate()
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        # Force kill if graceful shutdown fails
        process.kill()
        process.wait()


async def capture_runtime_errors(
    project_dir: Path,
    port: int = 5173,
    capture_duration_seconds: int = 30
) -> List[RuntimeError]:
    """
    Start Vite dev server, launch browser, capture all runtime errors.

    Args:
        project_dir: Path to Vue project root
        port: Port for Vite dev server (default: 5173)
        capture_duration_seconds: How long to capture errors (default: 30)

    Returns:
        List of RuntimeError objects
    """
    errors: List[RuntimeError] = []
    vite_process: Optional[subprocess.Popen] = None

    try:
        # Step 1: Start Vite dev server
        print(f"   Starting Vite dev server on port {port}...")
        vite_process = await start_vite_server(project_dir, port)

        # Step 2: Wait for server to be ready
        if not await wait_for_server(port, timeout=60):
            print(f"   ⚠️  Vite server failed to start within 60 seconds")
            return errors

        # Step 3: Launch headless browser
        print(f"   Launching headless browser...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            # Step 4: Setup error listeners
            await setup_error_listeners(page, errors)

            # Step 5: Navigate to app
            url = f"http://localhost:{port}"
            try:
                await page.goto(url, wait_until='networkidle', timeout=30000)
            except Exception as e:
                print(f"   ⚠️  Navigation error: {e}")
                # Continue anyway - we might still capture errors

            # Step 6: Inject Vue error handler
            try:
                await inject_vue_error_handler(page, errors)
            except Exception as e:
                print(f"   ⚠️  Could not inject Vue error handler: {e}")

            # Step 7: Wait and capture errors
            print(f"   Capturing errors for {capture_duration_seconds}s...")
            await asyncio.sleep(capture_duration_seconds)

            # Cleanup
            await browser.close()

    except Exception as e:
        print(f"   ⚠️  Runtime capture failed: {e}")

    finally:
        # Always cleanup Vite server
        if vite_process:
            print(f"   Stopping Vite server...")
            cleanup_server(vite_process)

    return errors
