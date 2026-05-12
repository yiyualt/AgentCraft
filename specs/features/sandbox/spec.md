# Feature: Sandbox Executor (Docker Isolation)

## 背景

工具执行直接在 Gateway 进程中运行存在安全风险：
- 文件系统无限制访问
- 网络访问不受控
- 可能执行危险命令
- 资源消耗无上限

Sandbox Executor 通过 Docker 容器隔离执行，提供安全边界。

## 目标

- [x] Docker 容器隔离执行
- [x] 资源限制（CPU、内存）
- [x] 文件系统挂载控制（只读/可写目录）
- [x] 网络访问控制（可禁用）
- [x] 执行超时
- [x] 自动清理容器
- [x] 可选 pip 包安装

## 配置

```python
class SandboxConfig:
    image: str = "python:3.13-slim"  # Docker 镜像
    cpu_limit: float = 0.5           # CPU 限制 (50%)
    memory_limit: str = "256m"       # 内存限制
    timeout: int = 30                # 执行超时（秒）
    read_dirs: list[str]             # 只读挂载目录
    write_dirs: list[str]            # 可写挂载目录
    network_disabled: bool = True    # 禁用网络
    pip_packages: list[str]          # 预安装 pip 包
    mount_host_bin: bool = False     # 挂载宿主机 /usr/bin
```

## 环境变量

```
SANDBOX_ENABLED=false        # 启用沙箱
SANDBOX_NETWORK=false        # 允许网络
SANDBOX_HOST_BIN=false       # 挂载宿主机命令
SANDBOX_PIP_PACKAGES=httpx,duckduckgo-search  # pip 包
SANDBOX_READ_DIRS=/Users/yiyu/Pyleaf  # 只读目录
SANDBOX_WRITE_DIRS=/Users/yiyu/output  # 可写目录
```

## 架构

```
Gateway → 检测 SANDBOX_ENABLED
        → 获取工具源代码
        → SandboxExecutor.run_tool()
            → 创建 Docker 容器
            → 注入 Python 脚本（工具代码 + 调用）
            → 执行并等待结果
            → 清理容器
        → 返回结果
```

## 实现

### SandboxExecutor (`tools/sandbox/__init__.py`)

1. 懒加载 Docker 客户端
2. 从工具 Registry 获取源代码
3. 剔除 `@tool` 装饰器
4. 构建执行脚本（导入 + 工具代码 + 调用）
5. 创建容器，配置资源限制和挂载
6. 等待执行，捕获 stdout/stderr
7. 清理容器

### MCP 工具处理

MCP 工具无法提取源代码，直接调用（不进入沙箱）。

## 安全特性

| 风险 | 缓解措施 |
|------|---------|
| 文件泄露 | 只读/可写目录分离 |
| 网络攻击 | network_disabled=True |
| 资源耗尽 | cpu_limit, memory_limit |
| 无限执行 | timeout 控制 |
| 容器堆积 | 自动清理 |

## 验证

```bash
# 启用沙箱运行 Gateway
export SANDBOX_ENABLED=true
export SANDBOX_READ_DIRS=/path/to/project
uv run gateway.py

# 测试沙箱执行
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"读取 README.md 的内容"}]}'
```

## 依赖

- Docker SDK: `uv add docker`
- Docker Daemon 运行中