"""Workflow models for multi-tool orchestration."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorkflowStep:
    """A single step in a workflow.

    Attributes:
        tool: Name of the tool to execute
        input: Input arguments for the tool
        condition: Optional condition expression to check before execution
        retry: Number of retry attempts on failure
        name: Optional step name for referencing in later steps
    """

    tool: str
    input: dict = field(default_factory=dict)
    condition: str | None = None
    retry: int = 0
    name: str | None = None


@dataclass
class Workflow:
    """A workflow consisting of multiple tool execution steps.

    Attributes:
        name: Workflow name
        steps: List of workflow steps to execute sequentially
        description: Optional workflow description
    """

    name: str
    steps: list[WorkflowStep] = field(default_factory=list)
    description: str | None = None


@dataclass
class StepResult:
    """Result of a single workflow step execution.

    Attributes:
        step_name: Name of the step (or tool name if no name given)
        output: Output from the tool execution
        success: Whether execution succeeded
        skipped: Whether step was skipped due to condition
        error: Error message if execution failed
    """

    step_name: str
    output: str
    success: bool = True
    skipped: bool = False
    error: str = ""


@dataclass
class WorkflowResult:
    """Result of a complete workflow execution.

    Attributes:
        workflow_name: Name of the executed workflow
        steps: List of step results
        success: Whether all steps succeeded
        final_output: Output from the last step (or aggregated output)
    """

    workflow_name: str
    steps: list[StepResult] = field(default_factory=list)
    success: bool = True
    final_output: str = ""


def parse_workflow_from_yaml(yaml_path: str | Path) -> Workflow:
    """Parse a workflow from a YAML file.

    Args:
        yaml_path: Path to the YAML workflow definition

    Returns:
        Workflow instance
    """
    import yaml

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    steps = []
    for step_data in data.get("steps", []):
        step = WorkflowStep(
            tool=step_data["tool"],
            input=step_data.get("input", {}),
            condition=step_data.get("condition"),
            retry=step_data.get("retry", 0),
            name=step_data.get("name"),
        )
        steps.append(step)

    return Workflow(
        name=data.get("name", "unnamed"),
        steps=steps,
        description=data.get("description"),
    )