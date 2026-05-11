"""Workflow engine for executing multi-tool sequences."""

import logging
import re
from typing import Any

from .models import (
    Workflow,
    WorkflowResult,
    WorkflowStep,
    StepResult,
    parse_workflow_from_yaml,
)

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Execute workflows defined as sequences of tool calls.

    Supports:
    - Sequential execution of steps
    - Input mapping from previous steps
    - Conditional execution
    - Retry on failure
    """

    def __init__(self, tool_registry: Any = None):
        """Initialize workflow engine.

        Args:
            tool_registry: Registry of available tools (callable dispatcher)
        """
        self.tool_registry = tool_registry
        self._context: dict[str, Any] = {}

    def load(self, yaml_path: str) -> Workflow:
        """Load a workflow from YAML file.

        Args:
            yaml_path: Path to the workflow YAML

        Returns:
            Workflow instance ready for execution
        """
        return parse_workflow_from_yaml(yaml_path)

    async def execute(
        self,
        workflow: Workflow,
        input: dict[str, Any] = None,
    ) -> WorkflowResult:
        """Execute a workflow with given input context.

        Args:
            workflow: Workflow to execute
            input: Initial input context

        Returns:
            WorkflowResult with all step results
        """
        self._context = {"input": input or {}, "steps": {}}

        results: list[StepResult] = []

        for i, step in enumerate(workflow.steps):
            step_result = await self._execute_step(step, i)
            results.append(step_result)

            # Store step result in context for later steps
            step_key = step.name or f"step_{i}"
            self._context["steps"][step_key] = {
                "result": step_result.output,
                "success": step_result.success,
            }

            # Stop on failure unless step has retry configured
            if not step_result.success and step.retry == 0:
                break

        # Determine final output
        final_output = ""
        if results:
            last_successful = None
            for r in results:
                if r.success and not r.skipped:
                    last_successful = r
            if last_successful:
                final_output = last_successful.output

        return WorkflowResult(
            workflow_name=workflow.name,
            steps=results,
            success=all(r.success for r in results),
            final_output=final_output,
        )

    async def _execute_step(
        self,
        step: WorkflowStep,
        index: int,
    ) -> StepResult:
        """Execute a single workflow step.

        Args:
            step: Step to execute
            index: Step index for naming

        Returns:
            StepResult with execution outcome
        """
        step_name = step.name or f"step_{index}"

        # Check condition if present
        if step.condition:
            if not self._evaluate_condition(step.condition):
                return StepResult(
                    step_name=step_name,
                    output="",
                    success=True,
                    skipped=True,
                )

        # Map input from context
        mapped_input = self._map_input(step.input)

        # Execute tool with retry
        attempts = step.retry + 1
        last_error = ""

        for attempt in range(attempts):
            try:
                output = await self._dispatch_tool(step.tool, mapped_input)
                return StepResult(
                    step_name=step_name,
                    output=output,
                    success=True,
                )
            except Exception as e:
                last_error = str(e)
                logger.warning(
                    f"Step {step_name} attempt {attempt + 1} failed: {e}"
                )
                if attempt < attempts - 1:
                    logger.info(f"Retrying step {step_name}...")

        return StepResult(
            step_name=step_name,
            output="",
            success=False,
            error=last_error,
        )

    async def _dispatch_tool(
        self,
        tool_name: str,
        args: dict,
    ) -> str:
        """Dispatch tool execution to registry.

        Args:
            tool_name: Name of the tool
            args: Arguments for the tool

        Returns:
            Tool output as string
        """
        if self.tool_registry is None:
            # Simulated execution for testing
            return f"Tool {tool_name} executed with args: {args}"

        # Call the tool registry dispatcher
        if hasattr(self.tool_registry, "dispatch"):
            result = await self.tool_registry.dispatch(tool_name, args)
            return str(result)
        elif callable(self.tool_registry):
            result = await self.tool_registry(tool_name, args)
            return str(result)
        else:
            raise ValueError(f"No dispatcher available for tool {tool_name}")

    def _map_input(self, input_template: dict) -> dict:
        """Map input template to actual values from context.

        Supports expressions like:
        - ${input.file} - from workflow input
        - ${steps[0].result} - from step result
        - ${steps.step_name.result} - from named step result

        Args:
            input_template: Template with potential expressions

        Returns:
            Mapped input dictionary
        """
        result = {}

        for key, value in input_template.items():
            if isinstance(value, str) and "${" in value:
                result[key] = self._interpolate(value)
            elif isinstance(value, dict):
                result[key] = self._map_input(value)
            else:
                result[key] = value

        return result

    def _interpolate(self, template: str) -> str:
        """Interpolate expressions in a string.

        Args:
            template: String with ${...} expressions

        Returns:
            Interpolated string
        """
        pattern = r"\$\{([^}]+)\}"

        def replace(match):
            expr = match.group(1)
            value = self._resolve_expression(expr)
            return str(value) if value is not None else ""

        return re.sub(pattern, replace, template)

    def _resolve_expression(self, expr: str) -> Any:
        """Resolve an expression to a value from context.

        Args:
            expr: Expression like "input.file" or "steps[0].result"

        Returns:
            Resolved value or None if not found
        """
        parts = expr.split(".")
        current = self._context

        for part in parts:
            # Handle array index notation: steps[0]
            if "[" in part and part.endswith("]"):
                name = part.split("[")[0]
                index = int(part.split("[")[1].rstrip("]"))
                if name in current and isinstance(current[name], dict):
                    keys = list(current[name].keys())
                    if 0 <= index < len(keys):
                        current = current[name][keys[index]]
                    else:
                        return None
                else:
                    return None
            elif part in current:
                current = current[part]
            else:
                return None

        return current

    def _evaluate_condition(self, condition: str) -> bool:
        """Evaluate a condition expression.

        Args:
            condition: Condition like "${steps[1].result != ''}"

        Returns:
            Boolean result of condition
        """
        # Simple condition evaluation
        # Supports: ${expr} == value, ${expr} != value, ${expr} exists

        interpolated = self._interpolate(condition)

        # Check for comparison operators
        if "==" in condition:
            parts = condition.split("==")
            left = self._resolve_expression(parts[0].strip().replace("${", "").replace("}", ""))
            right = parts[1].strip().strip("'\"")
            return str(left) == right
        elif "!=" in condition:
            parts = condition.split("!=")
            left = self._resolve_expression(parts[0].strip().replace("${", "").replace("}", ""))
            right = parts[1].strip().strip("'\"")
            return str(left) != right
        else:
            # Just check if value exists and is truthy
            expr = condition.replace("${", "").replace("}", "").strip()
            value = self._resolve_expression(expr)
            return bool(value)


__all__ = [
    "WorkflowEngine",
    "Workflow",
    "WorkflowStep",
    "WorkflowResult",
    "StepResult",
    "parse_workflow_from_yaml",
]