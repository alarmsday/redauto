"""
小红书自动化工作流正式运行脚本
功能：发现页自动浏览帖子，找到目标用户后进入详情，浏览内容，点赞收藏，返回
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow import XiaohongshuWorkflow

async def main():
    print("=" * 60)
    print("小红书自动化工作流 v2.0")
    print("=" * 60)
    print("功能说明：")
    print("1. 自动检测小红书是否在前台，未启动则自动打开")
    print("2. 浏览发现页帖子，自动识别目标用户（当前测试模式随机进入）")
    print("3. 进入帖子详情后自动判断是视频还是图文")
    print("4. 图文：滑动浏览到最后一张图片")
    print("5. 视频：拖动进度条到2/3位置，模拟观看")
    print("6. 自动点赞+收藏帖子")
    print("7. 自动返回发现页，继续下一个循环")
    print("=" * 60)

    # 初始化工作流，测试模式开启（随机进入帖子）
    workflow = XiaohongshuWorkflow(
        device_id="A4RYVB3A20000913",  # 你的设备ID
        test_mode=True
    )

    print("\n启动工作流...")
    try:
        await workflow.start()
    except KeyboardInterrupt:
        print("\n用户手动停止工作流")
    except Exception as e:
        print(f"\n工作流异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
