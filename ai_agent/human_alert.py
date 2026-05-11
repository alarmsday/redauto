"""人工告警模块"""

import asyncio
import threading
from typing import Optional, Dict, Any
from datetime import datetime


# 告警等待队列
_alert_waits: Dict[str, asyncio.Event] = {}
_alert_lock = threading.Lock()


async def trigger_human_alert(
    device_id: str,
    reason: str,
    screenshot_base64: Optional[str] = None,
    operation_context: Optional[Dict[str, Any]] = None
) -> bool:
    """
    触发人工告警，暂停workflow等待人工处理

    Args:
        device_id: 设备ID
        reason: 告警原因
        screenshot_base64: 截图base64（可以是bytes或str）
        operation_context: 操作上下文

    Returns:
        人工处理完成后返回True
    """
    # 确保screenshot_base64是字符串
    if screenshot_base64 and isinstance(screenshot_base64, bytes):
        import base64
        screenshot_base64 = base64.b64encode(screenshot_base64).decode()

    # 1. 发送告警通知
    await _send_notification(device_id, reason, screenshot_base64)

    # 2. 创建等待事件
    alert_event = asyncio.Event()
    with _alert_lock:
        _alert_waits[device_id] = alert_event

    # 3. 等待人工处理
    print(f"[人工告警] 设备{device_id}等待人工处理: {reason}")
    await alert_event.wait()

    # 4. 清理
    with _alert_lock:
        _alert_waits.pop(device_id, None)

    print(f"[人工告警] 设备{device_id}人工处理完成，继续执行")
    return True


async def _send_notification(
    device_id: str,
    reason: str,
    screenshot_base64: Optional[str] = None
):
    """
    发送告警通知（桌面通知+声音）
    """
    try:
        # 桌面通知
        from plyer import notification
        notification.notify(
            title=f"小红书自动化 - 人工介入 required",
            message=f"设备{device_id}: {reason[:100]}",
            app_name="Xiaohongshu Auto",
            timeout=0  # 持续显示直到人工处理
        )
    except ImportError:
        print("[警告] plyer未安装，无法发送桌面通知")

    # 播放声音
    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        print("[警告] 无法播放告警声音")

    # 广播到WebSocket
    try:
        from data.websocket_server import get_status_server
        server = get_status_server()
        await server.broadcast_exception(
            device_id=device_id,
            exception_type="human_alert",
            exception_message=reason,
            retry_count=0
        )
    except Exception as e:
        print(f"[警告] WebSocket广播失败: {e}")


def resolve_alert(device_id: str):
    """
    解决告警，允许workflow继续执行

    通常由监控面板调用
    """
    with _alert_lock:
        if device_id in _alert_waits:
            _alert_waits[device_id].set()


def get_pending_alerts() -> Dict[str, str]:
    """
    获取所有待处理的告警

    Returns:
        device_id -> reason
    """
    with _alert_lock:
        return {device_id: "人工处理中" for device_id in _alert_waits.keys()}


def is_alert_pending(device_id: str) -> bool:
    """检查设备是否有待处理的告警"""
    with _alert_lock:
        return device_id in _alert_waits
