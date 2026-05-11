"""Action校验模块"""


class ActionValidationError(Exception):
    """Action校验异常"""
    pass


# 允许的action类型
VALID_ACTIONS = {"click", "swipe", "back", "restart_app", "wait", "human_alert", "skip"}

# 坐标范围（根据设备分辨率，这里用通用值）
VALID_RANGES = {
    "x": (0, 1440),
    "y": (0, 3200),
    "duration": (100, 2000),
    "seconds": (1, 60)
}


def validate_action(action: dict) -> bool:
    """
    校验action格式和参数

    Args:
        action: action字典

    Returns:
        是否合法

    Raises:
        ActionValidationError: 校验失败时抛出
    """
    if not isinstance(action, dict):
        raise ActionValidationError(f"action必须是字典，实际: {type(action)}")

    action_type = action.get("action")
    if not action_type:
        raise ActionValidationError("action缺少action字段")

    if action_type not in VALID_ACTIONS:
        raise ActionValidationError(f"未知的action类型: {action_type}")

    # 根据action类型校验参数
    if action_type == "click":
        return _validate_click(action)
    elif action_type == "swipe":
        return _validate_swipe(action)
    elif action_type == "wait":
        return _validate_wait(action)
    elif action_type in ("back", "restart_app", "skip"):
        return True
    elif action_type == "human_alert":
        return _validate_human_alert(action)

    return True


def _validate_click(action: dict) -> bool:
    """校验click action"""
    x = action.get("x")
    y = action.get("y")

    if x is None or y is None:
        raise ActionValidationError("click缺少x或y坐标")

    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        raise ActionValidationError(f"坐标必须是数字，实际: x={x}, y={y}")

    if not (VALID_RANGES["x"][0] <= x <= VALID_RANGES["x"][1]):
        raise ActionValidationError(f"x坐标超出范围: {x}")

    if not (VALID_RANGES["y"][0] <= y <= VALID_RANGES["y"][1]):
        raise ActionValidationError(f"y坐标超出范围: {y}")

    return True


def _validate_swipe(action: dict) -> bool:
    """校验swipe action"""
    for coord in ["x1", "y1", "x2", "y2"]:
        value = action.get(coord)
        if value is None:
            raise ActionValidationError(f"swipe缺少{coord}")

        if not isinstance(value, (int, float)):
            raise ActionValidationError(f"{coord}必须是数字，实际: {value}")

        axis = "x" if coord[0] == "x" else "y"
        if not (VALID_RANGES[axis][0] <= value <= VALID_RANGES[axis][1]):
            raise ActionValidationError(f"{coord}={value}超出范围")

    duration = action.get("duration", 300)
    if not (VALID_RANGES["duration"][0] <= duration <= VALID_RANGES["duration"][1]):
        raise ActionValidationError(f"duration={duration}超出范围")

    return True


def _validate_wait(action: dict) -> bool:
    """校验wait action"""
    seconds = action.get("seconds")
    if seconds is None:
        raise ActionValidationError("wait缺少seconds")

    if not isinstance(seconds, (int, float)):
        raise ActionValidationError(f"seconds必须是数字，实际: {seconds}")

    if not (VALID_RANGES["seconds"][0] <= seconds <= VALID_RANGES["seconds"][1]):
        raise ActionValidationError(f"seconds={seconds}超出范围")

    return True


def _validate_human_alert(action: dict) -> bool:
    """校验human_alert action"""
    reason = action.get("reason")
    if not reason:
        raise ActionValidationError("human_alert缺少reason")

    if not isinstance(reason, str):
        raise ActionValidationError(f"reason必须是字符串，实际: {type(reason)}")

    if len(reason) < 3:
        raise ActionValidationError(f"reason太短: {reason}")

    return True
