"""Main entry point for Xiaohongshu automation system"""

import asyncio
import argparse
import signal
import sys
import os

# 设置工作目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_running = False


def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global _running
    print("\n正在关闭...")
    _running = False


async def initialize_system():
    """初始化系统组件"""
    from data.shared_state import get_db
    from device_manager.controller import list_connected_devices, get_device_controller

    # 初始化数据库
    db = get_db()
    print("[系统] 数据库初始化完成")

    # 扫描设备
    devices = list_connected_devices()
    if devices:
        print(f"[系统] 发现 {len(devices)} 个设备: {devices}")
        # 连接第一个设备
        ctrl = get_device_controller(devices[0])
        if ctrl.is_connected():
            print(f"[系统] 设备 {devices[0]} 已连接，分辨率: {ctrl.display_info.width}x{ctrl.display_info.height}")
    else:
        print("[系统] 未发现已连接设备")

    # 测试LLM
    from ai_agent.llm_client import test_llm_connection
    await test_llm_connection()

    return devices


async def run_single_device(device_id: str = None, test_mode: bool = False):
    """运行单设备工作流"""
    from workflow import XiaohongshuWorkflow
    from device_manager.controller import list_connected_devices

    if device_id is None:
        devices = list_connected_devices()
        if not devices:
            print("[错误] 未发现已连接设备")
            return
        device_id = devices[0]

    mode_str = "测试模式" if test_mode else "正常模式"
    print(f"[单设备模式] 启动设备 {device_id} ({mode_str})")

    workflow = XiaohongshuWorkflow(device_id, test_mode=test_mode)
    await workflow.start()


async def run_scheduler():
    """运行任务调度器"""
    from task_scheduler import get_scheduler

    print("[调度器模式] 启动任务调度器")
    scheduler = get_scheduler()
    await scheduler.start()


async def run_dashboard(host: str, port: int):
    """运行监控面板"""
    from dashboard import start_dashboard

    print(f"[监控面板] 启动 Dashboard http://{host}:{port}")
    start_dashboard(host, port)


async def main_async(args):
    """异步主函数"""
    global _running

    # 初始化
    devices = await initialize_system()

    if args.mode == "init":
        # 仅初始化，不运行
        print("[完成] 系统初始化完成")
        return

    elif args.mode == "device":
        # 运行单设备
        await run_single_device(args.device, args.test)

    elif args.mode == "dashboard":
        # 仅运行监控面板
        await run_dashboard(args.host, args.port)

    elif args.mode == "scheduler":
        # 仅运行调度器
        await run_scheduler()

    elif args.mode == "all":
        # 运行完整系统
        _running = True

        # 启动调度器和监控面板
        dashboard_task = asyncio.create_task(run_dashboard(args.host, args.port))
        scheduler_task = asyncio.create_task(run_scheduler())
        device_task = asyncio.create_task(run_single_device(args.device, args.test))

        while _running:
            await asyncio.sleep(1)

        # 清理
        scheduler_task.cancel()
        dashboard_task.cancel()
        device_task.cancel()


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        description="小红书多设备自动化运营系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py init                      # 仅初始化系统
  python main.py device                    # 运行单设备（自动选择第一个设备）
  python main.py device --device DEVICE_ID # 运行指定设备
  python main.py dashboard                 # 仅启动监控面板
  python main.py scheduler                 # 仅启动调度器
  python main.py all                        # 运行完整系统
        """
    )

    parser.add_argument(
        "mode",
        choices=["init", "device", "dashboard", "scheduler", "all"],
        default="init",
        help="运行模式"
    )

    parser.add_argument(
        "--device",
        help="设备ID (用于device或all模式)"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="测试模式：随机进入帖子测试点赞收藏流程"
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Dashboard主机地址 (默认: 0.0.0.0)"
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Dashboard端口 (默认: 8080)"
    )

    args = parser.parse_args()

    # 设置信号处理器
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("\n已中断")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
