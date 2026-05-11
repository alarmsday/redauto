"""Human operation simulation module"""

import random
import asyncio
from typing import Tuple
import yaml
import os

# 加载系统配置
_config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "system.yaml")
with open(_config_path, "r", encoding="utf-8") as f:
    _config = yaml.safe_load(f)
_anti_crawler_config = _config.get("system", {}).get("anti_crawler", {})


class HumanSimulator:
    """
    Human operation simulator

    Implements random swipe distance, duration, S-curve trajectory, random delay, etc.
    """

    def __init__(
        self,
        swipe_distance_range: Tuple[int, int] = (300, 800),
        swipe_duration_range: Tuple[int, int] = (
            _anti_crawler_config.get("human_swipe_speed_min", 200),
            _anti_crawler_config.get("human_swipe_speed_max", 800)
        ),
        click_delay_range: Tuple[int, int] = (
            _anti_crawler_config.get("human_like_delay_min", 500),
            _anti_crawler_config.get("human_like_delay_max", 2000)
        ),
        page_load_range: Tuple[int, int] = (
            _anti_crawler_config.get("human_browse_time_min", 1000),
            _anti_crawler_config.get("human_browse_time_max", 5000)
        ),
        behavior_profile = None
    ):
        self.base_swipe_distance_range = swipe_distance_range
        self.base_swipe_duration_range = swipe_duration_range
        self.base_click_delay_range = click_delay_range
        self.base_page_load_range = page_load_range
        self.behavior_profile = behavior_profile

        # 如果有行为画像，调整参数范围
        if behavior_profile:
            # 根据画像系数调整范围
            speed_factor = behavior_profile.swipe_speed_factor
            self.swipe_duration_range = (
                int(swipe_duration_range[0] * speed_factor),
                int(swipe_duration_range[1] * speed_factor)
            )

            delay_factor = behavior_profile.click_delay_factor
            self.click_delay_range = (
                int(click_delay_range[0] * delay_factor),
                int(click_delay_range[1] * delay_factor)
            )

            browse_factor = behavior_profile.browse_time_factor
            self.page_load_range = (
                int(page_load_range[0] * browse_factor),
                int(page_load_range[1] * browse_factor)
            )

            # 根据浏览速度调整滑动距离范围
            if behavior_profile.browse_speed == "fast":
                self.swipe_distance_range = (400, 900)  # 快速浏览滑动更远
            elif behavior_profile.browse_speed == "slow":
                self.swipe_distance_range = (200, 600)  # 慢速浏览滑动更近
            else:
                self.swipe_distance_range = swipe_distance_range
        else:
            # 没有画像使用默认值
            self.swipe_distance_range = swipe_distance_range
            self.swipe_duration_range = swipe_duration_range
            self.click_delay_range = click_delay_range
            self.page_load_range = page_load_range

    def get_random_swipe_distance(self) -> int:
        """Get random swipe distance (300-800px)"""
        return random.randint(*self.swipe_distance_range)

    def get_random_swipe_duration(self) -> int:
        """Get random swipe duration (200-500ms)"""
        return random.randint(*self.swipe_duration_range)

    def get_random_click_delay(self) -> int:
        """Get random click delay (500-2000ms)"""
        return random.randint(*self.click_delay_range)

    def get_random_page_load_wait(self) -> int:
        """Get random page load wait time (1000-3000ms)"""
        return random.randint(*self.page_load_range)

    def generate_s_curve_swipe(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        distance: int,
        duration: int
    ) -> Tuple[int, int, int, int, int]:
        """
        Generate S-curve swipe trajectory

        Args:
            start_x, start_y: Start coordinates
            end_x, end_y: End coordinates
            distance: Swipe distance
            duration: Swipe duration (ms)

        Returns:
            (x1, y1, x2, y2, duration) - Actual swipe parameters
        """
        # Calculate offset for S-curve effect
        offset_factor = self.behavior_profile.swipe_offset_factor if self.behavior_profile else 1.0
        offset_x = random.randint(int(-50 * offset_factor), int(50 * offset_factor))
        offset_y = random.randint(int(-30 * offset_factor), int(30 * offset_factor))

        # Add small random perturbation to end point
        perturbation = distance * 0.05 * (offset_factor * 0.5 + 0.5)  # 根据偏移系数调整扰动范围
        pert_x = random.randint(int(-perturbation), int(perturbation))
        pert_y = random.randint(int(-perturbation), int(perturbation))

        actual_end_x = end_x + pert_x + offset_x  # 应用偏移量
        actual_end_y = end_y + pert_y + offset_y

        return (start_x, start_y, actual_end_x, actual_end_y, duration)

    def generate_swipe_coordinates(
        self,
        direction: str = "up",
        start_x: int = 360,
        start_y: int = 800
    ) -> Tuple[int, int, int, int, int]:
        """
        Generate complete swipe parameters based on direction

        Args:
            direction: Swipe direction "up", "down", "left", "right"
            start_x, start_y: Start coordinates (default center-bottom of screen)

        Returns:
            (x1, y1, x2, y2, duration)
        """
        distance = self.get_random_swipe_distance()
        duration = self.get_random_swipe_duration()

        if direction == "up":
            end_x = start_x + random.randint(-30, 30)
            end_y = start_y - distance
        elif direction == "down":
            end_x = start_x + random.randint(-30, 30)
            end_y = start_y + distance
        elif direction == "left":
            end_x = start_x - distance
            end_y = start_y + random.randint(-30, 30)
        else:
            end_x = start_x + distance
            end_y = start_y + random.randint(-30, 30)

        # Ensure coordinates are within reasonable range
        end_x = max(0, min(1440, end_x))
        end_y = max(0, min(3200, end_y))

        return (start_x, start_y, end_x, end_y, duration)

    async def random_delay(self):
        """Random delay (simulating human thinking time)"""
        delay = self.get_random_click_delay()
        await asyncio.sleep(delay / 1000)

    async def wait_for_page_load(self):
        """Wait for page load"""
        wait_time = self.get_random_page_load_wait()
        await asyncio.sleep(wait_time / 1000)


# Global instance
_human_simulator = None


def get_human_simulator() -> HumanSimulator:
    global _human_simulator
    if _human_simulator is None:
        _human_simulator = HumanSimulator()
    return _human_simulator
