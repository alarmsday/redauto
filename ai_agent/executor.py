"""操作执行模块 - 实际调用设备控制器"""

import asyncio
from typing import Dict, Any


async def execute_action(action: Dict[str, Any], device_id: str) -> bool:
    """
    执行AI决策的action

    Args:
        action: action字典
        device_id: 设备ID

    Returns:
        执行是否成功
    """
    action_type = action.get("action")

    try:
        if action_type == "click":
            return await _execute_click(device_id, action["x"], action["y"])
        elif action_type == "swipe":
            return await _execute_swipe(
                device_id,
                action["x1"], action["y1"],
                action["x2"], action["y2"],
                action.get("duration", 300)
            )
        elif action_type == "back":
            return await _execute_back(device_id)
        elif action_type == "restart_app":
            return await _execute_restart_app(device_id)
        elif action_type == "wait":
            return await _execute_wait(action["seconds"])
        elif action_type == "human_alert":
            return await _execute_human_alert(device_id, action["reason"])
        elif action_type == "skip":
            return await _execute_skip(device_id, action.get("reason", ""))
        else:
            print(f"[Executor] Unknown action type: {action_type}")
            return False
    except Exception as e:
        print(f"[Executor] Action execution failed: {e}")
        return False


def _get_controller(device_id: str):
    """获取设备控制器"""
    from device_manager.controller import get_device_controller
    return get_device_controller(device_id)


async def _execute_click(device_id: str, x: int, y: int) -> bool:
    """执行点击"""
    try:
        ctrl = _get_controller(device_id)
        if ctrl and ctrl.is_connected():
            result = ctrl.click(x, y)
            print(f"[{device_id}] 点击: ({x}, {y}) -> {'成功' if result else '失败'}")
            return result
        else:
            print(f"[{device_id}] 设备未连接")
            return False
    except Exception as e:
        print(f"[{device_id}] 点击失败: {e}")
        return False


async def _execute_swipe(device_id: str, x1: int, y1: int, x2: int, y2: int, duration: int) -> bool:
    """执行滑动"""
    try:
        ctrl = _get_controller(device_id)
        if ctrl and ctrl.is_connected():
            result = ctrl.swipe(x1, y1, x2, y2, duration)
            print(f"[{device_id}] 滑动: ({x1},{y1}) -> ({x2},{y2}), {duration}ms -> {'成功' if result else '失败'}")
            return result
        else:
            print(f"[{device_id}] 设备未连接")
            return False
    except Exception as e:
        print(f"[{device_id}] 滑动失败: {e}")
        return False


async def _execute_back(device_id: str) -> bool:
    """执行返回"""
    try:
        ctrl = _get_controller(device_id)
        if ctrl and ctrl.is_connected():
            result = ctrl.press_back()
            print(f"[{device_id}] 按返回键 -> {'成功' if result else '失败'}")
            return result
        else:
            print(f"[{device_id}] 设备未连接")
            return False
    except Exception as e:
        print(f"[{device_id}] 返回失败: {e}")
        return False


async def _execute_restart_app(device_id: str) -> bool:
    """重启APP"""
    try:
        ctrl = _get_controller(device_id)
        if ctrl and ctrl.is_connected():
            print(f"[{device_id}] 重启小红书APP...")
            result = ctrl.restart_app()
            return result
        else:
            print(f"[{device_id}] 设备未连接")
            return False
    except Exception as e:
        print(f"[{device_id}] 重启APP失败: {e}")
        return False


async def _execute_wait(seconds: float) -> bool:
    """等待"""
    print(f"等待 {seconds} 秒...")
    await asyncio.sleep(seconds)
    return True


async def _execute_human_alert(device_id: str, reason: str) -> bool:
    """人工告警"""
    try:
        from ai_agent.human_alert import trigger_human_alert
        ctrl = _get_controller(device_id)

        # 获取截图
        screenshot = b""
        if ctrl and ctrl.is_connected():
            screenshot = ctrl.take_screenshot()

        # 触发人工告警（会暂停等待）
        await trigger_human_alert(
            device_id=device_id,
            reason=reason,
            screenshot_base64= screenshot
        )
        return True
    except Exception as e:
        print(f"[{device_id}] 人工告警失败: {e}")
        return False


async def _execute_skip(device_id: str, reason: str) -> bool:
    """跳过任务"""
    print(f"[{device_id}] 跳过任务: {reason}")
    return True
