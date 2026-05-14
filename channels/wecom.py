"""企业微信 Channel implementation.

使用企业微信官方API收发消息。

配置步骤:
1. 在企业微信管理后台创建自建应用
2. 获取 CorpID、AgentId、Secret
3. 设置环境变量:
   - WECOM_CORP_ID: 企业ID
   - WECOM_AGENT_ID: 应用AgentId
   - WECOM_SECRET: 应用Secret
4. 配置回调URL（可选，用于接收消息）

消息模式:
- 主动发送: 调用API发送消息给指定用户
- 被动接收: 设置回调URL，企业微信推送消息到你的服务器
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Any

import httpx
from wechatpy.enterprise import WeChatClient
from wechatpy.enterprise.crypto import WeChatCrypto
from wechatpy.exceptions import WeChatException

from channels.base import Channel
from sessions.manager import SessionManager

logger = logging.getLogger(__name__)


class WeComChannel(Channel):
    """企业微信 Channel.

    支持两种模式:
    1. 主动发送消息 (发送通知、测试)
    2. 被动接收消息 (用户在企业微信应用中发消息)
    """

    name = "wecom"

    def __init__(
        self,
        session_manager: SessionManager,
        gateway_url: str = "http://127.0.0.1:8000",
    ):
        self._session_manager = session_manager
        self._gateway_url = gateway_url

        # 企业微信凭证
        self._corp_id = os.environ.get("WECOM_CORP_ID", "")
        self._agent_id = int(os.environ.get("WECOM_AGENT_ID", "0"))
        self._secret = os.environ.get("WECOM_SECRET", "")

        # 回调配置（被动接收消息）
        self._token = os.environ.get("WECOM_TOKEN", "")  # 回调Token
        self._encoding_aes_key = os.environ.get("WECOM_ENCODING_AES_KEY", "")  # 回调AES密钥

        # WeChatClient实例
        self._client: WeChatClient | None = None
        self._crypto: WeChatCrypto | None = None
        self._http_client = httpx.AsyncClient(timeout=30.0)
        self._running = False

    async def start(self) -> None:
        """启动企业微信Channel."""
        if not self._corp_id or not self._secret:
            logger.warning("[WeCom] Missing WECOM_CORP_ID or WECOM_SECRET, skipping")
            return

        # 初始化WeChatClient
        self._client = WeChatClient(
            corp_id=self._corp_id,
            secret=self._secret,
        )

        logger.info(f"[WeCom] Channel initialized: CorpID={self._corp_id}, AgentId={self._agent_id}")

        # 测试发送消息功能
        try:
            # 获取access_token测试连接
            access_token = self._client.access_token
            logger.info(f"[WeCom] Access token obtained: {access_token[:20]}...")
        except WeChatException as e:
            logger.error(f"[WeCom] Failed to get access token: {e}")

        # 初始化回调解密器（如果配置了）
        if self._token and self._encoding_aes_key:
            self._crypto = WeChatCrypto(
                token=self._token,
                encoding_aes_key=self._encoding_aes_key,
                corp_id=self._corp_id,
            )
            logger.info("[WeCom] Callback crypto initialized")

        self._running = True

    async def stop(self) -> None:
        """停止Channel."""
        self._running = False
        await self._http_client.aclose()
        logger.info("[WeCom] Channel stopped")

    async def send_message(self, peer_id: str, text: str) -> None:
        """发送消息给企业微信用户.

        Args:
            peer_id: 用户ID（企业微信用户账号，如 "ZhangSan" 或 "user123"）
            text: 消息内容
        """
        if not self._client:
            logger.error("[WeCom] Client not initialized")
            return

        try:
            # 使用WeChatClient发送消息
            # message.send() 返回消息ID
            result = self._client.message.send(
                agent_id=self._agent_id,
                user_ids=[peer_id],  # 用户ID列表
                msg_type="text",
                content=text,
            )
            logger.info(f"[WeCom] Message sent to {peer_id}: msg_id={result}")

        except WeChatException as e:
            logger.error(f"[WeCom] Failed to send message: {e}")

    async def handle_message(self, message: Any) -> None:
        """处理收到的企业微信消息.

        Args:
            message: 企业微信推送的消息数据（已解密）
        """
        if not isinstance(message, dict):
            return

        # 解析消息
        from_user = message.get("FromUserName", "")
        content = message.get("Content", "")
        msg_type = message.get("MsgType", "text")

        if msg_type != "text" or not content:
            logger.debug(f"[WeCom] Ignoring non-text message: {msg_type}")
            return

        logger.info(f"[WeCom] Received message from {from_user}: {content[:50]}...")

        # 调用Gateway处理消息
        await self._process_chat(from_user, content)

    async def _process_chat(self, from_user: str, text: str) -> None:
        """将消息发送到Gateway处理.

        Args:
            from_user: 发送者企业微信ID
            text: 消息内容
        """
        session_name = f"wecom-{from_user}"

        # 查找或创建session
        sessions = self._session_manager.list_sessions()
        matched = [s for s in sessions if s.name == session_name]

        if matched:
            session = matched[0]
            session_id = session.id
        else:
            session = self._session_manager.create_session(
                name=session_name,
                model="deepseek-chat",
            )
            session_id = session.id

        # 调用Gateway API
        try:
            response = await self._http_client.post(
                f"{self._gateway_url}/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "X-Session-Id": session_id,
                },
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": text}],
                },
            )

            if response.status_code == 200:
                data = response.json()
                assistant_msg = data.get("choices", [{}])[0].get("message", {})
                reply = assistant_msg.get("content", "")
                if reply:
                    await self.send_message(from_user, reply)
            else:
                logger.error(f"[WeCom] Gateway error: {response.status_code}")
                await self.send_message(from_user, "处理失败，请稍后再试")

        except Exception as e:
            logger.error(f"[WeCom] Gateway request failed: {e}")
            await self.send_message(from_user, f"系统错误: {str(e)}")

    # ===== 回调URL处理 (用于接收消息) =====

    def verify_callback_signature(
        self,
        signature: str,
        timestamp: str,
        nonce: str,
        echo_str: str | None = None,
    ) -> bool:
        """验证企业微信回调签名.

        企业微信在设置回调URL时会发送验证请求，
        使用Token计算签名来验证请求来自企业微信服务器。
        """
        if not self._token:
            return False

        # 计算签名
        sign_list = [self._token, timestamp, nonce]
        if echo_str:
            sign_list.append(echo_str)
        sign_list.sort()
        sign_str = "".join(sign_list)
        calculated = hashlib.sha1(sign_str.encode()).hexdigest()

        return calculated == signature

    def decrypt_message(self, encrypted_msg: str) -> dict:
        """解密企业微信推送的消息.

        Args:
            encrypted_msg: 企业微信推送的加密消息

        Returns:
            解密后的消息dict
        """
        if not self._crypto:
            raise ValueError("WeComCrypto not initialized (missing Token/AESKey)")

        return self._crypto.decrypt_message(encrypted_msg)


# ===== FastAPI路由处理器 (可选，用于接收回调消息) =====

def create_wecom_callback_handler(channel: WeComChannel):
    """创建企业微信回调处理器.

    返回一个FastAPI路由函数，用于处理企业微信推送的消息。
    """
    from fastapi import Request, Response

    async def wecom_callback(request: Request):
        """企业微信消息回调入口."""
        # 获取查询参数
        msg_signature = request.query_params.get("msg_signature", "")
        timestamp = request.query_params.get("timestamp", "")
        nonce = request.query_params.get("nonce", "")

        # 验证请求体
        body = await request.body()

        if not channel._crypto:
            logger.error("[WeCom] Callback received but crypto not initialized")
            return Response(content="Crypto not initialized", status_code=500)

        try:
            # 解密消息
            # XML格式: <Encrypt>...</Encrypt>
            import xml.etree.ElementTree as ET
            xml_content = body.decode("utf-8")
            root = ET.fromstring(xml_content)
            encrypt = root.find("Encrypt")
            if encrypt is None:
                return Response(content="Invalid XML", status_code=400)

            encrypted_msg = encrypt.text
            decrypted = channel.decrypt_message(encrypted_msg)

            # 处理消息
            await channel.handle_message(decrypted)

            return Response(content="success")

        except Exception as e:
            logger.error(f"[WeCom] Callback error: {e}")
            return Response(content=str(e), status_code=500)

    async def wecom_verify(request: Request):
        """企业微信回调URL验证.

        设置回调URL时，企业微信会发送GET请求验证。
        """
        signature = request.query_params.get("msg_signature", "")
        timestamp = request.query_params.get("timestamp", "")
        nonce = request.query_params.get("nonce", "")
        echostr = request.query_params.get("echostr", "")

        if channel.verify_callback_signature(signature, timestamp, nonce, echostr):
            # 解密echostr并返回
            if echostr and channel._crypto:
                decrypted_echo = channel._crypto.decrypt_message(echostr)
                return Response(content=decrypted_echo)
            return Response(content="success")

        return Response(content="Invalid signature", status_code=403)

    return wecom_callback, wecom_verify