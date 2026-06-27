# Copyright (c) 2024-2026 xiefujin <490021684@qq.com>
# Licensed under GNU GPLv3, see LICENSE file for full license terms.
"""iMessage 渠道适配器（Mac）"""

import asyncio
import subprocess
from typing import Optional

from gateway.channels.base import ChannelAdapter


class IMessageAdapter(ChannelAdapter):
    """iMessage 渠道适配器（仅支持 Mac）

    通过 AppleScript 与 Mac 上的 iMessage 交互。
    """

    def __init__(self):
        super().__init__("imessage")
        self.recipient = None

    async def connect(self):
        """建立连接（iMessage 不需要主动连接）"""
        print("iMessage adapter initialized")

    async def disconnect(self):
        """断开连接"""
        print("iMessage adapter disconnected")

    async def send_message(self, message: str, session_id: str = None):
        """发送 iMessage

        Args:
            message: 消息内容
            session_id: 格式为 imessage_{recipient}
        """
        recipient = session_id or self.recipient
        if not recipient:
            raise ValueError("Recipient is required for iMessage")

        recipient = (
            recipient.replace("imessage_", "")
            if recipient.startswith("imessage_")
            else recipient
        )

        script = f'''
        osascript -e '
        tell application "Messages"
            set targetService to 1
            set targetBuddy to "{recipient}"
            set msg to "{message.replace('"', '\\"')}"
            send msg to buddy targetBuddy of service id targetService
        end tell
        '
        '''

        try:
            result = subprocess.run(
                script,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                raise Exception(f"AppleScript error: {result.stderr}")

            return {"status": "sent", "recipient": recipient}

        except subprocess.TimeoutExpired:
            raise Exception("iMessage send timed out")
        except Exception as e:
            raise Exception(f"Failed to send iMessage: {e}")

    async def on_message(self, message: dict):
        """接收消息（iMessage 作为输入源）"""
        from gateway.router import _websocket_api
        from gateway.channels.handlers import handle_channel_message

        if not _websocket_api:
            print("[iMessage] ERROR: _websocket_api is None!")
            return

        text = message.get("text", "")
        sender = message.get("sender", "")
        if not text or not sender:
            return

        session_id = f"imessage_{sender}"
        print(f"[iMessage] Message from {sender}, session={session_id}")

        async def imessage_send(msg, sid):
            await self.send_message(msg, session_id=sid)

        await handle_channel_message(
            channel_name="imessage",
            sender_id=session_id,
            text_content=text,
            api=_websocket_api,
            send_func=imessage_send,
        )

    async def listen_incoming(self, callback):
        """监听传入消息（轮询方式）

        这是一个简化的实现，实际使用中可能需要使用 Notification Center
        或其他方式来监听 iMessage。

        Args:
            callback: 消息回调函数
        """
        script = """
        osascript -e '
        on run
            tell application "Messages"
                set theMessages to (every message of every chat)
                set msgList to {}
                repeat with aMessage in theMessages
                    set msgText to content of aMessage
                    set msgDate to date of aMessage
                    set msgSender to sender of aMessage
                    set end of msgList to msgText & "|" & msgDate & "|" & msgSender
                end repeat
                return msgList
            end tell
        end run
        """
        try:
            result = subprocess.run(
                script,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    parts = line.split("|")
                    if len(parts) >= 3:
                        await callback(
                            {
                                "text": parts[0],
                                "date": parts[1],
                                "sender": parts[2],
                            }
                        )

        except Exception as e:
            print(f"Error listening for iMessages: {e}")
