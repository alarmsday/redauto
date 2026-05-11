"""Debug 3: 视频帖子详情 - 已在详情页，检测类型、浏览视频、点赞、收藏"""
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

        # 1. 检测视频特征：底部操作栏（点赞/收藏/评论图标）
        # 视频帖底部有深色操作栏，包含心形、星形、气泡图标
        bottom_region = img_np[int(h*0.90):, :]
        bottom_gray = cv2.cvtColor(bottom_region, cv2.COLOR_RGB2GRAY)

        # 底部操作栏通常是半透明黑色背景
        avg_bottom = np.mean(bottom_gray)
        if avg_bottom < 80:
            # 底部很暗，检测白色图标（心形、星形、数字）
            _, icon_thresh = cv2.threshold(bottom_gray, 200, 255, cv2.THRESH_BINARY)
            icon_pixels = np.count_nonzero(icon_thresh)
            icon_ratio = icon_pixels / icon_thresh.size
            if icon_ratio > 0.005:
                print(f"检测为视频（底部操作栏，暗区亮度={int(avg_bottom)}，图标占比={icon_ratio:.3f}）")
                return "video"

        # 2. 检测图文特征：页面指示圆点
        dot_y_start = int(h * 0.55)
        dot_y_end = int(h * 0.65)
        dot_x_start = int(w * 0.3)
        dot_x_end = int(w * 0.7)
        dot_region = gray[dot_y_start:dot_y_end, dot_x_start:dot_x_end]
        _, dot_thresh = cv2.threshold(dot_region, 200, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(dot_thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        dot_count = 0
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if 5 < area < 100:
                x, y, cw, ch = cv2.boundingRect(cnt)
                aspect = cw / ch if ch > 0 else 0
                if 0.5 < aspect < 1.5:
                    dot_count += 1
        if dot_count >= 2:
            print(f"检测为图文（发现{dot_count}个页面指示圆点）")
            return "image"

        # 3. 全屏黑边 → 图文
        top_5pct = img_np[:int(h*0.05), :]
        bottom_5pct = img_np[int(h*0.95):, :]
        if np.mean(top_5pct) < 20 and np.mean(bottom_5pct) < 20:
            print("检测为图文（全屏模式，上下黑边）")
            return "image"

        print("检测为图文（兜底）")
        return "image"
    except Exception as e:
        print(f"帖子类型检测失败: {e}")
        return "image"

async def click_button_by_template(ctrl, button_type: str) -> bool:
    """模板匹配点击按钮"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io
        import os

        screenshot_bytes = ctrl.take_screenshot()
        if not screenshot_bytes:
            return False

        img = Image.open(io.BytesIO(screenshot_bytes))
        screenshot = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        sh, sw = screenshot.shape[:2]

        # 只在底部20%区域匹配（操作栏位置）
        roi_y = int(sh * 0.80)
        roi = screenshot[roi_y:, :]
        roi_h, roi_w = roi.shape[:2]

        template_candidates = {
            "like": ["templates/video_like.png", "templates/like_button.png"],
            "collect": ["templates/video_collect.png", "templates/collect_button.png"],
        }

        templates = template_candidates.get(button_type, [])
        best_score = 0
        best_center = (0, 0)

        for template_path in templates:
            if not os.path.exists(template_path):
                continue
            template = cv2.imread(template_path)
            if template is None:
                continue

            scales = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2, 1.5]
            for scale in scales:
                tw = int(template.shape[1] * scale)
                th = int(template.shape[0] * scale)
                if tw <= 0 or th <= 0 or tw > roi_w or th > roi_h:
                    continue

                scaled_template = cv2.resize(template, (tw, th))
                roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                t_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)
                result = cv2.matchTemplate(roi_gray, t_gray, cv2.TM_CCOEFF_NORMED)
                current_max = np.max(result)

                if current_max > best_score and current_max > 0.6:
                    max_loc = np.unravel_index(np.argmax(result), result.shape)
                    x, y = max_loc[1], max_loc[0]
                    center_x = int(x + tw // 2)
                    center_y = roi_y + int(y + th // 2)
                    if center_x < sw and center_y < sh:
                        best_score = current_max
                        best_center = (center_x, center_y)

        if best_score >= 0.6:
            ctrl.click(best_center[0], best_center[1])
            print(f"  {button_type}: 模板匹配成功 ({best_center[0]}, {best_center[1]}, 匹配度 {best_score:.3f})")
            return True
        else:
            print(f"  {button_type}: 模板匹配失败，最高分={best_score:.3f}")
            return False
    except Exception as e:
        print(f"  {button_type}: 模板匹配异常: {e}")
        return False

async def main():
    os.makedirs('debug_steps', exist_ok=True)

    ctrl = get_device_controller(DEVICE_ID)
    if not ctrl.is_connected():
        ctrl.connect()

    display = ctrl.display_info
    print(f"设备: {DEVICE_ID}, 分辨率: {display.width}x{display.height}")

    # 1. 检测帖子类型
    print("\n[步骤1] 检测帖子类型...")
    screenshot = ctrl.take_screenshot()
    save_screenshot(screenshot, "debug_steps/video_1_type_detect.png")
    post_type = detect_post_type(screenshot)

    if post_type != "video":
        print(f"  警告: 当前不是视频帖子（检测为{post_type}），请手动进入视频帖后重新运行")
        return

    # 2. 浏览视频
    print("\n[步骤2] 浏览视频...")
    center_x = display.width // 2
    center_y = int(display.height * 0.5)

    # 拖动进度条到2/3位置
    bar_y = int(display.height * 0.9)
    bar_start_x = int(display.width * 0.1)
    bar_end_x = int(display.width * 0.9)
    target_x = int(bar_start_x + (bar_end_x - bar_start_x) * 0.66)
    print(f"  拖动进度条: ({bar_start_x}, {bar_y}) -> ({target_x}, {bar_y})")
    ctrl.swipe(bar_start_x, bar_y, target_x, bar_y, 500)
    await asyncio.sleep(1)

    watch_time = random.randint(3, 5)
    print(f"  观看视频 {watch_time} 秒...")
    await asyncio.sleep(watch_time)

    save_screenshot(ctrl.take_screenshot(), "debug_steps/video_3_after_watch.png")

    # 3. 点赞
    print("\n[步骤3] 点赞...")
    success = await click_button_by_template(ctrl, "like")
    if not success:
        like_x = int(display.width * 0.72)
        like_y = int(display.height * 0.93)
        ctrl.click(like_x, like_y)
        print(f"  使用坐标点赞 ({like_x}, {like_y})")
    save_screenshot(ctrl.take_screenshot(), "debug_steps/video_4_after_like.png")

    # 4. 收藏
    print("\n[步骤4] 收藏...")
    await asyncio.sleep(0.5)
    success = await click_button_by_template(ctrl, "collect")
    if not success:
        collect_x = int(display.width * 0.82)
        collect_y = int(display.height * 0.93)
        ctrl.click(collect_x, collect_y)
        print(f"  使用坐标收藏 ({collect_x}, {collect_y})")
    save_screenshot(ctrl.take_screenshot(), "debug_steps/video_5_after_collect.png")

    # 5. 返回
    print("\n[步骤5] 返回发现页...")
    ctrl.press_back()
    await asyncio.sleep(2)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/video_6_after_back.png")
    print("  已返回")

    print("\n完成！检查 debug_steps/video_*.png")

if __name__ == "__main__":
    asyncio.run(main())
