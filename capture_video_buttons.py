"""截取视频详情页的按钮区域"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import io
from device_manager.controller import list_connected_devices, get_device_controller

async def main():
    devices = list_connected_devices()
    if not devices:
        print("没有找到设备")
        return

    ctrl = get_device_controller(devices[0])
    display = ctrl.display_info
    print(f"设备: {devices[0]}, 分辨率: {display.width}x{display.height}")

    print("请手动打开一个视频帖子，然后按回车继续...")
    input()

    # 截图
    screenshot_bytes = ctrl.take_screenshot()
    img = Image.open(io.BytesIO(screenshot_bytes))

    # 保存完整截图
    img.save("debug_steps/video_full_page.png")
    print("已保存完整视频页面截图: debug_steps/video_full_page.png")

    # 裁剪底部按钮区域（底部10%）
    bottom_h = int(display.height * 0.1)
    bottom_region = img.crop((0, display.height - bottom_h, display.width, display.height))
    bottom_region.save("debug_steps/video_buttons_region.png")
    print(f"已保存底部按钮区域截图: debug_steps/video_buttons_region.png (尺寸 {display.width}x{bottom_h})")

    print("\n截图完成！请查看 debug_steps/video_buttons_region.png，提供对应的点赞和收藏按钮模板。")

if __name__ == "__main__":
    asyncio.run(main())
