"""每日操作次数追踪

记录每个目标用户当天的点赞收藏次数，超过上限后跳过该用户。
记录上次操作时间，同一用户两次操作间隔必须≥3分钟。
使用JSON文件持久化存储，跨日自动重置。
"""

import json
import os
import time
from datetime import datetime
from typing import Optional

TRACK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "daily_ops.json")
MIN_INTERVAL_SECONDS = 180  # 同一用户两次操作最小间隔：3分钟


def _load_tracker() -> dict:
    """加载追踪数据"""
    if os.path.exists(TRACK_FILE):
        with open(TRACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"date": "", "users": {}}


def _save_tracker(data: dict):
    """保存追踪数据"""
    os.makedirs(os.path.dirname(TRACK_FILE), exist_ok=True)
    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _check_and_reset_date(data: dict) -> dict:
    """检查日期，如果是新的一天则重置计数"""
    today = datetime.now().strftime("%Y-%m-%d")
    if data.get("date") != today:
        print(f"[每日追踪] 日期变更: {data.get('date', '无')} -> {today}，重置计数")
        data = {"date": today, "users": {}}
        _save_tracker(data)
    return data


def get_today_count(nickname: str) -> int:
    """获取某个目标用户今天的点赞收藏次数"""
    data = _load_tracker()
    data = _check_and_reset_date(data)
    user_data = data.get("users", {}).get(nickname)
    if user_data is None:
        return 0
    if isinstance(user_data, dict):
        return user_data.get("count", 0)
    # 兼容旧格式（只有数字）
    return user_data


def increment_count(nickname: str) -> int:
    """增加某个目标用户今天的点赞收藏次数，记录操作时间戳，返回当前次数"""
    data = _load_tracker()
    data = _check_and_reset_date(data)
    if nickname not in data["users"]:
        data["users"][nickname] = {"count": 0, "last_time": 0}
    if isinstance(data["users"][nickname], int):
        # 兼容旧格式（只有数字）
        data["users"][nickname] = {"count": data["users"][nickname], "last_time": time.time()}
    data["users"][nickname]["count"] += 1
    data["users"][nickname]["last_time"] = time.time()
    _save_tracker(data)
    return data["users"][nickname]["count"]


def get_time_since_last_operation(nickname: str) -> float:
    """获取距离上次操作的秒数，如果从未操作则返回99999"""
    data = _load_tracker()
    data = _check_and_reset_date(data)
    user_data = data.get("users", {}).get(nickname)
    if user_data is None:
        return 99999
    if isinstance(user_data, int):
        # 兼容旧格式
        return 99999
    last_time = user_data.get("last_time", 0)
    if last_time == 0:
        return 99999
    return time.time() - last_time


def can_operate(nickname: str, daily_limit: int) -> tuple[bool, str]:
    """
    检查是否可以操作某个目标用户的帖子

    Args:
        nickname: 目标用户昵称
        daily_limit: 每日操作上限

    Returns:
        (can_operate, reason) - 是否可操作及原因
    """
    count = get_today_count(nickname)
    if count >= daily_limit:
        return False, f"[每日追踪] {nickname} 今日已操作{count}次，达到上限({daily_limit})，跳过"

    # 检查间隔：同一用户两次操作必须≥3分钟
    elapsed = get_time_since_last_operation(nickname)
    if elapsed < MIN_INTERVAL_SECONDS:
        remaining = int(MIN_INTERVAL_SECONDS - elapsed)
        return False, f"[每日追踪] {nickname} 距上次操作仅{int(elapsed)}秒，还需等待{remaining}秒（最小间隔3分钟），跳过"

    return True, f"[每日追踪] {nickname} 今日已操作{count}次，距上次操作{int(elapsed)}秒"
