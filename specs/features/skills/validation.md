# Validation: Skills System

## 手动测试

```bash
# 1. 创建 Skill 目录和 SKILL.md
mkdir -p ~/.agentcraft/skills/hello
cat > ~/.agentcraft/skills/hello/SKILL.md << 'EOF'
---
name: hello
description: 一个简单的打招呼技能
tools: []
---
# Hello Skill

当用户说"你好"或"打招呼"时，用友好的方式回应。
可以加上当前时间和一句名言。
EOF

# 2. 验证 Skill 被加载（查看启动日志）
curl http://127.0.0.1:8000/health

# 3. 测试 Skill 注入效果
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: {session_id}" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"打个招呼"}]}'

# 4. 创建带工具的 Skill
mkdir -p ~/.agentcraft/skills/weather
cat > ~/.agentcraft/skills/weather/SKILL.md << 'EOF'
---
name: weather
description: 天气查询
tools: [current_time]
---
# Weather Skill

用户询问天气时，先调用 current_time 获取时间，然后告知用户当前时间。
EOF

# 5. 测试带工具的 Skill
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Session-Id: {session_id}" \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"天气怎么样"}]}'
```

## 验证清单

- [ ] SKILL.md 被正确解析（name, description, tools, instructions）
- [ ] System prompt 中包含启用的 Skill 指令
- [ ] 禁用 Skill 后不再出现在 prompt 中
- [ ] 内置 Skills 和用户 Skills 同时生效
- [ ] 新增 Skill 目录后重启 Gateway 自动加载
- [ ] Skill 引用的工具可正常调用
- [ ] 没有 Skills 时行为不变（回归测试）