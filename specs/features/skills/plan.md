# Plan: Skills System

## Step 1: SKILL.md 解析

**涉及文件**: `skills/parser.py` (新建)

- 读取 SKILL.md，提取 frontmatter 和正文
- 解析字段：name, description, tools, dependencies, instructions
- 返回 `Skill` dataclass

## Step 2: Skills Registry

**涉及文件**: `skills/registry.py` (新建)

```
class Skill:
    name: str
    description: str
    tools: list[str]         # 引用的工具名列表
    instructions: str        # 注入到 prompt 的内容
    dependencies: list[str]  # pip 依赖
    enabled: bool
    path: Path               # 技能目录路径
    tool_module: Path | None # 可选的 tool.py 路径

class SkillsRegistry:
    def load(directories: list[Path]) → None
    def list_skills(enabled_only=True) → list[Skill]
    def get_skill(name) → Skill | None
    def enable(name) / disable(name) → None
    def build_system_prompt(base_prompt) → str
```

- 扫描 `~/.agentcraft/skills/` 和项目内置 `skills/` 目录
- 每个子目录如果有 `SKILL.md` 即视为一个 Skill

## Step 3: System Prompt 注入

**涉及文件**: `skills/registry.py` → `gateway.py`

- `build_system_prompt(base_prompt)` 拼接所有启用的 Skill instructions
- 生成格式：

```
{base_prompt}

## Available Skills
- skill_name: description

## Skill Instructions
### skill_name
{instructions}
```

- Gateway 在构造 LLM 请求时，如果有 session 的 system_prompt，注入 Skills
- 在 `_handle_non_streaming` 中 prepend system message

## Step 4: 工具联动

**涉及文件**: `skills/registry.py` → `tools/__init__.py`

- Skill 的 `tools` 字段声明需要的工具
- 如果 Skill 有 `tool.py`，动态加载并注册到 ToolRegistry
- Skills 只注入描述和指令，实际执行仍走 ToolRegistry

## Step 5: 内置 Skills

**涉及文件**: `skills/builtin/` (新建)

- 项目内置几个示例 Skill：
  - `skills/builtin/code-review/SKILL.md` — 代码审查
  - `skills/builtin/file-manager/SKILL.md` — 文件管理

## 依赖

- 无新依赖（用内置 yaml/json 或手写 frontmatter 解析）