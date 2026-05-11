"""Debug 2: 图文帖子详情 - 已在详情页，检测类型、滑动到最后、点赞、收藏"""
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

        # 1. 检测视频特征：底部操作栏
        bottom_region = img_np[int(h*0.90):, :]
        bottom_gray = cv2.cvtColor(bottom_region, cv2.COLOR_RGB2GRAY)
        avg_bottom = np.mean(bottom_gray)
        if avg_bottom < 80:
            _, icon_thresh = cv2.threshold(bottom_gray, 200, 255, cv2.THRESH_BINARY)
            icon_ratio = np.count_nonzero(icon_thresh) / icon_thresh.size
            if icon_ratio > 0.005:
                print(f"检测为视频（底部操作栏）")
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
        if np.mean(img_np[:int(h*0.05), :]) < 20 and np.mean(img_np[int(h*0.95):, :]) < 20:
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

        template_candidates = {
            "like": ["templates/like_button.png", "templates/video_like.png"],
            "collect": ["templates/collect_button.png", "templates/video_collect.png"],
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

            scales = [0.35, 0.4, 0.45, 0.5, 1.0]
            for scale in scales:
                tw = int(template.shape[1] * scale)
                th = int(template.shape[0] * scale)
                if tw <= 0 or th <= 0:
                    continue

                scaled_template = cv2.resize(template, (tw, th))
                s_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                t_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)
                result = cv2.matchTemplate(s_gray, t_gray, cv2.TM_CCOEFF_NORMED)
                current_max = np.max(result)

                if current_max > best_score and current_max > 0.6:
                    max_loc = np.unravel_index(np.argmax(result), result.shape)
                    x, y = max_loc[1], max_loc[0]
                    center_x = int(x + tw // 2)
                    center_y = int(y + th // 2)
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

def scroll_left(ctrl, display):
    """向左滑动翻阅图片"""
    start_x = int(display.width * 0.8)
    end_x = int(display.width * 0.2)
    center_y = display.height // 2
    ctrl.swipe(start_x, center_y, end_x, center_y, 300)

def count_pages(screenshot_bytes: bytes) -> int:
    """从右上角页码标识计数图片张数，检测失败返回10（兜底）"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]

        # 截取右上区域（跳过状态栏）
        corner = img_np[int(h*0.06):int(h*0.2), int(w*0.75):]

        # 用easyocr识别 "X/N"
        try:
            import easyocr
            reader = easyocr.Reader(['en', 'ch_sim'], gpu=False, verbose=False)
            result = reader.readtext(corner, detail=0)
            for text in result:
                if '/' in text:
                    parts = text.replace(' ', '').split('/')
                    for part in parts:
                        if part.isdigit():
                            n = int(part)
                            if 1 <= n <= 20:
                                print(f"  OCR识别到 {n} 张")
                                return n
        except Exception:
            pass

    except Exception as e:
        print(f"  页面计数失败: {e}")
    return 10  # 兜底10张

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
    save_screenshot(screenshot, "debug_steps/image_1_type_detect.png")
    post_type = detect_post_type(screenshot)

    if post_type != "image":
        print(f"  警告: 当前不是图文帖子（检测为{post_type}），请手动进入图文帖后重新运行")
        return

    # 2. 检测图片张数
    print("\n[步骤2] 检测图片张数...")
    page_count = count_pages(screenshot)
    print(f"  图片张数: {page_count}（兜底=10）")

    # 3. 浏览图片（左滑到最后一张）
    print("\n[步骤3] 浏览图片...")
    await asyncio.sleep(random.uniform(1, 2))

    # 已经在第1张，需要左滑 page_count - 1 次到达最后
    swipe_times = page_count - 1
    print(f"  需滑动 {swipe_times} 次")

    for i in range(swipe_times):
        scroll_left(ctrl, display)
        await asyncio.sleep(1)
        save_screenshot(ctrl.take_screenshot(), f"debug_steps/image_3_swipe_{i+1}.png")
        print(f"  第{i+1}次滑动")
        if i < swipe_times - 1:
            await asyncio.sleep(random.uniform(0.5, 1.5))

    save_screenshot(ctrl.take_screenshot(), "debug_steps/image_4_after_browse.png")

    # 4. 点赞
    print("\n[步骤4] 点赞...")
    success = await click_button_by_template(ctrl, "like")
    if not success:
        like_x = int(display.width * 0.72)
        like_y = int(display.height * 0.93)
        ctrl.click(like_x, like_y)
        print(f"  使用坐标点赞 ({like_x}, {like_y})")
    save_screenshot(ctrl.take_screenshot(), "debug_steps/image_5_after_like.png")

    # 5. 收藏
    print("\n[步骤5] 收藏...")
    await asyncio.sleep(0.5)
    success = await click_button_by_template(ctrl, "collect")
    if not success:
        collect_x = int(display.width * 0.82)
        collect_y = int(display.height * 0.93)
        ctrl.click(collect_x, collect_y)
        print(f"  使用坐标收藏 ({collect_x}, {collect_y})")
    save_screenshot(ctrl.take_screenshot(), "debug_steps/image_6_after_collect.png")

    # 6. 返回
    print("\n[步骤6] 返回发现页...")
    ctrl.press_back()
    await asyncio.sleep(2)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/image_7_after_back.png")
    print("  已返回")

    print("\n完成！检查 debug_steps/image_*.png")

if __name__ == "__main__":
    asyncio.run(main())
