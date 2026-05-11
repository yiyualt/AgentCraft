"""Sandbox configuration for Docker container execution."""

from dataclasses import dataclass, field


@dataclass
class SandboxConfig:
    """Configuration for sandbox container execution.

    Attributes:
        image: Docker image to use for execution
        cpu_limit: CPU limit as fraction (0.5 = 50% of one CPU)
        memory_limit: Memory limit string (e.g. "256m", "512m")
        timeout: Execution timeout in seconds
        read_dirs: Directories to mount as read-only
        write_dirs: Directories to mount as writable
        network_disabled: Whether to disable network access
        pip_packages: Python packages to install before execution
        system_packages: System packages to install (apt-get)
        mount_host_bin: Mount host /usr/bin for shell commands
    """

    image: str = "python:3.13-slim"
    cpu_limit: float = 0.5
    memory_limit: str = "256m"
    timeout: int = 30
    read_dirs: list[str] = field(default_factory=list)
    write_dirs: list[str] = field(default_factory=list)
    network_disabled: bool = True
    pip_packages: list[str] = field(default_factory=list)
    system_packages: list[str] = field(default_factory=list)
    mount_host_bin: bool = False


@dataclass
class ExecutionResult:
    """Result of a sandboxed tool execution.

    Attributes:
        output: stdout from the execution
        error: stderr from the execution (if any)
        exit_code: Process exit code
        timed_out: Whether execution exceeded timeout
    """

    output: str
    error: str = ""
    exit_code: int = 0
    timed_out: bool = False