"""Unit tests for tools/ module: Tool, ToolRegistry, and built-in tools."""

from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path

import pytest

from tools import Tool, ToolRegistry, get_default_registry, tool
from tools import builtin


# ============================================================
# Tool & ToolRegistry unit tests
# ============================================================


class TestTool:
    def test_basic_tool(self):
        def add(a: int, b: int) -> int:
            return a + b

        t = Tool(
            fn=add,
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {
                    "a": {"type": "integer"},
                    "b": {"type": "integer"},
                },
                "required": ["a", "b"],
            },
        )

        assert t.name == "add"
        assert t.description == "Add two numbers"
        assert t.run({"a": 1, "b": 2}) == "3"

    def test_to_openai_tool(self):
        def fn():
            pass

        t = Tool(fn=fn, name="test", description="desc", parameters={"type": "object"})
        expected = {
            "type": "function",
            "function": {
                "name": "test",
                "description": "desc",
                "parameters": {"type": "object"},
            },
        }
        assert t.to_openai_tool() == expected

    def test_run_non_string_result(self):
        t = Tool(fn=lambda: {"key": "value"}, name="dict_fn",
                 description="", parameters={"type": "object"})
        assert t.run({}) == '{"key": "value"}'

    def test_get_source_code(self):
        """Tool can return its source code."""
        def sample_fn(x: int) -> int:
            return x * 2

        t = Tool(fn=sample_fn, name="sample", description="", parameters={})
        code = t.get_source_code()

        assert code is not None
        assert "def sample_fn" in code
        assert "return x * 2" in code


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        t = Tool(fn=lambda: None, name="foo", description="", parameters={})
        reg.register(t)
        assert reg.get("foo") is t
        assert reg.get("bar") is None

    def test_list_tools(self):
        reg = ToolRegistry()
        t = Tool(fn=lambda: None, name="foo", description="desc", parameters={"type": "object"})
        reg.register(t)
        tools = reg.list_tools()
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "foo"

    def test_dispatch(self):
        reg = ToolRegistry()
        reg.register(Tool(fn=lambda x: int(x) * 2, name="double",
                          description="", parameters={
                              "type": "object",
                              "properties": {"x": {"type": "integer"}},
                              "required": ["x"],
                          }))
        assert reg.dispatch("double", {"x": 5}) == "10"
        assert "Unknown tool" in reg.dispatch("nonexistent", {})

    def test_get_source_code(self):
        """Registry can return tool source code."""
        def sample_fn(x: int) -> int:
            return x + 1

        reg = ToolRegistry()
        reg.register(Tool(fn=sample_fn, name="sample", description="", parameters={}))

        code = reg.get_source_code("sample")
        assert code is not None
        assert "def sample_fn" in code

        # Unknown tool returns None
        assert reg.get_source_code("nonexistent") is None

    def test_default_registry_singleton(self):
        assert get_default_registry() is get_default_registry()


class TestToolDecorator:
    def test_decorator_registers_tool(self):
        reg = ToolRegistry()

        # Use _default_registry — we'll check via get_default_registry
        @tool(description="A test function")
        def my_func(x: int) -> int:
            return x + 1

        default_reg = get_default_registry()
        assert default_reg.get("my_func") is not None

    def test_decorator_custom_name(self):
        @tool(name="custom_name", description="Custom name test")
        def some_fn():
            return 42

        reg = get_default_registry()
        assert reg.get("custom_name") is not None


# ============================================================
# Builtin tool unit tests
# ============================================================


class TestBuiltinTools:
    def test_current_time(self):
        result = builtin.current_time()
        # Should match ISO-like format YYYY-MM-DD HH:MM:SS
        parts = result.split(" ")
        assert len(parts) == 2
        date_parts = parts[0].split("-")
        assert len(date_parts) == 3
        assert len(date_parts[0]) == 4  # year

    def test_calculator_basic(self):
        assert builtin.calculator("2 + 2") == "4"
        assert builtin.calculator("10 * 20") == "200"

    def test_calculator_math_functions(self):
        result = builtin.calculator("sqrt(144)")
        assert result == "12.0"
        result2 = builtin.calculator("sin(0)")
        assert result2 == "0.0"

    def test_calculator_error(self):
        result = builtin.calculator("1/0")
        assert "Error" in result

    def test_read_file(self):
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("line1\nline2\nline3")
            tmp = f.name
        try:
            result = builtin.read_file(tmp)
            assert "line1" in result
            assert "line2" in result
        finally:
            os.unlink(tmp)

    def test_read_file_not_found(self):
        result = builtin.read_file("/tmp/nonexistent_file_xyz.txt")
        assert "Error" in result

    def test_write_file(self):
        path = "/tmp/agentcraft_test_write.txt"
        try:
            result = builtin.write_file(path, "hello world")
            assert "Successfully wrote" in result
            assert Path(path).read_text() == "hello world"
        finally:
            os.unlink(path)

    def test_write_file_creates_dirs(self):
        path = "/tmp/agentcraft_test_dir/nested/file.txt"
        try:
            result = builtin.write_file(path, "nested")
            assert "Successfully wrote" in result
            assert Path(path).read_text() == "nested"
        finally:
            os.unlink(path)
            os.removedirs("/tmp/agentcraft_test_dir/nested")

    def test_edit_file(self):
        path = "/tmp/agentcraft_test_edit.txt"
        Path(path).write_text("hello world foo")
        try:
            result = builtin.edit_file(path, "world", "there")
            assert "Successfully edited" in result
            assert Path(path).read_text() == "hello there foo"
        finally:
            os.unlink(path)

    def test_edit_file_not_found(self):
        path = "/tmp/agentcraft_test_edit.txt"
        Path(path).write_text("hello world")
        try:
            result = builtin.edit_file(path, "nonexistent", "x")
            assert "Could not find" in result
        finally:
            os.unlink(path)

    def test_glob(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "a.py").touch()
            Path(tmpdir, "b.py").touch()
            Path(tmpdir, "sub").mkdir()
            Path(tmpdir, "sub", "c.py").touch()

            result = builtin.glob_files("**/*.py", root=tmpdir)
            assert "a.py" in result
            assert "b.py" in result
            assert "sub/c.py" in result
            assert "3 file(s)" in result

    def test_glob_no_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = builtin.glob_files("*.xyz", root=tmpdir)
            assert "No files matching" in result

    @pytest.mark.skipif(os.name == "nt", reason="Grep requires Unix-like environment")
    def test_grep(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "test.txt").write_text("hello world\nfoo bar\nhello again")
            result = builtin.grep_files("hello", path=tmpdir)
            assert "test.txt" in result
            assert "hello" in result

    def test_bash_echo(self):
        result = builtin.bash("echo hello test")
        assert "hello test" in result

    def test_bash_exit_code(self):
        result = builtin.bash("false")
        assert "Exit code: 1" in result

    def test_bash_not_found(self):
        result = builtin.bash("nonexistent_command_xyz_123", workdir="/tmp")
        assert result is not None  # just shouldn't crash

    @pytest.mark.integration
    def test_web_fetch_invalid_url(self):
        """Integration test - requires network."""
        result = builtin.web_fetch("http://192.0.2.1/test")
        assert "Error" in result or "[HTTP" in result

    @pytest.mark.integration
    def test_web_fetch_httpbin(self):
        """Integration test - requires network."""
        result = builtin.web_fetch("https://httpbin.org/get")
        assert "url" in result or "Error" in result

    @pytest.mark.integration
    def test_web_search(self):
        """Integration test - DuckDuckGo search requires network."""
        result = builtin.web_search("test query")
        assert "Error" not in result or "No results" in result
        assert result is not None
        assert len(result) > 0

    @pytest.mark.integration
    def test_web_search_real_query(self):
        """Integration test - actual search requires network."""
        result = builtin.web_search("Python programming language")
        assert "No results" not in result or "Error" not in result

    @pytest.mark.asyncio
    async def test_agent_tool_not_initialized(self):
        """Test Agent tool when executor is not initialized."""
        # Directly call async function - executor not initialized in test context
        result = await builtin.agent_delegate("Write a poem")
        assert "[Error]" in result
        assert "not initialized" in result

    @pytest.mark.asyncio
    async def test_agent_tool_via_registry(self):
        """Test Agent tool dispatch through registry."""
        from tools import UnifiedToolRegistry
        import asyncio

        registry = UnifiedToolRegistry(get_default_registry())
        # When executor not initialized, should return error
        result = await registry.dispatch("Agent", {"prompt": "test task"})
        assert "Error" in result or "not initialized" in result


class TestAgentFork:
    """Test fork_from_current parameter in agent_delegate."""

    @pytest.fixture
    def mock_executor(self):
        """Create mock executor with async run but sync get_fork_manager."""
        from unittest.mock import MagicMock, AsyncMock
        mock = MagicMock()
        mock.run = AsyncMock(return_value="Fork agent result")
        return mock

    @pytest.fixture
    def mock_fork_manager(self):
        """Create mock ForkManager (no canvas manager to skip async canvas pushes)."""
        from unittest.mock import MagicMock
        from sessions.fork import ForkContext, FORK_PLACEHOLDER
        fm = MagicMock()
        ctx = ForkContext(
            parent_session_id="session-1",
            inherited_messages=[
                {"role": "system", "content": "fork boilerplate"},
                {"role": "user", "content": FORK_PLACEHOLDER},
            ],
            placeholder_index=1,
            is_fork_child=True,
        )
        fm.create_fork_context.return_value = ctx
        fm.get_canvas_manager.return_value = None
        return fm

    @pytest.mark.asyncio
    async def test_fork_from_current_no_session(self):
        """fork_from_current without current session returns error."""
        from unittest.mock import patch, MagicMock

        mock_exec = MagicMock()

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_exec), \
             patch("canvas.get_current_session_id", return_value=None):
            result = await builtin.agent_delegate("task", fork_from_current=True)
            assert "[FORK Error]" in result
            assert "No current session" in result

    @pytest.mark.asyncio
    async def test_fork_from_current_no_fork_manager(self):
        """fork_from_current without fork manager returns error."""
        from unittest.mock import patch, MagicMock

        mock_exec = MagicMock()
        mock_exec.get_fork_manager.return_value = None

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_exec), \
             patch("canvas.get_current_session_id", return_value="session-1"):
            result = await builtin.agent_delegate("task", fork_from_current=True)
            assert "[FORK Error]" in result
            assert "Fork manager not initialized" in result

    @pytest.mark.asyncio
    async def test_fork_from_current_success(self, mock_executor, mock_fork_manager):
        """Successful fork creation and execution."""
        from unittest.mock import patch

        mock_executor.get_fork_manager.return_value = mock_fork_manager

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_executor), \
             patch("canvas.get_current_session_id", return_value="session-1"):
            result = await builtin.agent_delegate(
                "summarize the history",
                description="summary",
                fork_from_current=True,
            )
            assert "Fork agent result" in result

    @pytest.mark.asyncio
    async def test_fork_from_current_passes_fork_context(self, mock_executor, mock_fork_manager):
        """fork_from_current=True passes fork_context and is_fork_child to run()."""
        from unittest.mock import patch

        mock_executor.get_fork_manager.return_value = mock_fork_manager

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_executor), \
             patch("canvas.get_current_session_id", return_value="session-1"):
            await builtin.agent_delegate("do something", fork_from_current=True)

        # Verify run() was called with fork_context and is_fork_child
        call_kwargs = mock_executor.run.call_args
        assert call_kwargs[1]["fork_context"] is not None
        assert call_kwargs[1]["is_fork_child"] is True
        assert call_kwargs[1]["fork_context"].parent_session_id == "session-1"

    @pytest.mark.asyncio
    async def test_fork_from_current_failed_context(self, mock_executor, mock_fork_manager):
        """When create_fork_context returns None, error is returned."""
        from unittest.mock import patch

        mock_fork_manager.create_fork_context.return_value = None
        mock_executor.get_fork_manager.return_value = mock_fork_manager

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_executor), \
             patch("canvas.get_current_session_id", return_value="session-1"):
            result = await builtin.agent_delegate("task", fork_from_current=True)
            assert "[FORK Error]" in result
            assert "Could not create fork context" in result

    @pytest.mark.asyncio
    async def test_fork_from_current_false_skips_fork(self, mock_executor):
        """fork_from_current=False (default) does not create fork context."""
        from unittest.mock import patch

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_executor), \
             patch("canvas.get_current_session_id") as mock_get_sid:
            await builtin.agent_delegate("task", subagent_type="explore", fork_from_current=False)

        # Should NOT call get_current_session_id
        mock_get_sid.assert_not_called()
        # run() called without fork_context
        call_kwargs = mock_executor.run.call_args
        assert call_kwargs[1].get("fork_context") is None
        assert call_kwargs[1].get("is_fork_child") is False

    @pytest.mark.asyncio
    async def test_fork_from_current_with_description(self, mock_executor, mock_fork_manager):
        """Task includes description as prefix."""
        from unittest.mock import patch

        mock_executor.get_fork_manager.return_value = mock_fork_manager

        with patch("tools.agent_executor.get_agent_executor", return_value=mock_executor), \
             patch("canvas.get_current_session_id", return_value="session-1"):
            await builtin.agent_delegate(
                "summarize",
                description="important summary",
                fork_from_current=True,
            )

        call_kwargs = mock_executor.run.call_args
        assert call_kwargs[1]["task"] == "[important summary] summarize"
