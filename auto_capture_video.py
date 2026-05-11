"""自动找视频帖子并截图按钮区域"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
import io
import numpy as np
from device_manager.controller import list_connected_devices, get_device_controller

def is_video_post(screenshot_bytes: bytes) -> bool:
    """判断是不是视频帖子"""
    try:
        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]
        bottom_region = img_np[int(h*0.85):, :]
        avg_brightness = np.mean(bottom_region)
        return avg_brightness < 100
    except:
        return False

async def main():
    devices = list_connected_devices()
    if not devices:
        print("没有找到设备")
        return

    ctrl = get_device_controller(devices[0])
    display = ctrl.display_info
    print(f"设备: {devices[0]}, 分辨率: {display.width}x{display.height}")

    # 确保在小红书发现页
    print("返回发现页...")
    for _ in range(3):
        ctrl.press_back()
        await asyncio.sleep(0.5)
    ctrl.click(600, 2500)  # 点击首页tab
    await asyncio.sleep(2)

    print("寻找视频帖子...")
    for attempt in range(5):
        # 进入帖子
        click_x = int(display.width * 0.75)
        click_y = int(display.height * 0.38)
        print(f"  进入帖子 ({click_x}, {click_y})")
        ctrl.click(click_x, click_y)
        await asyncio.sleep(3)

        # 判断是不是视频
        screenshot = ctrl.take_screenshot()
        if is_video_post(screenshot):
            print("✅ 找到视频帖子！")
            break
        else:
            print("❌ 图文帖子，返回...")
            ctrl.press_back()
            await asyncio.sleep(1)
            # 向上滑动
            ctrl.swipe(600, 2000, 600, 500, 500)
            await asyncio.sleep(1)
    else:
        print("❌ 没找到视频帖子，请手动打开后重新运行")
        return

    # 点击视频显示按钮
    print("点击视频唤醒控制栏...")
    ctrl.click(600, 1200)
    await asyncio.sleep(1)

    # 截图
    screenshot_bytes = ctrl.take_screenshot()
    img = Image.open(io.BytesIO(screenshot_bytes))

    # 保存完整截图
    img.save("debug_steps/video_full_page.png")
    print("已保存完整截图: debug_steps/video_full_page.png")

    # 裁剪底部按钮区域
    bottom_h = int(display.height * 0.12)
    bottom_region = img.crop((0, display.height - bottom_h, display.width, display.height))
    bottom_region.save("debug_steps/video_buttons_region.png")
    print(f"已保存底部按钮区域: debug_steps/video_buttons_region.png (尺寸 {display.width}x{bottom_h})")

    print("\n截图完成！请查看 debug_steps/video_buttons_region.png，提供对应的按钮模板。")

if __name__ == "__main__":
    asyncio.run(main())
