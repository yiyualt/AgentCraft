# Feature: Skills Enhancement & Sandbox

## 背景

Phase 2 已实现基础 Skills 系统：
- JSON 配置文件定义 Skill
- SkillLoader 加载并注入 instructions
- Skill 可指定可用 tools 列表

**当前限制**：
- Skills 只能本地定义，无法共享/发现
- 工具执行无隔离，安全风险
- 单工具调用，无编排能力

## 目标

### Phase 4.1: Skills 市场

- [ ] Skill Registry API（发现、搜索、安装）
- [ ] Skill Pack（打包多个 Skills + Tools）
- [ ] Skill Versioning（版本管理）
- [ ] Skill Metadata（作者、依赖、兼容性）

### Phase 4.2: 沙箱执行

- [ ] Docker 容器隔离执行工具
- [ ] 资源限制（CPU、内存、时间）
- [ ] 文件系统隔离（只允许特定目录）
- [ ] 安全策略配置

### Phase 4.3: 工具编排

- [ ] Workflow 定义（多工具顺序/并行调用）
- [ ] 条件分支（根据工具结果决定下一步）
- [ ] 错误处理与重试
- [ ] 结果聚合与转换

## 设计

### Skill Registry

```python
class SkillRegistry:
    """Skills 市场服务"""

    def search(query: str) -> list[SkillMeta]
    def install(name: str, version: str) -> Skill
    def publish(skill: Skill) -> None
    def list_installed() -> list[Skill]
```

### Sandbox Executor

```python
class SandboxExecutor:
    """Docker 沙箱执行器"""

    def run_tool(tool: Tool, args: dict) -> str
    def create_container(config: SandboxConfig) -> Container
    def set_limits(cpu: float, memory: str, timeout: int)
```

### Workflow Engine

```python
class Workflow:
    """工具编排工作流"""

    steps: list[WorkflowStep]
    def execute(input: dict) -> WorkflowResult

class WorkflowStep:
    tool: str
    input_mapping: dict  # 从上一步结果映射
    condition: str | None  # 条件表达式
    retry: int  # 重试次数
```

## 优先级

1. 沙箱执行 — 安全性是基础
2. 工具编排 — 提升自动化能力
3. Skills 市场 — 社区生态

## 技术方案

### Docker 沙箱

- 使用 Docker SDK for Python
- 每个工具调用创建临时容器
- 容器镜像：python:3.13-slim + 工具依赖
- 挂载目录：只读源码 + 可写输出目录

### Workflow DSL

使用 YAML 定义工作流：

```yaml
name: code-review-workflow
steps:
  - tool: read_file
    input: {path: "${input.file}"}
  - tool: grep
    input: {pattern: "TODO|FIXME", path: "${input.file}"}
  - tool: write_file
    input: {path: "${input.file}.review.md", content: "${steps[0].result}"}
    condition: "${steps[1].result != ''}"
```

## 验证

- [x] SandboxExecutor 模块创建 ✅
- [x] WorkflowEngine 支持顺序执行 ✅
- [x] WorkflowEngine 支持条件分支 ✅
- [x] WorkflowEngine 支持重试机制 ✅
- [x] LocalRegistry 支持安装/卸载 Skill Pack ✅
- [x] Gateway 集成 SandboxExecutor (SANDBOX_ENABLED) ✅
- [x] 工具源代码获取 (Tool.get_source_code) ✅
- [x] 沙箱脚本生成（自动导入标准库） ✅
- [ ] Docker 容器能成功执行工具 (需要 Docker 环境)
- [ ] 容器资源限制生效 (需要 Docker 环境)

## 沙箱执行流程

```
用户 → Gateway → LLM → tool_call
                    ↓
          SANDBOX_ENABLED=true?
                    ↓
          registry.get_source_code(fn_name)
                    ↓
          SandboxExecutor.run_tool(fn_name, args, tool_code)
                    ↓
          _prepare_script() → 生成 Python 脚本
                    ↓
          Docker 容器执行脚本
                    ↓
          返回结果 → Gateway → LLM → 用户
```

**注意事项**：
- MCP 工具无法沙箱化（外部进程），直接执行
- 使用 `httpx` 等外部库的工具无法在沙箱中运行（容器只有标准库）
- 网络被禁用 (`network_disabled=True`)，无法访问外部 API