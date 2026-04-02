# server.py
"""FastClaw Gateway 服务

FastAPI (端口 8765) serves both API and WebUI
"""

import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

from core.app import start
from gateway.router import router, set_websocket_api
from gateway.cron_scheduler import get_cron_scheduler
from gateway.channels import FeishuAdapter
from gateway.channels.feishu import set_main_loop

WEBUI_DIR = Path(__file__).parent.parent / "webui"

_channels = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    cron_scheduler = get_cron_scheduler()
    await cron_scheduler.start()
    yield
    await cron_scheduler.stop()


class GatewayServer:
    """FastClaw Gateway 服务"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.api = None
        self._server_thread = None
        self._stop_event = None

        self.app = FastAPI(title="FastClaw Gateway", lifespan=lifespan)
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        self.app.include_router(router)

        if WEBUI_DIR.exists():
            self.app.mount(
                "/webui/static",
                StaticFiles(directory=str(WEBUI_DIR / "static")),
                name="webui_static",
            )

        @self.app.get("/")
        async def root_page():
            return FileResponse(str(WEBUI_DIR / "index.html"))

    async def start(self):
        """启动 Gateway 服务"""
        self.api = await start()
        set_websocket_api(self.api)
        print(f"Gateway API started")

        await self._init_channels()

    async def _init_channels(self):
        """初始化渠道连接"""
        global _channels
        config_dir = Path("workspace/data/channels")

        if not config_dir.exists():
            print("No channels directory found, skipping channel initialization")
            return

        feishu_config_file = config_dir / "feishu_config.json"
        if feishu_config_file.exists():
            try:
                import json

                config = json.loads(feishu_config_file.read_text())
                if config.get("enabled"):
                    adapter = FeishuAdapter()
                    adapter.load_config_from_file(str(feishu_config_file))
                    await adapter.connect()
                    _channels["feishu"] = adapter
                    print(f"Feishu channel connected")
            except Exception as e:
                print(f"Failed to connect Feishu channel: {e}")

    async def stop(self):
        """停止 Gateway 服务"""
        global _channels
        for name, channel in _channels.items():
            try:
                await channel.disconnect()
                print(f"{name} channel disconnected")
            except Exception as e:
                print(f"Error disconnecting {name} channel: {e}")
        _channels.clear()

        if self.api:
            await self.api.stop()
        if self._stop_event:
            self._stop_event.set()
        if self._server_thread:
            self._server_thread.join(timeout=5)
        print("Gateway API stopped")

    def _run_server(self):
        """在独立线程中运行 uvicorn 服务器"""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        self._stop_event = asyncio.Event()

        # 设置主 loop 供飞书回调使用
        async def run_with_loop():
            set_main_loop(asyncio.get_running_loop())
            await server.serve()

        asyncio.run(run_with_loop())
        self._stop_event.set()

    def run(self):
        """在新线程中运行 uvicorn 服务器"""
        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()


async def main():
    """主函数"""
    server = GatewayServer()
    await server.start()

    print(f"FastClaw Gateway running at http://{server.host}:{server.port}")
    print(f"WebUI available at http://{server.host}:{server.port}/")
    print(f"SSE endpoint at http://{server.host}:{server.port}/api/chat/{{session_id}}")
    print(f"WebSocket available at ws://{server.host}:{server.port}/ws (legacy)")

    server.run()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
