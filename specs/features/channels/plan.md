# Plan: Channel Adapters

## Step 1: Channel 抽象

**涉及文件**: `channels/base.py` (新建)

```python
class Channel(ABC):
    """所有 Channel 的基类"""
    @abstractmethod
    async def start(self): ...
    @abstractmethod
    async def stop(self): ...
    @abstractmethod
    async def send_message(peer_id, text): ...

class ChannelRouter:
    """根据消息来源路由到对应 Session"""
    def __init__(self, session_manager): ...
    async def route(peer_id, message) → str: ...
```

- Channel 接收消息 → 查找/创建 Session → 调用 LLM → 返回响应

## Step 2: Telegram Bot

**涉及文件**: `channels/telegram.py` (新建)

- 使用 Telegram Bot API (HTTP long-polling)
- `python-telegram-bot` 或裸 httpx 调用
- 每个 chat 映射为一个 Session
- 命令: `/new` 新对话, `/history` 查看历史

## Step 3: Web Chat

**涉及文件**: `channels/web.py` + `static/chat.html` (新建)

- 简单的 HTML/JS 聊天界面
- SSE 或 fetch POST 调用 Gateway API
- 不需要额外的 WebSocket 服务器

## Step 4: Slack Bot (延后)

**涉及文件**: `channels/slack.py` (新建)

- Slack Bolt SDK
- 需要 Slack App 注册

## 依赖

- Telegram: httpx (已有)
- Web Chat: 无新依赖 (静态文件)
- Slack: slack-bolt (按需安装)