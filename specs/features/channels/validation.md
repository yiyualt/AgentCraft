# Validation: Channel Adapters

## 手动测试

```bash
# Telegram Bot (需要先注册 Bot Token)
# 1. 设置环境变量
export TELEGRAM_BOT_TOKEN="your_token"
# 2. 启动 Gateway，观察日志中的 Bot 启动信息
# 3. 在 Telegram 中向 Bot 发送消息
# 4. 验证 Bot 回复

# Web Chat
# 1. 浏览器打开
open http://127.0.0.1:8000/chat
# 2. 输入消息发送
# 3. 验证回复显示在页面上
```

## 验证清单

- [ ] Channel 基类接口清晰，可扩展
- [ ] Telegram Bot 能接收消息并回复
- [ ] 不同 Telegram 用户的消息隔离（独立 Session）
- [ ] Telegram Bot 支持 /new 和 /history 命令
- [ ] Web Chat 页面可正常加载和发送消息
- [ ] Web Chat 支持流式响应（SSE streaming）
- [ ] Channel 异常不影响 Gateway 主流程