"""Tests for workflow engine."""

import pytest
import tempfile
from pathlib import Path

from workflows import (
    WorkflowEngine,
    Workflow,
    WorkflowStep,
    WorkflowResult,
    StepResult,
    parse_workflow_from_yaml,
)


class TestWorkflowStep:
    """Tests for WorkflowStep dataclass."""

    def test_default_step(self):
        """Default workflow step."""
        step = WorkflowStep(tool="echo")

        assert step.tool == "echo"
        assert step.input == {}
        assert step.condition is None
        assert step.retry == 0
        assert step.name is None

    def test_full_step(self):
        """Fully configured workflow step."""
        step = WorkflowStep(
            tool="read_file",
            input={"path": "/src"},
            condition="${steps[0].result != ''}",
            retry=3,
            name="read_source",
        )

        assert step.tool == "read_file"
        assert step.input == {"path": "/src"}
        assert step.condition == "${steps[0].result != ''}"
        assert step.retry == 3
        assert step.name == "read_source"


class TestWorkflow:
    """Tests for Workflow dataclass."""

    def test_empty_workflow(self):
        """Workflow with no steps."""
        workflow = Workflow(name="empty")

        assert workflow.name == "empty"
        assert workflow.steps == []
        assert workflow.description is None

    def test_workflow_with_steps(self):
        """Workflow with multiple steps."""
        workflow = Workflow(
            name="test_flow",
            steps=[
                WorkflowStep(tool="step1"),
                WorkflowStep(tool="step2"),
            ],
            description="Test workflow",
        )

        assert workflow.name == "test_flow"
        assert len(workflow.steps) == 2
        assert workflow.description == "Test workflow"


class TestStepResult:
    """Tests for StepResult dataclass."""

    def test_success_result(self):
        """Successful step result."""
        result = StepResult(step_name="test", output="done")

        assert result.step_name == "test"
        assert result.output == "done"
        assert result.success
        assert not result.skipped

    def test_error_result(self):
        """Failed step result."""
        result = StepResult(
            step_name="test",
            output="",
            success=False,
            error="Tool not found",
        )

        assert not result.success
        assert result.error == "Tool not found"

    def test_skipped_result(self):
        """Skipped step result."""
        result = StepResult(
            step_name="test",
            output="",
            success=True,
            skipped=True,
        )

        assert result.success
        assert result.skipped


class TestWorkflowResult:
    """Tests for WorkflowResult dataclass."""

    def test_successful_workflow(self):
        """All steps succeeded."""
        result = WorkflowResult(
            workflow_name="test",
            steps=[
                StepResult(step_name="s1", output="a"),
                StepResult(step_name="s2", output="b"),
            ],
            success=True,
            final_output="b",
        )

        assert result.workflow_name == "test"
        assert result.success
        assert result.final_output == "b"

    def test_failed_workflow(self):
        """Workflow with failed step."""
        result = WorkflowResult(
            workflow_name="test",
            steps=[
                StepResult(step_name="s1", output="a"),
                StepResult(step_name="s2", output="", success=False),
            ],
            success=False,
        )

        assert not result.success


class TestParseWorkflowFromYaml:
    """Tests for YAML parsing."""

    def test_parse_simple_workflow(self):
        """Parse basic workflow YAML."""
        yaml_content = """
name: simple
steps:
  - tool: echo
    input: {text: "hello"}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            workflow = parse_workflow_from_yaml(f.name)

        assert workflow.name == "simple"
        assert len(workflow.steps) == 1
        assert workflow.steps[0].tool == "echo"
        assert workflow.steps[0].input == {"text": "hello"}

    def test_parse_complex_workflow(self):
        """Parse workflow with conditions and retries."""
        yaml_content = """
name: complex
description: Multi-step workflow
steps:
  - tool: read_file
    name: read
    input: {path: "${input.file}"}
  - tool: grep
    input: {pattern: "TODO", path: "${input.file}"}
  - tool: write_file
    input: {path: "${input.file}.review.md"}
    condition: "${steps.read.result != ''}"
    retry: 2
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()
            workflow = parse_workflow_from_yaml(f.name)

        assert workflow.name == "complex"
        assert workflow.description == "Multi-step workflow"
        assert len(workflow.steps) == 3

        # Check step 0
        assert workflow.steps[0].name == "read"
        assert workflow.steps[0].tool == "read_file"

        # Check step 2
        assert workflow.steps[2].condition == "${steps.read.result != ''}"
        assert workflow.steps[2].retry == 2


class TestWorkflowEngine:
    """Tests for WorkflowEngine class."""

    def test_engine_initialization(self):
        """Engine initializes correctly."""
        engine = WorkflowEngine()

        assert engine.tool_registry is None
        assert engine._context == {}

    def test_engine_with_registry(self):
        """Engine accepts tool registry."""
        engine = WorkflowEngine(tool_registry={"test": lambda x: x})

        assert engine.tool_registry is not None

    @pytest.mark.asyncio
    async def test_execute_empty_workflow(self):
        """Execute workflow with no steps."""
        engine = WorkflowEngine()
        workflow = Workflow(name="empty")

        result = await engine.execute(workflow)

        assert result.workflow_name == "empty"
        assert result.steps == []
        assert result.success

    @pytest.mark.asyncio
    async def test_execute_simple_workflow(self):
        """Execute workflow with single step."""
        engine = WorkflowEngine()
        workflow = Workflow(
            name="simple",
            steps=[WorkflowStep(tool="echo", input={"text": "hello"})],
        )

        result = await engine.execute(workflow)

        assert result.success
        assert len(result.steps) == 1
        assert "echo" in result.steps[0].output

    @pytest.mark.asyncio
    async def test_execute_multi_step_workflow(self):
        """Execute workflow with multiple steps."""
        engine = WorkflowEngine()
        workflow = Workflow(
            name="multi",
            steps=[
                WorkflowStep(tool="step1"),
                WorkflowStep(tool="step2"),
                WorkflowStep(tool="step3"),
            ],
        )

        result = await engine.execute(workflow)

        assert result.success
        assert len(result.steps) == 3

    @pytest.mark.asyncio
    async def test_execute_with_input_context(self):
        """Execute workflow with initial input."""
        engine = WorkflowEngine()
        workflow = Workflow(
            name="with_input",
            steps=[WorkflowStep(tool="echo", input={"path": "${input.file}"})],
        )

        result = await engine.execute(workflow, input={"file": "/src/test.py"})

        assert result.success
        assert "/src/test.py" in result.steps[0].output

    @pytest.mark.asyncio
    async def test_execute_with_named_step_reference(self):
        """Execute workflow with step name references."""
        engine = WorkflowEngine()
        workflow = Workflow(
            name="named",
            steps=[
                WorkflowStep(tool="first", name="step_one"),
                WorkflowStep(
                    tool="second",
                    input={"data": "${steps.step_one.result}"},
                ),
            ],
        )

        result = await engine.execute(workflow)

        assert result.success
        assert len(result.steps) == 2
        # Second step should reference first step's output
        assert "first" in result.steps[1].output

    def test_interpolate_expression(self):
        """Interpolate expressions correctly."""
        engine = WorkflowEngine()
        engine._context = {
            "input": {"file": "/src/test.py"},
            "steps": {"step_0": {"result": "output_data"}},
        }

        # Test input interpolation
        result = engine._interpolate("${input.file}")
        assert result == "/src/test.py"

        # Test step interpolation
        result = engine._interpolate("${steps.step_0.result}")
        assert result == "output_data"

    def test_map_input(self):
        """Map input template to values."""
        engine = WorkflowEngine()
        engine._context = {
            "input": {"file": "/src/main.py", "mode": "read"},
        }

        template = {
            "path": "${input.file}",
            "mode": "${input.mode}",
            "static": "value",
        }

        result = engine._map_input(template)

        assert result["path"] == "/src/main.py"
        assert result["mode"] == "read"
        assert result["static"] == "value"


class TestWorkflowEngineConditions:
    """Tests for condition evaluation."""

    def test_evaluate_equals_condition(self):
        """Evaluate == condition."""
        engine = WorkflowEngine()
        engine._context = {"steps": {"s1": {"result": "success"}}}

        # Should match
        assert engine._evaluate_condition("${steps.s1.result} == 'success'")
        # Should not match
        assert not engine._evaluate_condition("${steps.s1.result} == 'other'")

    def test_evaluate_not_equals_condition(self):
        """Evaluate != condition."""
        engine = WorkflowEngine()
        engine._context = {"steps": {"s1": {"result": ""}}}

        # Empty string should not equal 'data'
        assert engine._evaluate_condition("${steps.s1.result} != 'data'")

    def test_evaluate_truthy_condition(self):
        """Evaluate truthy condition."""
        engine = WorkflowEngine()
        engine._context = {"steps": {"s1": {"result": "has_data"}}}

        # Non-empty string is truthy
        assert engine._evaluate_condition("${steps.s1.result}")

        # Empty string is falsy
        engine._context = {"steps": {"s1": {"result": ""}}}
        assert not engine._evaluate_condition("${steps.s1.result}")

    @pytest.mark.asyncio
    async def test_execute_with_condition_skip(self):
        """Execute workflow where condition causes skip."""
        engine = WorkflowEngine()
        workflow = Workflow(
            name="conditional",
            steps=[
                WorkflowStep(tool="check", name="check"),
                WorkflowStep(
                    tool="process",
                    condition="${steps.check.result} == 'skip'",
                ),
            ],
        )

        # Condition not met (result != 'skip'), step should be skipped
        result = await engine.execute(workflow)
        assert result.steps[1].skipped


class TestWorkflowEngineRetry:
    """Tests for retry mechanism."""

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Step retries on failure."""
        engine = WorkflowEngine()

        # Mock tool that always fails
        async def failing_dispatcher(tool, args):
            raise RuntimeError("Tool failed")

        engine.tool_registry = failing_dispatcher

        workflow = Workflow(
            name="retry_test",
            steps=[WorkflowStep(tool="failing", retry=2)],
        )

        result = await engine.execute(workflow)

        # Should fail after retries
        assert not result.success
        assert not result.steps[0].success
        assert "Tool failed" in result.steps[0].error


@pytest.mark.integration
class TestWorkflowEngineIntegration:
    """Integration tests with actual YAML files."""

    @pytest.mark.asyncio
    async def test_load_and_execute_yaml(self):
        """Load workflow from YAML and execute."""
        yaml_content = """
name: test_workflow
steps:
  - tool: get_time
    name: time_check
  - tool: echo
    input: {text: "Time checked"}
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            f.flush()

            engine = WorkflowEngine()
            workflow = engine.load(f.name)
            result = await engine.execute(workflow)

        assert result.success
        assert result.workflow_name == "test_workflow"