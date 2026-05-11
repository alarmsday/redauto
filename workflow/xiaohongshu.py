"""Xiaohongshu workflow - 核心业务流程

设计原则：
- 正常流程使用固定脚本操作，无需LLM介入
- 仅在出现异常/卡点时才调用AI Agent进行决策
- 这样既节省token又保证执行速度
"""

import asyncio
import time
import random
import io
import numpy as np
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

from PIL import Image
from device_manager.controller import XiaohongshuController, get_device_controller
from human_simulation import get_human_simulator, HumanSimulator


@dataclass
class TargetUser:
    xiaohongshu_id: Optional[str]
    nickname: str
    match_mode: str = "exact"
    daily_like_limit: int = 3  # 每日点赞收藏上限


class XiaohongshuWorkflow:
    """
    小红书核心工作流
    """

    PACKAGE = "com.xingin.xhs"

    def __init__(self, device_id: str, test_mode: bool = False):
        self.device_id = device_id
        self.controller: Optional[XiaohongshuController] = None
        self.test_mode = test_mode

        # 获取设备行为画像
        from device_manager import get_device_manager
        device_manager = get_device_manager()
        self.behavior_profile = device_manager.get_device_profile(device_id)
        self.human_sim = HumanSimulator(behavior_profile=self.behavior_profile)

    def _get_controller(self) -> XiaohongshuController:
        """获取或创建设备控制器"""
        if self.controller is None:
            self.controller = get_device_controller(self.device_id)
        return self.controller

    async def start(self):
        """启动工作流"""
        ctrl = self._get_controller()
        print(f"[Workflow] 设备 {self.device_id} 启动")

        if not ctrl.is_connected():
            ctrl.connect()

        # 确保小红书已打开
        await self._ensure_xiaohongshu_loaded()

        # 主循环
        await self._main_loop()

    async def _ensure_xiaohongshu_loaded(self):
        """确保小红书已打开并加载完成"""
        ctrl = self._get_controller()

        xhs_in_foreground = False
        try:
            top_activity = ctrl._device.adb.shell(
                "dumpsys activity top | grep ACTIVITY | head -1"
            )
            if "com.xingin.xhs" in top_activity:
                xhs_in_foreground = True
        except Exception:
            pass

        if not xhs_in_foreground:
            print("[Workflow] 小红书不在前台，启动中...")
            ctrl.start_xiaohongshu()
            await asyncio.sleep(5)

        # 验证APP已加载（通过有效截图判断）
        max_retries = 10
        for i in range(max_retries):
            screenshot = ctrl.take_screenshot()
            if screenshot and len(screenshot) > 10000:
                print(f"[Workflow] APP加载成功 (尝试 {i+1} 次)")
                return
            print(f"[Workflow] 等待APP加载... (尝试 {i+1}/{max_retries})")
            await asyncio.sleep(2)

        print("[Workflow] APP加载失败，重启中...")
        ctrl.restart_xiaohongshu()
        await asyncio.sleep(5)

    async def _main_loop(self):
        """主浏览循环"""
        ctrl = self._get_controller()
        display = ctrl.display_info
        loop_count = 0
        max_loops = 100
        consecutive_no_target = 0  # 连续未找到目标计数

        while loop_count < max_loops:
            loop_count += 1
            print(f"[Workflow] 第 {loop_count} 轮循环")

            try:
                # 首次进入循环确保在发现页
                if loop_count == 1:
                    await self._ensure_discovery_page()

                # 纠错：确保当前在发现页
                if not await self._is_on_discovery_page():
                    print("[Workflow] 当前不在发现页，执行纠错...")
                    await self._ensure_discovery_page()

                await self._save_discovery_screenshot()

                # 测试模式：随机滑动后进入随机帖子
                if self.test_mode:
                    await self._random_scroll()
                    await asyncio.sleep(random.uniform(1, 2))
                    is_video = random.random() < 0.5
                    post_type = "视频" if is_video else "图文"
                    print(f"[Workflow] 测试模式：进入随机{post_type}帖子")
                    target_info = {
                        'is_video': is_video,
                        'post_id': f'post_test_{random.randint(1000, 9999)}',
                    }
                    consecutive_no_target = 0
                else:
                    # 生产模式：先扫描当前页，最多滑动2次
                    target_info = None
                    for scan_attempt in range(3):
                        target_info = await self._find_target_post()
                        if target_info is not None:
                            consecutive_no_target = 0
                            break
                        print(f"[Workflow] 第{scan_attempt+1}次扫描未找到目标")
                        # 滑动一次
                        await self._random_scroll()
                        await asyncio.sleep(random.uniform(1.5, 2.5))

                    if target_info is None:
                        consecutive_no_target += 1
                        print(f"[Workflow] 当前区域无目标（连续{consecutive_no_target}次），继续滑动...")
                        # 再滑动一次，给算法推荐新内容
                        await self._random_scroll()
                        await asyncio.sleep(random.uniform(1.5, 2.5))
                        continue

                    # 检查每日操作次数限制
                    from workflow.daily_tracker import can_operate
                    from workflow.target_detector import get_target_users
                    nickname = target_info.get('nickname', '')
                    # 从TargetUser获取该用户的每日上限
                    daily_limit = 3
                    for u in get_target_users():
                        if u.nickname == nickname:
                            daily_limit = u.daily_like_limit
                            break
                    allowed, reason = can_operate(nickname, daily_limit)
                    print(reason)
                    if not allowed:
                        # 该用户今日已达上限，滑动跳过
                        await self._random_scroll()
                        await asyncio.sleep(random.uniform(1.5, 2.5))
                        continue

                # 进入帖子
                await self._enter_post(target_info)

                # 浏览帖子（自动识别视频/图文）
                await self._browse_post()

                # 点赞和收藏
                await self._like_and_collect()

                # 记录每日操作次数
                from workflow.daily_tracker import increment_count
                nickname = target_info.get('nickname', '')
                if nickname:
                    new_count = increment_count(nickname)
                    print(f"[每日追踪] {nickname} 今日第{new_count}次点赞收藏")

                # 保存截图
                await self._save_operation_screenshot(target_info)

                # 返回发现页
                await self._return_to_discovery()

                # 纠错：确保返回后仍在发现页
                if not await self._is_on_discovery_page():
                    print("[Workflow] 返回后不在发现页，执行纠错...")
                    await self._ensure_discovery_page()

                # 随机等待
                await asyncio.sleep(random.uniform(2, 5))

            except Exception as e:
                print(f"[Workflow] 循环异常: {e}")
                # 错误恢复：多次返回+确保在发现页
                for _ in range(3):
                    ctrl.press_back()
                    await asyncio.sleep(0.5)
                # 如果还没到发现页，强制切过去
                if not await self._is_on_discovery_page():
                    await self._ensure_discovery_page()
                consecutive_no_target = 0

    async def _is_on_discovery_page(self) -> bool:
        """检测当前是否在发现页 - OCR+颜色检测高亮Tab"""
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import io

            ctrl = self._get_controller()
            screenshot_bytes = ctrl.take_screenshot()
            if not screenshot_bytes:
                return False

            img = Image.open(io.BytesIO(screenshot_bytes))
            img_np = np.array(img)
            h, w = img_np.shape[:2]

            # Tab文字在屏幕约10%-20%位置（通过uiautomator实测发现文字在y=354左右）
            tab_region = img_np[int(h*0.08):int(h*0.22), :]

            try:
                reader = self._get_ocr_reader()
                if reader is not None:
                    results = reader.readtext(tab_region, detail=1)

                    # 记录每个Tab文字的颜色深度（越深=越可能是高亮）
                    tab_colors = {}
                    for (bbox, text, conf) in results:
                        x_coords = [int(p[0]) for p in bbox]
                        y_coords = [int(p[1]) for p in bbox]

                        if '发现' in text or '同城' in text or '关注' in text:
                            x1, y1 = max(0, min(x_coords)), max(0, min(y_coords))
                            x2, y2 = min(tab_region.shape[1], max(x_coords)), min(tab_region.shape[0], max(y_coords))
                            if x2 > x1 and y2 > y1:
                                text_patch = tab_region[y1:y2, x1:x2]
                                brightness = np.mean(text_patch)
                                tab_colors[text.strip()] = (brightness, (min(x_coords) + max(x_coords)) // 2)

                    # 最暗的文字 = 高亮Tab
                    if tab_colors:
                        darkest_tab = min(tab_colors.items(), key=lambda x: x[1][0])
                        tab_name = darkest_tab[0]

                        if '同城' in tab_name:
                            print(f"[Workflow] 高亮Tab: {tab_name}，不在发现页")
                            return False
                        elif '发现' in tab_name:
                            print(f"[Workflow] 高亮Tab: {tab_name}，在发现页")
                            return True
                        else:
                            print(f"[Workflow] 高亮Tab: {tab_name}，不在发现页")
                            return False

            except Exception as e:
                print(f"[Workflow] OCR检测异常: {e}")

            return False
        except Exception as e:
            print(f"[Workflow] 页面检测异常: {e}")
            return False

    async def _ensure_discovery_page(self):
        """确保在发现页 - 重启APP确保进入正确的页面"""
        ctrl = self._get_controller()

        # 重启小红书，确保从发现页启动
        print("[Workflow] 重启APP确保在发现页...")
        ctrl.restart_xiaohongshu()
        await asyncio.sleep(5)

        # 验证APP加载
        for i in range(5):
            screenshot = ctrl.take_screenshot()
            if screenshot and len(screenshot) > 10000:
                print(f"[Workflow] APP加载成功 (尝试 {i+1} 次)")
                break
            await asyncio.sleep(1)

        # 验证是否在发现页，如果不在，尝试点击"发现"Tab
        if not await self._is_on_discovery_page():
            print("[Workflow] 重启后不在发现页，尝试点击发现Tab...")
            try:
                self._click_discovery_tab()
                await asyncio.sleep(2)
            except Exception as e:
                print(f"[Workflow] 点击发现Tab失败: {e}")

    def _click_discovery_tab(self):
        """点击顶部"发现"Tab - 通过OCR定位"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        screenshot_bytes = ctrl.take_screenshot()
        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]

        # Tab区域：屏幕顶部约8%-22%
        tab_region = img_np[int(h*0.08):int(h*0.22), :]

        reader = self._get_ocr_reader()
        if reader is not None:
            results = reader.readtext(tab_region, detail=1)
            for (bbox, text, conf) in results:
                if '发现' in text and conf > 0.2:
                    abs_x = [int(p[0]) for p in bbox]
                    abs_y = [int(p[1]) + int(h*0.08) for p in bbox]
                    x_center = sum(abs_x) // len(abs_x)
                    y_center = sum(abs_y) // len(abs_y)
                    ctrl.click(x_center, y_center)
                    print(f"[Workflow] 点击发现Tab ({x_center}, {y_center})")
                    return True
        return False

    async def _save_discovery_screenshot(self):
        """保存发现页截图"""
        ctrl = self._get_controller()
        screenshot = ctrl.take_screenshot()
        try:
            from storage import get_storage_manager
            storage = get_storage_manager()
            storage.save_discovery_screenshot(
                account_name="default",
                user_nickname="discovery",
                device_id=self.device_id,
                screenshot_data=screenshot
            )
        except Exception as e:
            print(f"[Workflow] 截图保存失败: {e}")

    async def _find_target_post(self) -> Optional[Dict]:
        """查找目标用户帖子 - 优先OCR扫描（快），降级为LLM检测（兜底）"""
        ctrl = self._get_controller()
        screenshot = ctrl.take_screenshot()

        # 1. 优先使用OCR快速扫描
        try:
            target_users = self._get_target_users()
            if target_users:
                result = await self._ocr_scan_for_targets()
                if result is not None:
                    return result
        except Exception as e:
            print(f"[Workflow] OCR目标扫描失败: {e}")

        # 2. OCR没找到，用LLM兜底
        try:
            from workflow.target_detector import (
                check_discovery_page_for_targets,
                get_target_users
            )
            target_users = get_target_users()
            if target_users:
                found, target_info = await check_discovery_page_for_targets(
                    screenshot, target_users
                )
                if found:
                    return target_info
        except Exception as e:
            print(f"[Workflow] LLM目标检测不可用: {e}")

        return None

    def _get_target_users(self) -> List[TargetUser]:
        """获取目标用户列表"""
        # 可以从配置文件读取，这里先用硬编码
        target_users = []
        try:
            from workflow.target_detector import get_target_users
            target_users = get_target_users()
        except Exception:
            pass
        return target_users

    async def _ocr_scan_for_targets(self) -> Optional[Dict]:
        """使用OCR扫描发现页查找目标用户，支持昵称截断模糊匹配"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        import unicodedata
        screenshot_bytes = ctrl.take_screenshot()
        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]

        content_y_start = int(h * 0.08)
        content_y_end = int(h * 0.85)
        content_region = img_np[content_y_start:content_y_end, :]

        reader = self._get_ocr_reader()
        if reader is not None:
            results = reader.readtext(content_region, detail=1)
            target_users = self._get_target_users()

            for target in target_users:
                # 跳过纯emoji昵称（OCR无法识别emoji）
                nick_text = target.nickname.strip()
                is_emoji_only = all(
                    unicodedata.category(c)[0] == 'So' for c in nick_text
                ) if nick_text else True
                if is_emoji_only:
                    continue

                for (bbox, text, conf) in results:
                    if conf < 0.3:
                        continue
                    # 使用target_detector的匹配逻辑
                    from workflow.target_detector import _match_nickname
                    if _match_nickname(target.nickname, text, target.match_mode):
                        abs_y = [int(p[1]) + content_y_start for p in bbox]
                        y_pos = sum(abs_y) // len(abs_y)
                        x_center = sum([int(p[0]) for p in bbox]) // 4
                        print(f"[Workflow] OCR找到目标用户: '{text}' -> '{target.nickname}' ({x_center}, {y_pos})")
                        return {
                            'nickname': target.nickname,
                            'x': x_center,
                            'y': y_pos,
                            'is_video': False,
                        }
        return None

    async def _click_user_nickname(self, target_name: str = None):
        """检测发现页上的用户昵称并点击

        Args:
            target_name: 指定目标用户名，如果为None则点击第一个可用昵称
        """
        ctrl = self._get_controller()
        display = ctrl.display_info

        screenshot_bytes = ctrl.take_screenshot()
        img = Image.open(io.BytesIO(screenshot_bytes))
        img_np = np.array(img)
        h, w = img_np.shape[:2]

        try:
            # 检测帖子内容区域（跳过顶部Tab和底部导航栏）
            content_y_start = int(h * 0.08)
            content_y_end = int(h * 0.85)
            content_region = img_np[content_y_start:content_y_end, :]

            reader = self._get_ocr_reader()
            if reader is not None:
                results = reader.readtext(content_region, detail=1)

                # 查找符合昵称特征的文字：短文本、有@符号或纯中文
                nickname_candidates = []
                for (bbox, text, conf) in results:
                    # 昵称特征：长度2-10字符，置信度>0.5
                    if 2 <= len(text) <= 10 and conf > 0.5:
                        # 计算文字在屏幕上的绝对位置
                        abs_y = [int(p[1]) + content_y_start for p in bbox]
                        y_pos = sum(abs_y) // len(abs_y)

                        # 昵称通常在帖子卡片底部，跳过太靠上和太靠下的文字
                        if int(h * 0.15) < y_pos < int(h * 0.75):
                            x_center = sum([int(p[0]) for p in bbox]) // 4
                            nickname_candidates.append((text, x_center, y_pos, conf))

                # 如果指定了目标用户名，优先匹配
                if target_name:
                    for (text, x, y, conf) in nickname_candidates:
                        if target_name in text:
                            ctrl.click(x, y)
                            await asyncio.sleep(3)
                            print(f"[Workflow] 点击目标用户昵称: {text} ({x}, {y})")
                            return True
                    print(f"[Workflow] 当前页面未找到目标用户: {target_name}")
                    return False

                # 否则选择置信度最高的昵称点击
                if nickname_candidates:
                    nickname_candidates.sort(key=lambda x: x[3], reverse=True)
                    target = nickname_candidates[0]
                    ctrl.click(target[1], target[2])
                    await asyncio.sleep(3)
                    print(f"[Workflow] 点击用户昵称: {target[0]} ({target[1]}, {target[2]})")
                    return True

        except Exception as e:
            print(f"[Workflow] 昵称检测失败: {e}")

        # 降级方案：使用固定位置点击
        nickname_x = int(display.width * 0.3)
        nickname_y = int(display.height * 0.5)
        ctrl.click(nickname_x, nickname_y)
        await asyncio.sleep(3)
        print(f"[Workflow] 使用固定坐标点击昵称 ({nickname_x}, {nickname_y})")
        return True

    async def _enter_post(self, target_info: Dict):
        """进入帖子详情 - 点击帖子封面下方的用户昵称"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        if self.test_mode:
            # 测试模式：随机坐标点击进入帖子
            nickname_x = random.randint(int(display.width * 0.15), int(display.width * 0.4))
            nickname_y = random.randint(int(display.height * 0.45), int(display.height * 0.55))
            ctrl.click(nickname_x, nickname_y)
            await asyncio.sleep(3)
            print(f"[Workflow] 进入帖子 (随机坐标 {nickname_x}, {nickname_y})")
        elif 'x' in target_info and 'y' in target_info:
            # OCR扫描找到目标，直接点击昵称位置
            ctrl.click(target_info['x'], target_info['y'])
            await asyncio.sleep(3)
            print(f"[Workflow] 进入帖子 (OCR目标昵称 {target_info['x']}, {target_info['y']})")
        else:
            # 生产模式：通过OCR检测用户昵称并点击
            await self._click_user_nickname()

    async def _detect_post_type(self) -> str:
        """检测帖子类型，返回 'video' 或 'image'"""
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import io

            ctrl = self._get_controller()
            screenshot_bytes = ctrl.take_screenshot()
            if not screenshot_bytes:
                return "image"

            img = Image.open(io.BytesIO(screenshot_bytes))
            img_np = np.array(img)
            h, w = img_np.shape[:2]
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)

            # 1. 检测视频特征：底部操作栏（半透明黑色背景 + 白色图标）
            bottom_region = img_np[int(h*0.90):, :]
            bottom_gray = cv2.cvtColor(bottom_region, cv2.COLOR_RGB2GRAY)
            avg_bottom = np.mean(bottom_gray)
            if avg_bottom < 80:
                _, icon_thresh = cv2.threshold(bottom_gray, 200, 255, cv2.THRESH_BINARY)
                icon_ratio = np.count_nonzero(icon_thresh) / icon_thresh.size
                if icon_ratio > 0.005:
                    print(f"[Workflow] 检测为视频（底部操作栏）")
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
                print(f"[Workflow] 检测为图文（发现{dot_count}个页面指示圆点）")
                return "image"

            # 3. 全屏黑边 → 图文
            if np.mean(img_np[:int(h*0.05), :]) < 20 and np.mean(img_np[int(h*0.95):, :]) < 20:
                print("[Workflow] 检测为图文（全屏模式，上下黑边）")
                return "image"

            print("[Workflow] 检测为图文（兜底）")
            return "image"
        except Exception as e:
            print(f"[Workflow] 帖子类型检测失败: {e}")
            return "image"

    async def _browse_post(self):
        """浏览帖子 - 自动识别视频/图文"""
        post_type = await self._detect_post_type()
        if post_type == "video":
            print("[Workflow] 浏览视频内容...")
            await self._browse_video()
        else:
            print("[Workflow] 浏览图文内容...")
            await self._browse_images()

    async def _browse_images(self):
        """浏览图文帖子 - 滑动到最后一张，通过截图对比判断是否到达末页"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        browse_time = random.uniform(1, 3)
        await asyncio.sleep(browse_time)

        # 先尝试检测图片张数（作为参考）
        total = await self._count_image_pages()
        if total <= 1:
            print("[Workflow] 单图帖子，无需滑动")
            return

        print(f"[Workflow] 检测到约 {total} 张图，开始滑动浏览")

        # 滑动到最后一张：左滑直到连续2次截图不再变化
        max_swipes = max(total + 5, 20)  # 安全上限
        swipe_count = 0
        consecutive_same = 0  # 连续相似计数

        # 获取当前截图作为基准
        prev_screenshot = ctrl.take_screenshot()

        while swipe_count < max_swipes:
            self._scroll_left()
            await asyncio.sleep(2.0)  # 等页面动画完全完成
            swipe_count += 1

            curr_screenshot = ctrl.take_screenshot()
            similarity = self._compare_images(prev_screenshot, curr_screenshot)

            print(f"[Workflow] 左滑第 {swipe_count} 次，截图相似度={similarity:.3f}")

            if similarity > 0.95:
                consecutive_same += 1
                if consecutive_same >= 2:
                    # 连续2次相似，确认已到达最后一页
                    print(f"[Workflow] 连续{consecutive_same}次相似，已到达最后一页")
                    break
            else:
                consecutive_same = 0  # 有变化，重置计数

            prev_screenshot = curr_screenshot
            if swipe_count < max_swipes:
                await asyncio.sleep(random.uniform(0.3, 0.8))

    def _compare_images(self, img_bytes1: bytes, img_bytes2: bytes) -> float:
        """比较两张截图的相似度，只关注内容区域（排除底部操作栏）"""
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import io

            img1 = np.array(Image.open(io.BytesIO(img_bytes1)))
            img2 = np.array(Image.open(io.BytesIO(img_bytes2)))

            # 如果尺寸不同，缩放到相同尺寸
            if img1.shape != img2.shape:
                img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]))

            h = img1.shape[0]
            # 排除顶部状态栏(5%)和底部操作栏(15%)，只比较中间内容区
            content1 = img1[int(h*0.05):int(h*0.85), :]
            content2 = img2[int(h*0.05):int(h*0.85), :]

            gray1 = cv2.cvtColor(content1, cv2.COLOR_RGB2GRAY)
            gray2 = cv2.cvtColor(content2, cv2.COLOR_RGB2GRAY)

            diff = cv2.absdiff(gray1, gray2)
            mean_diff = np.mean(diff)
            # 差值越小相似度越高，转换为 0~1 范围
            similarity = max(0, 1 - mean_diff / 30)

            return similarity
        except Exception as e:
            print(f"[Workflow] 图片对比失败: {e}")
            return 0

    def _scroll_left(self):
        """向左滑动（翻阅图片）"""
        ctrl = self._get_controller()
        display = ctrl.display_info
        start_x = int(display.width * 0.8)
        end_x = int(display.width * 0.2)
        center_y = display.height // 2
        ctrl.swipe(start_x, center_y, end_x, center_y, 300)

    def _get_ocr_reader(self):
        """懒加载EasyOCR"""
        if not hasattr(self, '_ocr_reader'):
            try:
                import easyocr
                self._ocr_reader = easyocr.Reader(['ch_sim', 'en'], gpu=False, verbose=False)
                print("[Workflow] EasyOCR 模型加载成功")
            except Exception as e:
                print(f"[Workflow] EasyOCR 加载失败: {e}")
                self._ocr_reader = None
        return self._ocr_reader

    async def _count_image_pages(self) -> int:
        """检测图片张数，检测失败返回10（兜底）"""
        try:
            import cv2
            import numpy as np
            from PIL import Image
            import io

            ctrl = self._get_controller()
            screenshot_bytes = ctrl.take_screenshot()
            if not screenshot_bytes:
                return 10

            img = Image.open(io.BytesIO(screenshot_bytes))
            img_np = np.array(img)
            h, w = img_np.shape[:2]

            # 方法1: 从右上角页码标识 "X/N" OCR识别，取斜杠后的数字（总页数）
            corner = img_np[int(h*0.06):int(h*0.2), int(w*0.75):]
            try:
                reader = self._get_ocr_reader()
                if reader is not None:
                    result = reader.readtext(corner, detail=0)
                    for text in result:
                        if '/' in text:
                            parts = text.replace(' ', '').split('/')
                            total_part = parts[-1]  # 取斜杠后的部分（总页数）
                            if total_part.isdigit():
                                n = int(total_part)
                                if 1 <= n <= 20:
                                    print(f"[Workflow] OCR识别到 {n} 张")
                                    return n
            except Exception:
                pass

            # 方法2: 圆点计数
            gray = cv2.cvtColor(img_np, cv2.COLOR_RGB2GRAY)
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
                print(f"[Workflow] 圆点计数 {dot_count} 个")
                return dot_count

        except Exception as e:
            print(f"[Workflow] 图片计数失败: {e}")
        return 10  # 兜底10张

    async def _ocr_page_number(self) -> Tuple[int, int]:
        """检测页码 - 兼容旧接口，返回 (当前页, 总页数)"""
        total = await self._count_image_pages()
        return 1, total

    async def _browse_video(self):
        """浏览视频帖子"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        # 拖动进度条到2/3位置
        bar_y = int(display.height * 0.9)
        bar_start_x = int(display.width * 0.1)
        bar_end_x = int(display.width * 0.9)
        target_x = int(bar_start_x + (bar_end_x - bar_start_x) * 0.66)

        ctrl.swipe(bar_start_x, bar_y, target_x, bar_y, 500)
        await asyncio.sleep(1)

        watch_time = random.randint(3, 5)
        print(f"[Workflow] 观看视频 {watch_time} 秒...")
        await asyncio.sleep(watch_time)

    async def _like_and_collect(self):
        """执行点赞和收藏 - 使用模板匹配"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        operations = ["like", "collect"]
        if random.random() < 0.5:
            operations.reverse()

        for op in operations:
            clicked = await self._click_button_by_template(op, ctrl)
            if not clicked:
                # 模板匹配失败，使用固定坐标
                if op == "like":
                    like_x = int(display.width * 0.72)
                    like_y = int(display.height * 0.93)
                    ctrl.click(like_x, like_y)
                    print(f"[Workflow] 点赞 (坐标 {like_x}, {like_y})")
                else:
                    collect_x = int(display.width * 0.82)
                    collect_y = int(display.height * 0.93)
                    ctrl.click(collect_x, collect_y)
                    print(f"[Workflow] 收藏 (坐标 {collect_x}, {collect_y})")

            if op != operations[-1]:
                await asyncio.sleep(random.uniform(0.5, 1.5))

    async def _click_button_by_template(self, button_type: str, ctrl) -> bool:
        """使用图像模板匹配点击按钮"""
        try:
            import cv2
            import numpy as np
            import io
            from PIL import Image
            import os

            screenshot_bytes = ctrl.take_screenshot()
            if not screenshot_bytes:
                return False

            img = Image.open(io.BytesIO(screenshot_bytes))
            screenshot = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            display = ctrl.display_info
            sh, sw = screenshot.shape[:2]

            # 底部20%区域（操作栏位置）
            roi_y = int(sh * 0.80)
            roi = screenshot[roi_y:, :]

            # 优先使用视频专用模板
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
                    if tw <= 0 or th <= 0 or tw > roi.shape[1] or th > roi.shape[0]:
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
                print(f"[Workflow] {button_type} (模板匹配 {best_center[0]}, {best_center[1]}, 匹配度 {best_score:.3f})")
                return True
            else:
                print(f"[Workflow] {button_type}: 模板匹配失败，最高分={best_score:.3f}")
                return False
        except Exception as e:
            print(f"[Workflow] 模板匹配异常: {e}")
            return False

    async def _save_operation_screenshot(self, target_info: Dict):
        """保存操作完成截图"""
        ctrl = self._get_controller()
        screenshot = ctrl.take_screenshot()
        try:
            from storage import get_storage_manager
            storage = get_storage_manager()
            storage.save_operation_screenshot(
                account_name="default",
                user_nickname="operation",
                device_id=self.device_id,
                screenshot_data=screenshot
            )
        except Exception as e:
            print(f"[Workflow] 操作截图保存失败: {e}")

    async def _return_to_discovery(self):
        """返回发现页"""
        ctrl = self._get_controller()
        ctrl.press_back()
        await asyncio.sleep(2)

        # 纠错：确保返回后在发现页
        if not await self._is_on_discovery_page():
            print("[Workflow] 返回后不在发现页，执行纠错...")
            await self._ensure_discovery_page()

    async def _random_scroll(self):
        """随机下滑（浏览新内容）"""
        ctrl = self._get_controller()
        display = ctrl.display_info

        # 手指从下往上滑 = 内容上移，浏览新内容
        # 短距离滑动（20%屏幕高度），避免瀑布流滑过太多帖子
        start_x = display.width // 2
        start_y = int(display.height * 0.65)
        end_y = int(display.height * 0.45)
        duration = random.randint(150, 300)
        ctrl.swipe(start_x, start_y, start_x, end_y, duration)
