"""Debug full flow: enter post → browse → like → collect → back"""
import asyncio
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from device_manager.controller import list_connected_devices, get_device_controller

def save_screenshot(screenshot_bytes: bytes, path: str):
    """Save screenshot bytes to file"""
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(screenshot_bytes))
    img.save(path)

async def main():
    devices = list_connected_devices()
    if not devices:
        print("No devices found")
        return

    ctrl = get_device_controller(devices[0])
    display = ctrl.display_info
    print(f"Device: {devices[0]}, Resolution: {display.width}x{display.height}")

    # 1. Ensure Xiaohongshu is open
    if not ctrl.is_app_running():
        print("Xiaohongshu not running, launching...")
        ctrl.start_xiaohongshu()
        await asyncio.sleep(5)
    else:
        try:
            current_focus = ctrl._device.adb.shell("dumpsys window | grep mCurrentFocus")
            if "com.xingin.xhs" not in current_focus:
                print("Xiaohongshu in background, bringing to front...")
                ctrl.start_xiaohongshu()
                await asyncio.sleep(3)
        except Exception as e:
            print(f"Could not check foreground: {e}")

    # Wait for app to load
    for i in range(5):
        screenshot = ctrl.take_screenshot()
        if screenshot and len(screenshot) > 10000:
            break
        await asyncio.sleep(2)

    # Step 0: Initial (discovery page)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/flow_0_discovery.png")
    print("Step 0: Discovery page")

    # Step 1: Enter post (click right column)
    click_x = int(display.width * 0.75)
    click_y = int(display.height * 0.38)
    print(f"Clicking post at ({click_x}, {click_y})")
    ctrl.click(click_x, click_y)
    await asyncio.sleep(3)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/flow_1_post_detail.png")
    print("Step 1: Post detail opened")

    # Step 2: Analyze current post
    screenshot = ctrl.take_screenshot()
    is_video, total_images = analyze_post(screenshot)
    print(f"Post analysis: is_video={is_video}, total_images={total_images}")

    # Step 3: Browse content
    if is_video:
        await browse_video(ctrl, display)
    else:
        await browse_images(ctrl, display, total_images)

    save_screenshot(ctrl.take_screenshot(), "debug_steps/flow_2_after_browse.png")
    print("Step 2: After browsing")

    # Step 4: Like
    await like_post(ctrl, display)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/flow_3_after_like.png")
    print("Step 3: After like")

    # Step 5: Collect
    await collect_post(ctrl, display)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/flow_4_after_collect.png")
    print("Step 4: After collect")

    # Step 6: Return to discovery
    ctrl.press_back()
    await asyncio.sleep(2)
    save_screenshot(ctrl.take_screenshot(), "debug_steps/flow_5_after_back.png")
    print("Step 5: Back to discovery")

    print("\nDone! Check debug_steps/flow_*.png")


def detect_post_type(screenshot_bytes: bytes) -> str:
    """检测帖子类型，返回 'video' 或 'image'"""
    try:
        import cv2
        import numpy as np
        from PIL import Image
        import io

        if not screenshot_bytes:
            return "image"  # 默认按图文处理

        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]

        # 方法1：检测底部是否有视频控制栏（半透明深色条）
        # 截取底部12%的区域
        bottom_region = img_np[int(h*0.88):, :]
        avg_brightness = np.mean(bottom_region)

        # 视频控制栏通常比较暗，亮度低于120
        if avg_brightness < 120:
            print(f"检测为视频帖子（底部控制栏亮度={int(avg_brightness)}）")
            return "video"

        # 方法2：检测右上角是否有视频时长标签（红色或白色的时间标签）
        top_right = img_np[int(h*0.02):int(h*0.08), int(w*0.85):]
        avg_red = np.mean(top_right[:, :, 0])
        avg_green = np.mean(top_right[:, :, 1])
        avg_blue = np.mean(top_right[:, :, 2])

        # 时间标签通常是红色背景白色文字，红色通道值高
        if avg_red > avg_green + 20 and avg_red > avg_blue + 20:
            print(f"检测为视频帖子（右上角红色时长标签）")
            return "video"

        print(f"检测为图文帖子（底部亮度={int(avg_brightness)}）")
        return "image"

    except Exception as e:
        print(f"帖子类型检测失败，默认按图文处理: {e}")
        return "image"


def analyze_post(screenshot: bytes) -> tuple:
    """
    Analyze if the post is a video or image, and count images

    Returns:
        (is_video, total_images)
    """
    post_type = detect_post_type(screenshot)
    is_video = (post_type == "video")
    # 图片数量暂时不检测，由browse_images自动判断最后一页
    return is_video, None


async def browse_images(ctrl, display, total_images=None):
    """Browse image post - swipe to the last image (优化速度版)"""
    browse_time = random.uniform(0.5, 1.5)  # 第一张浏览时间从2-5s改成0.5-1.5s
    await asyncio.sleep(browse_time)

    max_swipes = 4  # 最多滑4次就够了
    for i in range(max_swipes):
        scroll_left(ctrl, display)
        await asyncio.sleep(0.8)  # 滑动后等待时间从1s改成0.8s

        screenshot = ctrl.take_screenshot()
        is_last = detect_last_image(screenshot)
        if is_last:
            print(f"Reached last image after {i+1} swipes")
            break

        await asyncio.sleep(random.uniform(0.5, 1.5))  # 浏览时间从2-5s改成0.5-1.5s


def detect_last_image(screenshot: bytes) -> bool:
    """
    Detect if we're at the last image by checking the page indicator

    The page indicator on Xiaohongshu typically shows:
    - "1/3" for 3-image posts
    - "2/4" for 4-image posts
    - Or a series of dots with the current one highlighted

    For now, use a simple heuristic and let the max_swipes limit prevent issues
    """
    # TODO: Implement OCR-based detection
    # For now, return False to rely on max_swipes limit
    return False


async def browse_video(ctrl, display):
    """Browse video post - seek to 2/3 position and watch briefly"""
    center_x = display.width // 2
    center_y = int(display.height * 0.5)
    ctrl.click(center_x, center_y)
    await asyncio.sleep(1)

    bar_y = int(display.height * 0.9)
    bar_start_x = int(display.width * 0.1)
    bar_end_x = int(display.width * 0.9)
    target_x = int(bar_start_x + (bar_end_x - bar_start_x) * 0.66)

    print(f"Seeking video to 2/3 position: ({target_x}, {bar_y})")
    ctrl.swipe(bar_start_x, bar_y, target_x, bar_y, 500)
    await asyncio.sleep(1)
    await asyncio.sleep(random.randint(3, 5))


async def like_post(ctrl, display):
    """Click like button using template matching"""
    success = await click_button_by_template(ctrl, "like")
    if success:
        print("Liked post (template match)")
    else:
        like_x = int(display.width * 0.72)
        like_y = int(display.height * 0.93)
        ctrl.click(like_x, like_y)
        print(f"Liked post (fallback {like_x}, {like_y})")
    await asyncio.sleep(0.5)


async def collect_post(ctrl, display):
    """Click collect/favorite button using template matching"""
    success = await click_button_by_template(ctrl, "collect")
    if success:
        print("Collected post (template match)")
    else:
        collect_x = int(display.width * 0.82)
        collect_y = int(display.height * 0.93)
        ctrl.click(collect_x, collect_y)
        print(f"Collected post (fallback {collect_x}, {collect_y})")
    await asyncio.sleep(0.5)


async def click_button_by_template(ctrl, button_type: str) -> bool:
    """Click button using image template matching (support both image and video templates)"""
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

        # 支持图文和视频两种模板，优先匹配视频模板
        template_candidates = {
            "like": [
                "templates/video_like.png",    # 视频点赞模板
                "templates/like_button.png"           # 图文点赞模板
            ],
            "collect": [
                "templates/video_collect.png", # 视频收藏模板
                "templates/collect_button.png"        # 图文收藏模板
            ],
            "comment": [
                "templates/common_button.png"         # 评论模板
            ]
        }

        templates = template_candidates.get(button_type, [])
        if not templates:
            return False

        best_score = 0
        best_center = (0, 0)
        best_template = ""

        # 尝试所有候选模板和多种缩放比例
        for template_path in templates:
            if not os.path.exists(template_path):
                continue

            template = cv2.imread(template_path)
            if template is None:
                continue

            # 多尺度匹配：尝试不同缩放比例适配不同场景
            scales = [0.35, 0.4, 0.45, 0.5, 1.0]
            for scale in scales:
                tw, th = int(template.shape[1] * scale), int(template.shape[0] * scale)
                if tw <= 0 or th <= 0:
                    continue

                scaled_template = cv2.resize(template, (tw, th))

                # 灰度匹配
                s_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
                t_gray = cv2.cvtColor(scaled_template, cv2.COLOR_BGR2GRAY)

                # 模板匹配
                result = cv2.matchTemplate(s_gray, t_gray, cv2.TM_CCOEFF_NORMED)
                current_max = np.max(result)

                # 记录最佳匹配
                if current_max > best_score and current_max > 0.6:
                    max_loc = np.unravel_index(np.argmax(result), result.shape)
                    x, y = max_loc[1], max_loc[0]
                    center_x = int(x + tw // 2)
                    center_y = int(y + th // 2)
                    best_score = current_max
                    best_center = (center_x, center_y)
                    best_template = template_path

        # 如果找到匹配度足够高的按钮
        if best_score >= 0.6:
            ctrl.click(best_center[0], best_center[1])
            template_name = os.path.basename(best_template)
            print(f"  {button_type}: matched at ({best_center[0]}, {best_center[1]}) score={best_score:.3f} template={template_name}")
            return True
        else:
            print(f"  {button_type}: match failed, best score={best_score:.3f}")
            return False
    except Exception as e:
        print(f"Template matching failed: {e}")
        return False


def scroll_left(ctrl, display):
    """Swipe left (for swiping through images)"""
    start_x = int(display.width * 0.8)
    end_x = int(display.width * 0.2)
    center_y = display.height // 2
    ctrl.swipe(start_x, center_y, end_x, center_y, 300)


if __name__ == "__main__":
    asyncio.run(main())
