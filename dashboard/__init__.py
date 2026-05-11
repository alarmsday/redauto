"""Monitoring dashboard module - Flask backend"""

import asyncio
import json
import threading
from datetime import datetime
from typing import Dict, Any
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS

from data.shared_state import (
    get_db, get_online_devices,
    get_device_status, update_device_status
)
from data.websocket_server import get_status_server


app = Flask(__name__, template_folder='templates')
CORS(app)

# 设备工作流运行状态注册表 {device_id: {'task': Thread, 'test_mode': bool, 'started_at': str, 'logs': [str]}}
_running_workflows: Dict[str, Dict] = {}
_workflows_lock = threading.Lock()

# 日志缓冲区 {device_id: deque(maxlen=500)}
_log_buffers: Dict[str, Any] = {}
_logs_lock = threading.Lock()


def _log(device_id: str, msg: str):
    """向日志缓冲区追加一行"""
    with _logs_lock:
        if device_id not in _log_buffers:
            from collections import deque
            _log_buffers[device_id] = deque(maxlen=500)
        timestamp = datetime.now().strftime('%H:%M:%S')
        _log_buffers[device_id].append(f"[{timestamp}] {msg}")


def get_device_logs(device_id: str) -> list:
    """获取设备日志"""
    with _logs_lock:
        return list(_log_buffers.get(device_id, []))


def clear_device_logs(device_id: str):
    """清空设备日志"""
    with _logs_lock:
        if device_id in _log_buffers:
            _log_buffers[device_id].clear()


class DeviceLogWriter:
    """自定义 print 目标，将输出重定向到设备日志"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.original_stdout = None

    def write(self, text: str):
        if text.strip():
            _log(self.device_id, text.strip())

    def flush(self):
        pass


class LogCapture:
    """上下文管理器，临时重定向 stdout 到设备日志"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self.original_stdout = None

    def __enter__(self):
        self.original_stdout = __import__('sys').stdout
        __import__('sys').stdout = DeviceLogWriter(self.device_id)
        return self

    def __exit__(self, *args):
        __import__('sys').stdout = self.original_stdout


def get_running_workflows() -> Dict[str, Dict]:
    """获取所有运行中的工作流状态（清理已完成的线程）"""
    with _workflows_lock:
        # 清理已结束的线程
        for did in list(_running_workflows.keys()):
            wf = _running_workflows[did]
            if not wf['task'].is_alive():
                del _running_workflows[did]
        return dict(_running_workflows)


def is_workflow_running(device_id: str) -> bool:
    """检查设备是否正在运行工作流"""
    with _workflows_lock:
        wf = _running_workflows.get(device_id)
        if wf and not wf['task'].is_alive():
            del _running_workflows[device_id]
            return False
        return device_id in _running_workflows


def stop_workflow(device_id: str) -> bool:
    """停止设备的工作流 - 强制终止线程 + 杀掉残留ADB进程"""
    import ctypes
    import subprocess
    with _workflows_lock:
        if device_id not in _running_workflows:
            return False
        wf = _running_workflows[device_id]
        thread = wf['task']
        # 立即从注册表中移除，让前端知道已停止
        wf['stopping'] = True
        del _running_workflows[device_id]

    # 先等1秒看能否自然退出
    thread.join(timeout=1)
    if thread.is_alive():
        _log(device_id, "[Dashboard] 线程未自然退出，强制终止...")
        try:
            # thread.ident 就是 Windows 线程 ID，直接传给 OpenThread
            THREAD_TERMINATE = 0x0001
            hThread = ctypes.windll.kernel32.OpenThread(THREAD_TERMINATE, False, thread.ident)
            if hThread:
                ctypes.windll.kernel32.TerminateThread(hThread, 0)
                ctypes.windll.kernel32.CloseHandle(hThread)
                _log(device_id, "[Dashboard] 线程已强制终止")
            else:
                _log(device_id, f"[Dashboard] OpenThread 失败, error={ctypes.windll.kernel32.GetLastError()}")
        except Exception as e:
            _log(device_id, f"[Dashboard] 强制终止异常: {e}")

    # 杀掉该设备相关的 ADB shell 进程（不杀 adb server）
    _log(device_id, "[Dashboard] 清理残留ADB进程...")
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                name = proc.info.get('name', '') or ''
                if 'adb' not in name.lower():
                    continue
                cmdline = ' '.join(proc.info.get('cmdline', []) or [])
                # 只杀带设备ID的 shell 命令进程，不杀 adb server
                if device_id in cmdline and 'shell' in cmdline:
                    _log(device_id, f"[Dashboard] 杀掉进程: {cmdline[-100:]}")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        pass

    update_device_status(device_id, status='online')
    return True


def run_workflow_thread(device_id: str, test_mode: bool):
    """在工作线程中运行工作流（stdout重定向到设备日志）"""
    with LogCapture(device_id):
        _run_workflow_inner(device_id, test_mode)


def _run_workflow_inner(device_id: str, test_mode: bool):
    """工作流实际执行逻辑"""
    try:
        import sys
        sys.path.insert(0, '.')
        from workflow import XiaohongshuWorkflow
        workflow = XiaohongshuWorkflow(device_id, test_mode=test_mode)

        async def start_with_check():
            ctrl = workflow._get_controller()
            if not ctrl.is_connected():
                ctrl.connect()

            # 停止检查辅助函数
            def _check_stopping():
                with _workflows_lock:
                    wf = _running_workflows.get(device_id)
                    if wf and wf.get('stopping'):
                        print(f"[Workflow] 收到停止信号，退出工作流")
                        if device_id in _running_workflows:
                            del _running_workflows[device_id]
                        update_device_status(device_id, status='online')
                        return True
                return False

            await workflow._ensure_xiaohongshu_loaded()
            if _check_stopping():
                return

            loop_count = 0
            max_loops = 100
            consecutive_no_target = 0
            display = ctrl.display_info

            while loop_count < max_loops:
                loop_count += 1
                if _check_stopping():
                    return

                print(f"[Workflow] 第 {loop_count} 轮循环")

                try:
                    if loop_count == 1:
                        await workflow._ensure_discovery_page()
                    if _check_stopping():
                        return

                    if not await workflow._is_on_discovery_page():
                        print("[Workflow] 当前不在发现页，执行纠错...")
                        await workflow._ensure_discovery_page()
                    if _check_stopping():
                        return

                    await workflow._save_discovery_screenshot()
                    if _check_stopping():
                        return

                    if test_mode:
                        await workflow._random_scroll()
                        await asyncio.sleep(1)
                        import random
                        is_video = random.random() < 0.5
                        post_type = "视频" if is_video else "图文"
                        print(f"[Workflow] 测试模式：进入随机{post_type}帖子")
                        target_info = {
                            'nickname': 'test_user',
                            'is_video': is_video,
                            'post_id': f'post_test_{random.randint(1000, 9999)}',
                        }
                        consecutive_no_target = 0
                    else:
                        target_info = None
                        for scan_attempt in range(3):
                            if _check_stopping():
                                return
                            target_info = await workflow._find_target_post()
                            if target_info is not None:
                                consecutive_no_target = 0
                                break
                            print(f"[Workflow] 第{scan_attempt+1}次扫描未找到目标")
                            await workflow._random_scroll()
                            await asyncio.sleep(2)

                        if target_info is None:
                            consecutive_no_target += 1
                            print(f"[Workflow] 当前区域无目标（连续{consecutive_no_target}次）")
                            await workflow._random_scroll()
                            await asyncio.sleep(2)
                            continue

                        from workflow.daily_tracker import can_operate
                        from workflow.target_detector import get_target_users
                        nickname = target_info.get('nickname', '')
                        daily_limit = 3
                        for u in get_target_users():
                            if u.nickname == nickname:
                                daily_limit = u.daily_like_limit
                                break
                        allowed, reason = can_operate(nickname, daily_limit)
                        print(reason)
                        if not allowed:
                            await workflow._random_scroll()
                            await asyncio.sleep(2)
                            continue

                    if _check_stopping():
                        return
                    await workflow._enter_post(target_info)

                    if _check_stopping():
                        return
                    await workflow._browse_post()

                    if _check_stopping():
                        return
                    await workflow._like_and_collect()

                    from workflow.daily_tracker import increment_count
                    nickname = target_info.get('nickname', '')
                    if nickname:
                        new_count = increment_count(nickname)
                        print(f"[每日追踪] {nickname} 今日第{new_count}次")

                    if _check_stopping():
                        return
                    await workflow._save_operation_screenshot(target_info)

                    if _check_stopping():
                        return
                    await workflow._return_to_discovery()

                    if _check_stopping():
                        return
                    if not await workflow._is_on_discovery_page():
                        print("[Workflow] 返回后不在发现页，执行纠错...")
                        await workflow._ensure_discovery_page()

                    import random
                    await asyncio.sleep(random.uniform(2, 5))

                except Exception as e:
                    print(f"[Workflow] 循环异常: {e}")
                    if _check_stopping():
                        return
                    for _ in range(3):
                        ctrl.press_back()
                        await asyncio.sleep(0.5)
                    if not await workflow._is_on_discovery_page():
                        await workflow._ensure_discovery_page()
                    consecutive_no_target = 0

            print("[Workflow] 达到最大循环次数，正常退出")
            with _workflows_lock:
                if device_id in _running_workflows:
                    del _running_workflows[device_id]
            update_device_status(device_id, status='online')

        asyncio.run(start_with_check())

    except Exception as e:
        print(f"[Workflow] 工作流异常: {e}")
    finally:
        with _workflows_lock:
            if device_id in _running_workflows:
                del _running_workflows[device_id]
            update_device_status(device_id, status='online')


def get_device_statistics() -> Dict[str, Any]:
    """Get device statistics"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) as total FROM device_status")
        total = cursor.fetchone()[0]

    online = get_online_devices()
    return {
        "total": total,
        "online": len(online),
        "offline": total - len(online)
    }


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')


@app.route('/api/stats')
def stats():
    """Get overall statistics"""
    device_stats = get_device_statistics()
    return jsonify({
        "devices": device_stats,
        "timestamp": datetime.now().isoformat()
    })


@app.route('/api/devices')
def devices():
    """Get all devices"""
    db = get_db()
    with db.get_cursor() as cursor:
        cursor.execute("SELECT * FROM device_status ORDER BY last_heartbeat DESC")
        devices = [dict(row) for row in cursor.fetchall()]

    return jsonify({"devices": devices})


@app.route('/api/devices/<device_id>')
def device_detail(device_id: str):
    """Get device detail"""
    status = get_device_status(device_id)
    if not status:
        return jsonify({"error": "Device not found"}), 404
    result = dict(status)
    result['workflow_running'] = is_workflow_running(device_id)
    return jsonify(result)


@app.route('/api/devices/<device_id>/start', methods=['POST'])
def start_workflow(device_id: str):
    """启动设备工作流"""
    data = request.get_json() or {}
    test_mode = data.get('test_mode', False)

    if is_workflow_running(device_id):
        return jsonify({"error": "工作流已在运行中"}), 400

    # 检查设备是否在线
    status = get_device_status(device_id)
    if not status or status.get('status') != 'online':
        return jsonify({"error": "设备未在线"}), 400

    # 更新设备状态为 running
    update_device_status(device_id, status='running')

    # 启动工作流线程
    thread = threading.Thread(target=run_workflow_thread, args=(device_id, test_mode), daemon=True)
    with _workflows_lock:
        _running_workflows[device_id] = {
            'task': thread,
            'test_mode': test_mode,
            'started_at': datetime.now().isoformat(),
            'stopping': False,
        }
    thread.start()

    mode_str = "测试模式" if test_mode else "正式模式"
    return jsonify({"success": True, "message": f"已在{mode_str}下启动工作流"})


@app.route('/api/devices/<device_id>/stop', methods=['POST'])
def stop_workflow_endpoint(device_id: str):
    """停止设备工作流"""
    if not is_workflow_running(device_id):
        return jsonify({"error": "没有运行中的工作流"}), 400

    _log(device_id, "[Dashboard] 收到停止信号")
    result = stop_workflow(device_id)
    if result:
        return jsonify({"success": True, "message": "工作流已停止"})
    return jsonify({"error": "停止失败"}), 500


@app.route('/api/workflows')
def list_workflows():
    """列出所有运行中的工作流"""
    workflows = get_running_workflows()
    result = {}
    for did, wf in workflows.items():
        result[did] = {
            'test_mode': wf.get('test_mode', False),
            'started_at': wf.get('started_at', ''),
            'stopping': wf.get('stopping', False),
        }
    return jsonify({"workflows": result})


@app.route('/api/devices/<device_id>/logs')
def device_logs(device_id: str):
    """获取设备运行日志"""
    logs = get_device_logs(device_id)
    return jsonify({"logs": logs})


@app.route('/api/devices/<device_id>/logs/clear', methods=['POST'])
def clear_device_logs_endpoint(device_id: str):
    """清空设备运行日志"""
    clear_device_logs(device_id)
    return jsonify({"success": True})


@app.route('/api/reports')
def reports():
    """Get historical reports"""
    # TODO: List reports from storage
    return jsonify({"reports": []})


@app.route('/api/health')
def health():
    """Health check"""
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


async def run_websocket_server():
    """Run WebSocket server in background"""
    server = get_status_server()
    await server.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        await server.stop()


def start_dashboard(host: str = "127.0.0.1", port: int = 8080):
    """Start the dashboard server"""
    from threading import Thread
    from data.shared_state import update_device_status

    # 初始化设备状态：扫描 ADB 设备并写入 device_status
    def _init_device_status():
        try:
            from device_manager.controller import list_connected_devices
            devices = list_connected_devices()
            connected = set(devices)

            # 更新在线设备
            for d in devices:
                update_device_status(device_id=d, status='online', device_name=d)

            # 将已断开连接的设备标记为 offline
            from data.shared_state import get_db
            db = get_db()
            with db.get_cursor() as cursor:
                cursor.execute("SELECT device_id FROM device_status WHERE status IN ('online', 'running')")
                db_ids = [row['device_id'] for row in cursor.fetchall()]
                for did in db_ids:
                    if did not in connected:
                        cursor.execute("UPDATE device_status SET status='offline' WHERE device_id=?", (did,))

            print(f"[Dashboard] 设备状态已刷新: {len(devices)} 台设备在线")
        except Exception as e:
            print(f"[Dashboard] 设备状态刷新失败: {e}")

    _init_device_status()

    # 定期刷新设备状态
    def _refresh_devices_loop():
        while True:
            try:
                _init_device_status()
            except Exception:
                pass
            import time
            time.sleep(15)

    Thread(target=_refresh_devices_loop, daemon=True).start()

    # Start WebSocket server in background thread
    def run_ws():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_websocket_server())

    ws_thread = Thread(target=run_ws, daemon=True)
    ws_thread.start()

    # Run Flask app
    app.run(host=host, port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    start_dashboard()
