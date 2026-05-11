# Plan: Skills Enhancement Phase 4

## Step 1: 沙箱执行基础

### 目标
- Docker 容器隔离执行工具
- 基本资源限制

### 实现

**文件**: `tools/sandbox/__init__.py` (新建)

```python
class SandboxExecutor:
    def __init__(self, docker_client, config: SandboxConfig)
    async def run_tool(self, tool_name: str, args: dict) -> str
    async def cleanup(self) -> None
```

**文件**: `tools/sandbox/config.py`

```python
@dataclass
class SandboxConfig:
    image: str = "python:3.13-slim"
    cpu_limit: float = 0.5  # 50% CPU
    memory_limit: str = "256m"
    timeout: int = 30  # seconds
    read_dirs: list[str] = []
    write_dirs: list[str] = []
```

**依赖**: `docker>=7.0.0`

### 验证
```bash
# 启动 Docker Desktop
# 运行测试
uv run pytest tests/test_sandbox.py -v
```

## Step 2: Workflow DSL 解析

### 目标
- YAML 工作流定义解析
- 顺序执行多工具

### 实现

**文件**: `workflows/__init__.py` (新建)

```python
class WorkflowEngine:
    def load(yaml_path: str) -> Workflow
    async def execute(workflow: Workflow, input: dict) -> WorkflowResult
```

**文件**: `workflows/models.py`

```python
@dataclass
class Workflow:
    name: str
    steps: list[WorkflowStep]

@dataclass
class WorkflowStep:
    tool: str
    input: dict
    condition: str | None = None
    retry: int = 0
```

**依赖**: `pyyaml>=6.0`

### 验证
```bash
# 定义测试 workflow
cat > test-workflow.yaml << EOF
name: test
steps:
  - tool: get_time
    input: {}
  - tool: echo
    input: {text: "当前时间: ${steps[0].result}"}
EOF

# 执行测试
uv run python -m workflows test-workflow.yaml
```

## Step 3: Gateway 集成 Sandbox

### 目标
- Gateway 可选启用沙箱模式
- Tool Loop 在沙箱中执行

### 实现

**文件**: `gateway.py` (修改)

```python
# 添加配置
SANDBOX_ENABLED = os.getenv("SANDBOX_ENABLED", "false") == "true"

# 修改 Tool Loop
if SANDBOX_ENABLED:
    result = await _sandbox_executor.run_tool(fn_name, fn_args)
else:
    result = await _tool_registry.dispatch(fn_name, fn_args)
```

## Step 4: Skills Registry 基础

### 目标
- 本地 Skill Pack 管理
- 简单的 skill install 命令

### 实现

**文件**: `skills/registry.py` (新建)

```python
class SkillPack:
    """打包 Skills + Tools 配置"""
    name: str
    version: str
    skills: list[Skill]
    tools: list[ToolMeta]

class LocalRegistry:
    """本地 Skill Registry"""
    def install(pack: SkillPack) -> None
    def list_installed() -> list[SkillPack]
    def uninstall(name: str) -> bool
```

**文件**: `skills/pack.py`

```python
def create_pack(name: str, skills_dir: Path) -> SkillPack
def load_pack(pack_file: str) -> SkillPack
```

### 验证
```bash
# 打包 skill
uv run python -m skills.pack cat-girl --output cat-girl.pack

# 安装 skill
uv run python -m skills.registry install cat-girl.pack

# 验证安装
ls ~/.agentcraft/skills/
```

## Step 5: 条件分支与错误处理

### 目标
- Workflow 条件表达式
- 重试机制

### 实现

**文件**: `workflows/engine.py` (扩展)

```python
def evaluate_condition(self, expr: str, context: dict) -> bool
async def execute_step_with_retry(self, step: WorkflowStep, context: dict) -> str
```

## Dependencies

新增依赖：
- `docker>=7.0.0`
- `pyyaml>=6.0`

## 验证清单

```bash
# 沙箱测试
uv run pytest tests/test_sandbox.py -v

# Workflow 测试
uv run pytest tests/test_workflow.py -v

# Registry 测试
uv run pytest tests/test_registry.py -v

# 集成测试
uv run pytest tests/integration/test_phase4.py -v -m integration
```