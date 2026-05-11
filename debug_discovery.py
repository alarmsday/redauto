"""Debug 1: 发现页 → 进入帖子详情 → 返回"""
import asyncio
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from device_manager.controller import list_connected_devices, get_device_controller

DEVICE_ID = 'NABDU20330005550'

def save_screenshot(screenshot_bytes: bytes, path: str):
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(screenshot_bytes))
    img.save(path)

def detect_post_type(screenshot_bytes: bytes) -> str:
    """检测帖子类型，返回 'video' 或 'image'"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]
        gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

        bar_y_start = int(h * 0.93)
        bar_y_end = int(h * 0.97)
        bar_region = gray[bar_y_start:bar_y_end, :]
        _, bar_thresh = cv2.threshold(bar_region, 180, 255, cv2.THRESH_BINARY)
        for row in range(bar_thresh.shape[0]):
            line = bar_thresh[row]
            transitions = np.where(line[:-1] != line[1:])[0]
            if len(transitions) >= 2:
                for i in range(0, len(transitions)-1, 2):
                    if transitions[i+1] - transitions[i] > w * 0.3:
                        return "video"

        dot_y_start = int(h * 0.85)
        dot_y_end = int(h * 0.92)
        dot_x_start = int(w * 0.25)
        dot_x_end = int(w * 0.75)
        dot_region = gray[dot_y_start:dot_y_end, dot_x_start:dot_x_end]
        _, dot_thresh = cv2.threshold(dot_region, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(dot_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dot_count = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 10 < area < 200:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / ch if ch > 0 else 0
                if 0.5 < aspect < 1.5:
                    dot_count += 1
        if dot_count >= 2:
            return "image"

        if np.mean(img_np[:int(h*0.05), :]) < 20 and np.mean(img_np[int(h*0.95):, :]) < 20:
            return "image"

        return "image"
    except Exception as e:
        print(f"帖子类型检测失败: {e}")
        return "image"

async def main():
    os.makedirs('debug_steps', exist_ok=True)

    ctrl = get_device_controller(DEVICE_ID)
    if not ctrl.is_connected():
        ctrl.connect()

    display = ctrl.display_info
    print(f"设备: {DEVICE_ID}, 分辨率: {display.width}x{display.height}")

    # 1. 确保小红书已打开
    if not ctrl.is_app_running():
        print("[1] 小红书未运行，启动中...")
        ctrl.start_xiaohongshu()
        await asyncio.sleep(5)
    else:
        print("[1] 小红书已在运行")

    # 2. 验证APP加载
    for i in range(5):
        screenshot = ctrl.take_screenshot()
        if screenshot and len(screenshot) > 10000:
            print(f"[2] APP加载成功 (尝试{i+1}次)")
            break
        print(f"[2] 等待APP加载... ({i+1}/5)")
        await asyncio.sleep(2)

    # 3. 截图确认当前页面
    save_screenshot(ctrl.take_screenshot(), "debug_steps/discovery_1_initial.png")
    print("[3] 初始页面截图已保存")

    # 4. 确保在发现页 - 点击顶部"发现"Tab
    print("[4] 切换到发现页...")
    ctrl.click_by_text("发现")
    await asyncio.sleep(2)

    # 5. 截图确认切换到发现页
    save_screenshot(ctrl.take_screenshot(), "debug_steps/discovery_2_discovery_tab.png")
    print("[5] 发现页截图已保存")

    # 6. 下滑刷新（手指从下往上滑 = 浏览新内容）
    center_x = display.width // 2
    start_y = int(display.height * 0.75)
    end_y = int(display.height * 0.25)
    ctrl.swipe(center_x, start_y, center_x, end_y, 300)
    await asyncio.sleep(2)

    # 7. 截图确认下滑后
    save_screenshot(ctrl.take_screenshot(), "debug_steps/discovery_3_after_scroll.png")
    print("[7] 下滑后截图已保存")

    # 8. 随机点击进入帖子详情
    print("\n[8] 进入帖子详情...")
    click_x = random.randint(100, int(display.width * 0.9))
    click_y = random.randint(int(display.height * 0.15), int(display.height * 0.75))
    print(f"  点击坐标: ({click_x}, {click_y})")
    ctrl.click(click_x, click_y)
    await asyncio.sleep(3)

    save_screenshot(ctrl.take_screenshot(), "debug_steps/discovery_4_post_detail.png")
    print("[8] 帖子详情页截图已保存")

    # 9. 检测帖子类型
    print("\n[9] 检测帖子类型...")
    post_type = detect_post_type(ctrl.take_screenshot())
    print(f"  检测结果: {post_type}")

    # 10. 返回发现页
    print("\n[10] 返回发现页...")
    ctrl.press_back()
    await asyncio.sleep(2)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/discovery_5_after_back.png")
    print("[10] 返回后截图已保存")

    print("\n完成！检查 debug_steps/discovery_*.png")

if __name__ == "__main__":
    asyncio.run(main())
