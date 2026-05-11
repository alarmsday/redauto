"""WebSocket状态推送服务器 - asyncio实现"""

import asyncio
import json
from datetime import datetime
from typing import Set
from aiohttp import web
import threading


class StatusPushServer:
    """WebSocket状态推送服务器"""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.subscribers: Set[web.WebSocketResponse] = set()
        self._app: web.Application = None
        self._runner: web.AppRunner = None
        self._site: web.TCPSite = None
        self._lock = threading.Lock()

    async def _websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        with self._lock:
            self.subscribers.add(ws)

        try:
            # 发送当前状态快照
            await self._send_state_snapshot(ws)

            async for msg in ws:
                if msg.type == web.WSMsgType.ERROR:
                    print(f'WebSocket error: {ws.exception()}')
                    break
        finally:
            with self._lock:
                self.subscribers.discard(ws)

        return ws

    async def _send_state_snapshot(self, ws: web.WebSocketResponse):
        """发送当前状态快照给新连接客户端"""
        from data.shared_state import get_db, get_online_devices, get_pending_tasks

        db = get_db()
        with db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total, "
                          "SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) as completed, "
                          "SUM(CASE WHEN status='running' THEN 1 ELSE 0 END) as running "
                          "FROM task_queue")
            task_stats = dict(cursor.fetchone())

            cursor.execute("SELECT COUNT(*) as total FROM device_status")
            device_count = cursor.fetchone()[0]

        online_devices = get_online_devices()
        pending_tasks = get_pending_tasks(limit=10)

        snapshot = {
            "type": "snapshot",
            "data": {
                "task_stats": task_stats,
                "device_count": device_count,
                "online_devices": len(online_devices),
                "pending_tasks": pending_tasks,
                "timestamp": datetime.now().isoformat()
            }
        }
        await ws.send_str(json.dumps(snapshot))

    async def broadcast_status(self, device_id: str, status: str, progress: float = 0,
                              current_operation: str = "", error: str = None):
        """广播设备状态更新"""
        message = {
            "type": "status_update",
            "data": {
                "device_id": device_id,
                "status": status,
                "progress": progress,
                "current_operation": current_operation,
                "error": error,
                "timestamp": datetime.now().isoformat()
            }
        }
        await self._broadcast(json.dumps(message))

    async def broadcast_exception(self, device_id: str, exception_type: str,
                                 exception_message: str, retry_count: int):
        """广播异常事件"""
        message = {
            "type": "exception",
            "data": {
                "device_id": device_id,
                "exception_type": exception_type,
                "exception_message": exception_message,
                "retry_count": retry_count,
                "timestamp": datetime.now().isoformat()
            }
        }
        await self._broadcast(json.dumps(message))

    async def broadcast_task_complete(self, device_id: str, task_id: int,
                                     target_user: str, success: bool):
        """广播任务完成"""
        message = {
            "type": "task_complete",
            "data": {
                "device_id": device_id,
                "task_id": task_id,
                "target_user": target_user,
                "success": success,
                "timestamp": datetime.now().isoformat()
            }
        }
        await self._broadcast(json.dumps(message))

    async def _broadcast(self, message: str):
        """向所有订阅者广播消息"""
        dead_ws = set()
        with self._lock:
            for ws in self.subscribers:
                try:
                    await ws.send_str(message)
                except Exception:
                    dead_ws.add(ws)

        # 清理断开的连接
        for ws in dead_ws:
            self.subscribers.discard(ws)

    async def start(self):
        """启动服务器"""
        self._app = web.Application()
        self._app.router.add_get('/ws', self._websocket_handler)
        self._app.router.add_get('/', self._index_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        print(f"WebSocket server started on ws://{self.host}:{self.port}/ws")

    async def stop(self):
        """停止服务器"""
        if self._site:
            await self._site.stop()
        if self._runner:
            await self._runner.cleanup()

    async def _index_handler(self, request: web.Request) -> web.Response:
        """主页"""
        return web.Response(text="小红书多设备自动化运营系统 - 监控面板")


# 全局服务器实例
_server_instance: StatusPushServer = None
_server_lock = threading.Lock()


def get_status_server() -> StatusPushServer:
    global _server_instance
    if _server_instance is None:
        with _server_lock:
            if _server_instance is None:
                _server_instance = StatusPushServer()
    return _server_instance


async def run_server():
    """运行服务器（用于启动）"""
    server = get_status_server()
    await server.start()

    # 保持运行
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(run_server())
