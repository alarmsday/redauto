"""共享状态数据库模块 - SQLite WAL模式支持多进程并发"""

import sqlite3
import threading
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
import os

DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "shared_state.db")


class SharedStateDB:
    """线程安全的SQLite数据库封装，支持WAL模式"""

    _local = threading.local()

    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._ensure_dir()
        self._init_database()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'connection'):
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            self._local.connection = conn
        return self._local.connection

    @contextmanager
    def get_cursor(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _init_database(self):
        with self.get_cursor() as cursor:
            # 任务队列
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_user_id TEXT,
                    target_nickname TEXT,
                    device_id TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)

            # 操作记录
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS operation_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_user_id TEXT NOT NULL,
                    device_id TEXT,
                    operation_type TEXT,
                    operated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 设备状态
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS device_status (
                    device_id TEXT PRIMARY KEY,
                    status TEXT DEFAULT 'offline',
                    current_task_id INTEGER,
                    last_heartbeat TIMESTAMP,
                    device_name TEXT,
                    connection_type TEXT
                )
            """)

            # 案例库
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS case_library (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    exception_type TEXT,
                    screen_hash TEXT,
                    screen_embedding BLOB,
                    control_tree TEXT,
                    context_summary TEXT,
                    action_taken TEXT,
                    success INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    used_count INTEGER DEFAULT 0
                )
            """)

            # 账号保护
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS account_protection (
                    account TEXT PRIMARY KEY,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    daily_count INTEGER DEFAULT 0,
                    last_daily_reset DATE
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON task_queue(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_user ON operation_records(target_user_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_operation_date ON operation_records(operated_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_type ON case_library(exception_type)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_case_hash ON case_library(screen_hash)")


# 全局数据库实例
_db_instance: Optional[SharedStateDB] = None
_db_lock = threading.Lock()


def get_db() -> SharedStateDB:
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                _db_instance = SharedStateDB()
    return _db_instance


# ============== 任务队列操作 ==============

def create_task(target_user_id: str, target_nickname: str) -> int:
    """创建新任务"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO task_queue (target_user_id, target_nickname) VALUES (?, ?)",
            (target_user_id, target_nickname)
        )
        return cursor.lastrowid


def get_pending_tasks(limit: int = 10) -> List[Dict[str, Any]]:
    """获取待处理任务"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM task_queue WHERE status = 'pending' ORDER BY created_at LIMIT ?",
            (limit,)
        )
        return [dict(row) for row in cursor.fetchall()]


def assign_task_to_device(task_id: int, device_id: str) -> bool:
    """分配任务给设备（原子操作）"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "UPDATE task_queue SET status = 'running', device_id = ?, started_at = ? "
            "WHERE id = ? AND status = 'pending'",
            (device_id, datetime.now(), task_id)
        )
        return cursor.rowcount > 0


def complete_task(task_id: int, status: str = 'completed'):
    """完成任务"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "UPDATE task_queue SET status = ?, completed_at = ? WHERE id = ?",
            (status, datetime.now(), task_id)
        )


# ============== 操作记录操作 ==============

def record_operation(target_user_id: str, device_id: str, operation_type: str):
    """记录操作"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO operation_records (target_user_id, device_id, operation_type) VALUES (?, ?, ?)",
            (target_user_id, device_id, operation_type)
        )


def get_user_operation_count_today(target_user_id: str) -> int:
    """获取用户今日操作次数"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM operation_records "
            "WHERE target_user_id = ? AND date(operated_at) = date('now')",
            (target_user_id,)
        )
        return cursor.fetchone()[0]


def get_last_operation_time(target_user_id: str) -> Optional[datetime]:
    """获取用户最后一次操作时间"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT MAX(operated_at) FROM operation_records WHERE target_user_id = ?",
            (target_user_id,)
        )
        result = cursor.fetchone()[0]
        return datetime.fromisoformat(result) if result else None


# ============== 设备状态操作 ==============

def update_device_status(device_id: str, status: str, current_task_id: int = None, device_name: str = None, connection_type: str = None):
    """更新设备状态"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT OR REPLACE INTO device_status "
            "(device_id, status, current_task_id, last_heartbeat, device_name, connection_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (device_id, status, current_task_id, datetime.now(), device_name, connection_type)
        )


def get_online_devices() -> List[Dict[str, Any]]:
    """获取在线设备"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM device_status WHERE status IN ('online', 'running')"
        )
        return [dict(row) for row in cursor.fetchall()]


def get_device_status(device_id: str) -> Optional[Dict[str, Any]]:
    """获取设备状态"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM device_status WHERE device_id = ?", (device_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


# ============== 案例库操作 ==============

def add_case(exception_type: str, screen_hash: str, control_tree: str,
             action_taken: str, success: bool, context_summary: str = "",
             screen_embedding: bytes = None) -> int:
    """添加案例"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "INSERT INTO case_library "
            "(exception_type, screen_hash, control_tree, action_taken, success, context_summary, screen_embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (exception_type, screen_hash, control_tree, action_taken, int(success), context_summary, screen_embedding)
        )
        return cursor.lastrowid


def find_exact_match(screen_hash: str) -> Optional[Dict[str, Any]]:
    """精确匹配案例"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM case_library WHERE screen_hash = ? AND success = 1 ORDER BY used_count DESC LIMIT 1",
            (screen_hash,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def find_similar_case(exception_type: str) -> Optional[Dict[str, Any]]:
    """相似案例查找（简化版：同类型+成功）"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT * FROM case_library WHERE exception_type = ? AND success = 1 "
            "ORDER BY used_count DESC, created_at DESC LIMIT 1",
            (exception_type,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def increment_case_usage(case_id: int):
    """增加案例使用次数"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("UPDATE case_library SET used_count = used_count + 1 WHERE id = ?", (case_id,))


def mark_case_failed(case_id: int):
    """标记案例失败"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("UPDATE case_library SET success = 0 WHERE id = ?", (case_id,))


# ============== 账号保护 ==============

def init_account(account: str) -> bool:
    """初始化账号记录（首次使用时）"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT account FROM account_protection WHERE account = ?",
            (account,)
        )
        if cursor.fetchone():
            return False  # 已存在
        cursor.execute(
            "INSERT INTO account_protection (account, created_at, daily_count, last_daily_reset) VALUES (?, ?, 0, ?)",
            (account, datetime.now(), date.today().isoformat())
        )
        return True


def check_account_protection(account: str, ramp_days: int, daily_limit: int) -> tuple[bool, str]:
    """检查账号是否允许继续操作
    Returns:
        (是否允许, 原因描述)
    """
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT created_at, daily_count, last_daily_reset FROM account_protection WHERE account = ?",
            (account,)
        )
        row = cursor.fetchone()
        if not row:
            # 首次使用，初始化
            init_account(account)
            return (True, "新账号初始化")

        created_at = datetime.fromisoformat(row["created_at"])
        daily_count = row["daily_count"]
        last_daily_reset = row["last_daily_reset"]
        today = date.today()

        # 检查是否需要重置每日计数
        if last_daily_reset != today.isoformat():
            cursor.execute(
                "UPDATE account_protection SET daily_count = 0, last_daily_reset = ? WHERE account = ?",
                (today.isoformat(), account)
            )
            daily_count = 0

        # 养号期检查
        days_since_creation = (datetime.now() - created_at).days
        if days_since_creation < ramp_days:
            # 新账号每日限制
            if daily_count >= daily_limit:
                return (False, f"新账号养号期（第{days_since_creation + 1}天），今日已达上限{daily_limit}次")
        else:
            # 成熟账号使用全局限制
            if daily_count >= daily_limit:
                return (False, f"今日操作已达上限{daily_limit}次")

        return (True, "")


def increment_account_daily_count(account: str):
    """增加账号今日操作次数"""
    db = get_db()
    today = date.today()
    with db.get_cursor() as cursor:
        # 先检查是否需要重置
        cursor.execute(
            "SELECT last_daily_reset FROM account_protection WHERE account = ?",
            (account,)
        )
        row = cursor.fetchone()
        if row and row["last_daily_reset"] != today.isoformat():
            cursor.execute(
                "UPDATE account_protection SET daily_count = 1, last_daily_reset = ? WHERE account = ?",
                (today.isoformat(), account)
            )
        else:
            cursor.execute(
                "UPDATE account_protection SET daily_count = daily_count + 1 WHERE account = ?",
                (account,)
            )


def get_account_age_days(account: str) -> int:
    """获取账号已使用天数"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT created_at FROM account_protection WHERE account = ?",
            (account,)
        )
        row = cursor.fetchone()
        if row:
            created_at = datetime.fromisoformat(row["created_at"])
            return (datetime.now() - created_at).days
        return 0


def get_account_daily_count(account: str) -> int:
    """获取账号今日已操作次数"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute(
            "SELECT daily_count, last_daily_reset FROM account_protection WHERE account = ?",
            (account,)
        )
        row = cursor.fetchone()
        if row:
            if row["last_daily_reset"] != date.today().isoformat():
                return 0
            return row["daily_count"]
        return 0
