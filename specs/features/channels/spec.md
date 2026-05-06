# Feature: Channel Adapters

## 背景

目前只能通过 chat.py (终端) 或 curl 与 LLM 交互。无法从 Telegram、Slack 等渠道接入。

## 目标

- [ ] 统一的 Channel 抽象（Channel → Session → LLM 的流水线）
- [ ] Telegram Bot Channel
- [ ] Slack Bot Channel
- [ ] Web Chat Channel (简单 HTML/JS)
- [ ] Channel Router：根据来源自动路由到对应 Session

## 设计

```python
class Channel(ABC):
    """所有 Channel 的基类"""
    @abstractmethod
    async def start(self): ...
    @abstractmethod
    async def stop(): ...
    @abstractmethod
    async def send_message(peer_id, text): ...

class ChannelRouter:
    """根据消息来源决定使用哪个 Session / Agent"""
    def route(message) -> Session: ...
```

## 接入流程

```
User → Telegram → Channel Adapter → Session Manager → LLM Call
                                    ← Response        ←
```

## 优先级

1. Telegram Bot（最简单，Bot API 不需要暴露端口）
2. Web Chat（需要简单的前端）
3. Slack（需要 App 注册）
