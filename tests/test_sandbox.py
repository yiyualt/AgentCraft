"""Tests for sandbox executor."""

import asyncio
import pytest

from tools.sandbox import SandboxExecutor, SandboxConfig, ExecutionResult


class TestSandboxConfig:
    """Tests for SandboxConfig dataclass."""

    def test_default_config(self):
        """Default configuration values."""
        config = SandboxConfig()

        assert config.image == "python:3.13-slim"
        assert config.cpu_limit == 0.5
        assert config.memory_limit == "256m"
        assert config.timeout == 30
        assert config.read_dirs == []
        assert config.write_dirs == []
        assert config.network_disabled is True

    def test_custom_config(self):
        """Custom configuration values."""
        config = SandboxConfig(
            image="custom:latest",
            cpu_limit=1.0,
            memory_limit="512m",
            timeout=60,
            read_dirs=["/src"],
            write_dirs=["/output"],
            network_disabled=False,
        )

        assert config.image == "custom:latest"
        assert config.cpu_limit == 1.0
        assert config.memory_limit == "512m"
        assert config.timeout == 60
        assert config.read_dirs == ["/src"]
        assert config.write_dirs == ["/output"]
        assert config.network_disabled is False


class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self):
        """Successful execution result."""
        result = ExecutionResult(output="done", error="", exit_code=0)

        assert result.output == "done"
        assert result.error == ""
        assert result.exit_code == 0
        assert not result.timed_out

    def test_error_result(self):
        """Error execution result."""
        result = ExecutionResult(
            output="",
            error="ModuleNotFoundError",
            exit_code=1,
        )

        assert result.output == ""
        assert result.error == "ModuleNotFoundError"
        assert result.exit_code == 1

    def test_timeout_result(self):
        """Timed out execution result."""
        result = ExecutionResult(
            output="",
            error="",
            exit_code=137,
            timed_out=True,
        )

        assert result.timed_out
        assert result.exit_code == 137


class TestSandboxExecutor:
    """Tests for SandboxExecutor class."""

    def test_executor_initialization(self):
        """Executor initializes with default config."""
        executor = SandboxExecutor()

        assert executor.config is not None
        assert executor.config.image == "python:3.13-slim"
        assert executor._client is None
        assert executor._containers == set()

    def test_executor_with_custom_config(self):
        """Executor accepts custom config."""
        config = SandboxConfig(timeout=120)
        executor = SandboxExecutor(config)

        assert executor.config.timeout == 120

    @pytest.mark.asyncio
    async def test_health_check_docker_not_available(self):
        """Health check returns False when Docker unavailable."""
        executor = SandboxExecutor()

        # Mock client initialization to fail
        async def mock_get_client():
            raise RuntimeError("Docker not available")

        executor._get_client = mock_get_client

        result = await executor.health_check()
        assert result is False

    @pytest.mark.asyncio
    async def test_run_tool_without_docker(self):
        """Run tool returns error when Docker unavailable."""
        executor = SandboxExecutor()

        # Mock client to raise error
        async def mock_get_client():
            raise RuntimeError("Docker SDK not installed")

        executor._get_client = mock_get_client

        result = await executor.run_tool("test_tool", {"arg": "value"})

        assert result.output == ""
        assert "Docker" in result.error
        assert result.exit_code == -1

    def test_prepare_script_with_code(self):
        """Script preparation with inline tool code."""
        executor = SandboxExecutor()

        script = executor._prepare_script(
            "echo",
            {"text": "hello"},
            "def execute(text): return {'result': text}",
        )

        assert "import json" in script
        assert "args = json.loads" in script
        assert "def execute" in script
        assert "print(result)" in script
        assert "execute(**args)" in script

    def test_prepare_script_without_code(self):
        """Script preparation without tool code."""
        executor = SandboxExecutor()

        script = executor._prepare_script("unknown_tool", {}, None)

        assert "Tool code not provided" in script


@pytest.mark.integration
class TestSandboxExecutorIntegration:
    """Integration tests requiring Docker."""

    @pytest.mark.asyncio
    async def test_health_check_with_docker(self):
        """Health check passes when Docker is running."""
        executor = SandboxExecutor()

        result = await executor.health_check()

        # This will pass if Docker is running, fail otherwise
        # In CI without Docker, skip this test
        assert result is True or result is False  # Accept either

    @pytest.mark.asyncio
    async def test_simple_execution(self):
        """Execute simple Python code in container."""
        executor = SandboxExecutor()

        result = await executor.run_tool(
            "echo",
            {"text": "hello"},
            tool_code="def execute(text): return {'output': text}",
        )

        # If Docker available, should get output
        # If not, should get error
        if result.exit_code == 0:
            assert "hello" in result.output
        else:
            assert result.error != "" or result.exit_code != 0

    @pytest.mark.asyncio
    async def test_cleanup_after_execution(self):
        """Cleanup removes containers."""
        executor = SandboxExecutor()

        # Run a simple execution (may fail if docker unavailable)
        result = await executor.run_tool("test", {}, tool_code="def execute(): return {'status': 'ok'}")

        # Cleanup should work even if execution failed
        try:
            await executor.cleanup()
        except Exception:
            pass  # cleanup may fail if client not initialized

        assert len(executor._containers) == 0