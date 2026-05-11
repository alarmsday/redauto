"""Data storage module"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path


class StorageManager:
    """Storage manager for screenshots, logs, and reports"""

    def __init__(self, base_dir: str = "output"):
        self.base_dir = base_dir

    def _get_account_dir(self, account_name: str) -> Path:
        """Get directory for account"""
        account_dir = Path(self.base_dir) / account_name
        account_dir.mkdir(parents=True, exist_ok=True)
        return account_dir

    def _get_user_dir(self, account_name: str, user_nickname: str) -> Path:
        """Get directory for user"""
        user_dir = self._get_account_dir(account_name) / user_nickname
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _create_subdirs(self, account_name: str):
        """Create standard subdirectories"""
        account_dir = self._get_account_dir(account_name)
        subdirs = ["发现页截图", "操作完成截图", "异常报告"]
        for subdir in subdirs:
            (account_dir / subdir).mkdir(exist_ok=True)

    def save_screenshot(
        self,
        account_name: str,
        user_nickname: str,
        device_id: str,
        page_type: str,
        timestamp: datetime = None
    ) -> str:
        """
        Save screenshot with standardized naming

        Format: {device_id}_{user_nickname}_{page_type}_{timestamp}.png
        """
        if timestamp is None:
            timestamp = datetime.now()

        self._create_subdirs(account_name)

        filename = f"{device_id}_{user_nickname}_{page_type}_{timestamp.strftime('%Y%m%d_%H%M%S')}.png"
        filepath = self._get_user_dir(account_name, user_nickname) / filename

        # TODO: Actually save the screenshot data
        # For now, just return the path
        print(f"[Storage] Screenshot saved: {filepath}")
        return str(filepath)

    def save_discovery_screenshot(
        self,
        account_name: str,
        user_nickname: str,
        device_id: str,
        screenshot_data: bytes
    ) -> str:
        """Save discovery page screenshot"""
        filepath = self.save_screenshot(
            account_name, user_nickname, device_id, "发现页"
        )
        if screenshot_data and filepath:
            with open(filepath, 'wb') as f:
                f.write(screenshot_data)
        return filepath

    def save_operation_screenshot(
        self,
        account_name: str,
        user_nickname: str,
        device_id: str,
        screenshot_data: bytes
    ) -> str:
        """Save operation completion screenshot"""
        filepath = self.save_screenshot(
            account_name, user_nickname, device_id, "操作完成"
        )
        if screenshot_data and filepath:
            with open(filepath, 'wb') as f:
                f.write(screenshot_data)
        return filepath

    def save_exception_screenshot(
        self,
        account_name: str,
        device_id: str,
        exception_type: str,
        screenshot_data: bytes
    ) -> str:
        """Save exception screenshot"""
        self._create_subdirs(account_name)
        account_dir = self._get_account_dir(account_name)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{device_id}_{exception_type}_{timestamp}.png"
        filepath = account_dir / "异常报告" / filename

        # Write screenshot data
        if screenshot_data:
            with open(filepath, 'wb') as f:
                f.write(screenshot_data)
        print(f"[Storage] Exception screenshot saved: {filepath}")
        return str(filepath)

    def append_operation_log(
        self,
        account_name: str,
        log_entry: Dict[str, Any]
    ):
        """Append operation log entry"""
        self._create_subdirs(account_name)
        account_dir = self._get_account_dir(account_name)
        log_file = account_dir / "操作日志.log"

        # Format: timestamp|device_id|operation_type|status|duration|notes
        timestamp = log_entry.get('timestamp', datetime.now().isoformat())
        device_id = log_entry.get('device_id', '')
        operation_type = log_entry.get('operation_type', '')
        status = log_entry.get('status', '')
        duration = log_entry.get('duration', 0)
        notes = log_entry.get('notes', '')

        log_line = f"{timestamp}|{device_id}|{operation_type}|{status}|{duration}|{notes}\n"

        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(log_line)

    def generate_statistics_report(
        self,
        account_name: str,
        task_stats: Dict[str, Any]
    ) -> str:
        """
        Generate task statistics report

        Returns:
            Path to generated report
        """
        self._create_subdirs(account_name)
        account_dir = self._get_account_dir(account_name)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"任务统计报告_{timestamp}.md"
        filepath = account_dir / filename

        # Build report content
        content = f"""# 任务统计报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 任务概况

- **任务总耗时**: {task_stats.get('total_duration', 'N/A')}
- **参与设备数**: {task_stats.get('device_count', 0)}
- **处理目标用户数**: {task_stats.get('users_processed', 0)}
- **处理帖子总数**: {task_stats.get('posts_processed', 0)}

## 操作统计

- **点赞成功数**: {task_stats.get('likes_success', 0)}
- **收藏成功数**: {task_stats.get('favorites_success', 0)}
- **异常发生次数**: {task_stats.get('exception_count', 0)}

## AI Agent 统计

- **AI处理异常次数**: {task_stats.get('ai_handled_count', 0)}
- **AI处理成功率**: {task_stats.get('ai_success_rate', 'N/A')}

## 异常统计

{self._format_exception_stats(task_stats.get('exceptions', []))}
"""

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        print(f"[Storage] Statistics report saved: {filepath}")
        return str(filepath)

    def _format_exception_stats(self, exceptions: list) -> str:
        """Format exception statistics"""
        if not exceptions:
            return "无异常记录"

        lines = []
        for exc in exceptions:
            lines.append(f"- **{exc.get('type', 'Unknown')}**: {exc.get('count', 0)}次")
        return "\n".join(lines)


# Global instance
_storage_manager: StorageManager = None


def get_storage_manager() -> StorageManager:
    global _storage_manager
    if _storage_manager is None:
        _storage_manager = StorageManager()
    return _storage_manager
