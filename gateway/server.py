# server.py
"""FastClaw Gateway 服务

FastAPI (端口 8765) serves both API and WebUI
"""

import asyncio
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse
import uvicorn

from core.app import start
from gateway.router import router, set_websocket_api

WEBUI_DIR = Path(__file__).parent.parent / "webui"


class GatewayServer:
    """FastClaw Gateway 服务"""

    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.api = None
        self._server_thread = None
        self._stop_event = None

        self.app = FastAPI(title="FastClaw Gateway")
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

    async def stop(self):
        """停止 Gateway 服务"""
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
        asyncio.run(server.serve())
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
    print(f"WebSocket available at ws://{server.host}:{server.port}/ws")

    server.run()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        await server.stop()


if __name__ == "__main__":
    asyncio.run(main())
