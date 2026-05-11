"""自学习模块 - 案例库管理"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from data.shared_state import (
    add_case, increment_case_usage, mark_case_failed,
    find_exact_match, find_similar_case
)


class SelfLearner:
    """自学习模块 - 管理案例库"""

    def __init__(self, similarity_threshold: float = 0.85):
        self.similarity_threshold = similarity_threshold

    def record_success(
        self,
        exception_type: str,
        screen_hash: str,
        control_tree: str,
        action: Dict[str, Any],
        context_summary: str = "",
        screen_embedding: bytes = None
    ) -> int:
        """
        记录成功案例

        Returns:
            案例ID
        """
        return add_case(
            exception_type=exception_type,
            screen_hash=screen_hash,
            screen_embedding=screen_embedding,
            control_tree=control_tree,
            action_taken=json.dumps(action),
            success=True,
            context_summary=context_summary
        )

    def record_failure(self, case_id: int):
        """记录失败案例"""
        mark_case_failed(case_id)

    def find_best_case(
        self,
        screen_hash: str,
        exception_type: str
    ) -> Optional[Dict[str, Any]]:
        """
        查找最佳匹配案例

        Args:
            screen_hash: 当前屏幕截图hash
            exception_type: 异常类型

        Returns:
            最佳匹配案例，未找到返回None
        """
        # 1. 精确匹配
        exact_case = find_exact_match(screen_hash)
        if exact_case:
            increment_case_usage(exact_case['id'])
            return exact_case

        # 2. 相似匹配
        similar_case = find_similar_case(exception_type)
        if similar_case:
            increment_case_usage(similar_case['id'])
            return similar_case

        return None

    def cleanup_old_cases(self, days: int = 30, min_usage: int = 3) -> int:
        """
        清理旧案例（不删除，只是标记）

        注意：这个函数实际不会删除案例，只是检查哪些案例可以归档

        Args:
            days: 案例创建超过此天数
            min_usage: 使用次数低于此值

        Returns:
            符合清理条件的案例数
        """
        # TODO: 实现清理逻辑
        # 暂时只是标记，不实际删除
        return 0

    def get_case_stats(self) -> Dict[str, Any]:
        """获取案例库统计"""
        from data.shared_state import get_db

        db = get_db()
        with db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as total FROM case_library")
            total = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) as successful FROM case_library WHERE success = 1")
            successful = cursor.fetchone()[0]

            cursor.execute("SELECT exception_type, COUNT(*) as count FROM case_library GROUP BY exception_type")
            by_type = {row[0]: row[1] for row in cursor.fetchall()}

            cursor.execute("SELECT SUM(used_count) as total_usage FROM case_library")
            total_usage = cursor.fetchone()[0] or 0

        return {
            "total_cases": total,
            "successful_cases": successful,
            "success_rate": successful / total if total > 0 else 0,
            "by_exception_type": by_type,
            "total_usage": total_usage
        }
