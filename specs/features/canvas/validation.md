# Validation: Live Canvas

## 手动测试

```bash
# 1. 启动 Gateway
uv run uvicorn gateway:app --reload

# 2. 浏览器打开 Canvas
open http://127.0.0.1:8000/canvas

# 3. 通过 API 让 Agent 更新 Canvas
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -d '{"model":"qwen3:8b","messages":[{"role":"user","content":"在工作台上展示一个表格"}]}'

# 4. 验证 Canvas 页面实时显示更新
```

## 验证清单

- [ ] Canvas 页面可正常加载
- [ ] Agent 可通过 tool call 更新 Canvas 内容
- [ ] Canvas 支持 Markdown 渲染
- [ ] Canvas 支持代码高亮
- [ ] Canvas 支持表格显示
- [ ] SSE 推送延迟 < 1s
- [ ] 多客户端同步（打开两个浏览器标签页查看）