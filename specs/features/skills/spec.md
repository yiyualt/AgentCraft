# Feature: Skills System

## 背景

OpenClaw 的 Skills 是注入到 Agent prompt 中的能力描述文件。Agent 根据 Skill 描述决定何时调用对应的工具。这是一种轻量、灵活的能力扩展方式。

## 目标

- [x] Skills Registry：注册/发现/加载 Skills
- [x] Skill = 一个目录，包含 `SKILL.md`（能力描述）和可选的执行脚本
- [x] 自动注入到 System Prompt
- [x] Skills 的启用/禁用

## 设计

```
~/.agentcraft/skills/
├── weather/
│   ├── SKILL.md      # "你可以查询天气，使用 get_weather(city) 工具"
│   └── tool.py       # 实际的工具实现
├── calendar/
│   ├── SKILL.md
│   └── tool.py
└── filesystem/
    ├── SKILL.md
    └── tool.py
```

## SKILL.md 格式

```markdown
# Skill: Weather

## Description
查询任意城市的实时天气。

## Tools
- `get_weather(city: str) -> dict`: 返回 {temperature, humidity, description}

## Dependencies
- httpx (调用天气 API)
```
