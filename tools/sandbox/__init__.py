"""Sandbox executor for isolated tool execution in Docker containers."""

import asyncio
import json
import logging
from pathlib import Path

from .config import ExecutionResult, SandboxConfig

logger = logging.getLogger(__name__)


class SandboxExecutor:
    """Execute tools in isolated Docker containers.

    Provides security isolation, resource limits, and filesystem
    restrictions for tool execution.
    """

    def __init__(self, config: SandboxConfig | None = None):
        """Initialize sandbox executor.

        Args:
            config: Sandbox configuration, uses defaults if not provided
        """
        self.config = config or SandboxConfig()
        self._client = None
        self._containers: set[str] = set()

    async def _get_client(self):
        """Lazy initialization of Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except ImportError:
                raise RuntimeError(
                    "Docker SDK not installed. Run: uv add docker"
                )
            except Exception as e:
                raise RuntimeError(f"Failed to connect to Docker: {e}")
        return self._client

    async def run_tool(
        self,
        tool_name: str,
        args: dict,
        tool_code: str | None = None,
    ) -> ExecutionResult:
        """Execute a tool in sandbox container.

        Args:
            tool_name: Name of the tool to execute
            args: Arguments to pass to the tool
            tool_code: Optional Python code to execute (for builtin tools)

        Returns:
            ExecutionResult with output, error, and status
        """
        try:
            client = await self._get_client()

            # Prepare execution script
            script = self._prepare_script(tool_name, args, tool_code)

            # Create and run container
            container = await asyncio.to_thread(
                self._create_and_run_container,
                client,
                script,
            )
            self._containers.add(container.id)

            # Wait for execution with timeout
            result = await asyncio.to_thread(
                self._wait_and_get_result,
                container,
                self.config.timeout,
            )

            return result

        except Exception as e:
            logger.error(f"Sandbox execution failed: {e}")
            return ExecutionResult(
                output="",
                error=str(e),
                exit_code=-1,
                timed_out=False,
            )

    def _prepare_script(
        self,
        tool_name: str,
        args: dict,
        tool_code: str | None,
    ) -> str:
        """Prepare Python script to execute in container.

        The script:
        1. Installs pip packages if configured
        2. Includes necessary imports
        3. Strips @tool decorator from tool code
        4. Embeds the tool function
        5. Calls the function with provided args
        6. Prints result
        """
        args_json = json.dumps(args)

        # Pre-install pip packages if configured
        pip_install = ""
        if self.config.pip_packages:
            pip_install = f'''
import subprocess
subprocess.run(["pip", "install", "-q"] + {json.dumps(self.config.pip_packages)}, check=True)
'''

        if tool_code:
            # Strip @tool decorator block (multi-line support)
            lines = tool_code.split('\n')
            cleaned_lines = []
            in_decorator = False
            paren_count = 0
            for i, line in enumerate(lines):
                stripped = line.strip()
                # Detect start of decorator block
                if stripped.startswith('@tool') or (stripped.startswith('@') and not in_decorator):
                    in_decorator = True
                    # Count parentheses in the decorator line
                    paren_count += stripped.count('(') - stripped.count(')')
                    if paren_count <= 0:
                        in_decorator = False
                    continue
                # Inside decorator block
                if in_decorator:
                    paren_count += stripped.count('(') - stripped.count(')')
                    if paren_count <= 0:
                        in_decorator = False
                    continue
                cleaned_lines.append(line)
            cleaned_code = '\n'.join(cleaned_lines)

            # Find the function name
            import re
            func_match = re.search(r'def\s+(\w+)\s*\(', cleaned_code)
            func_name = func_match.group(1) if func_match else tool_name

            # Standard imports used by builtin tools (all from Python standard library)
            standard_imports = '''
import json
import os
import sys
import subprocess
from pathlib import Path
import datetime
import math
import re
import shutil
import tempfile
import glob
import hashlib
import time
'''

            # Add external imports if pip packages configured
            if self.config.pip_packages:
                for pkg in self.config.pip_packages:
                    if pkg == "httpx":
                        standard_imports += "import httpx\n"
                    elif pkg.startswith("duckduckgo"):
                        standard_imports += "from duckduckgo_search import DDGS\n"

            # Build script with tool code
            script = f'''
{pip_install}
{standard_imports}

# Tool arguments
args = json.loads('{args_json}')

# --- Tool Code ---
{cleaned_code}
# --- End Tool Code ---

# Execute tool
try:
    result = {func_name}(**args)
    if not isinstance(result, str):
        result = json.dumps(result, ensure_ascii=False)
    print(result)
except Exception as e:
    import traceback
    print(json.dumps({{"error": str(e), "error_type": type(e).__name__, "traceback": traceback.format_exc()}}))
'''
        else:
            # No tool code provided - fallback to direct execution
            script = f'''
import json
print(json.dumps({{"error": "Tool code not provided", "tool": "{tool_name}"}}))
'''

        return script

    def _create_and_run_container(self, client, script: str):
        """Create and start a container with the script."""
        volumes = {}

        # Mount read directories
        for dir_path in self.config.read_dirs:
            p = Path(dir_path).resolve()
            if p.exists():
                volumes[str(p)] = {
                    "bind": str(p),
                    "mode": "ro",
                }

        # Mount write directories
        for dir_path in self.config.write_dirs:
            p = Path(dir_path).resolve()
            if p.exists():
                volumes[str(p)] = {
                    "bind": str(p),
                    "mode": "rw",
                }

        # Mount host /usr/bin for shell commands (bash tool)
        # This allows container to use host's system commands like ls, cat, grep, git
        if self.config.mount_host_bin:
            volumes["/usr/bin"] = {
                "bind": "/host/bin",
                "mode": "ro",
            }

        container = client.containers.run(
            self.config.image,
            command=["python", "-c", script],
            detach=True,
            remove=False,
            mem_limit=self.config.memory_limit,
            cpu_quota=int(self.config.cpu_limit * 100000),
            network_disabled=self.config.network_disabled,
            volumes=volumes,
            working_dir="/workspace",
        )

        return container

    def _wait_and_get_result(
        self,
        container,
        timeout: int,
    ) -> ExecutionResult:
        """Wait for container and extract result."""
        try:
            status = container.wait(timeout=timeout)

            stdout = container.logs(stdout=True, stderr=False).decode()
            stderr = container.logs(stdout=False, stderr=True).decode()

            exit_code = status.get("StatusCode", -1)
            timed_out = exit_code == 137  # OOM or timeout kill

            return ExecutionResult(
                output=stdout.strip(),
                error=stderr.strip(),
                exit_code=exit_code,
                timed_out=timed_out,
            )

        finally:
            # Cleanup container
            try:
                container.remove(force=True)
                self._containers.discard(container.id)
            except Exception:
                pass

    async def cleanup(self) -> None:
        """Clean up all tracked containers."""
        client = await self._get_client()

        for container_id in list(self._containers):
            try:
                container = client.containers.get(container_id)
                container.remove(force=True)
                self._containers.discard(container_id)
            except Exception:
                self._containers.discard(container_id)

    async def health_check(self) -> bool:
        """Check if Docker is available and running."""
        try:
            client = await self._get_client()
            client.ping()
            return True
        except Exception as e:
            logger.warning(f"Docker health check failed: {e}")
            return False


# Module exports
__all__ = ["SandboxExecutor", "SandboxConfig", "ExecutionResult"]