"""Device controller - AirTest integration for Xiaohongshu control"""

import os
import sys
import io
import time
import base64
import tempfile
from typing import Optional, Tuple, Dict, Any, List
from dataclasses import dataclass
from PIL import Image
import numpy as np

# AirTest imports
from airtest.core.api import (
    connect_device,
    snapshot, touch, swipe, text, keyevent,
    start_app, stop_app
)


@dataclass
class DeviceDisplayInfo:
    width: int
    height: int
    density: float
    orientation: int
    rotation: int


class DeviceController:
    """
    Device controller using AirTest

    Provides device control capabilities through AirTest for:
    - Screenshot capture
    - Touch operations (tap, swipe)
    - Text input
    - App management
    - UI hierarchy (via yaml dump)
    """

    # Package name for Xiaohongshu
    XIAOHONGSHU_PACKAGE = "com.xingin.xhs"

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._device: Optional[Android] = None
        self._connected = False
        self._display_info: Optional[DeviceDisplayInfo] = None

    def connect(self) -> bool:
        """Connect to the device via AirTest"""
        if self._connected:
            return True

        try:
            # Connect using Android:// protocol
            # cap_method: javacap (Java screenshot) or minicap
            # touch_method: adb (ADB tap) or minitouch
            self._device = connect_device(
                f"Android:///{self.device_id}?cap_method=javacap&touch_method=adb"
            )
            self._connected = True

            # Get display info
            self._update_display_info()

            print(f"[DeviceController] Connected to device {self.device_id}")
            print(f"[DeviceController] Display: {self._display_info}")
            return True

        except Exception as e:
            print(f"[DeviceController] Failed to connect: {e}")
            self._connected = False
            return False

    def _update_display_info(self):
        """Update display information"""
        if self._device:
            info = self._device.display_info
            self._display_info = DeviceDisplayInfo(
                width=info.get('width', 1080),
                height=info.get('height', 2400),
                density=info.get('density', 3.0),
                orientation=info.get('orientation', 0),
                rotation=info.get('rotation', 0)
            )

    def disconnect(self):
        """Disconnect from the device"""
        if self._device:
            try:
                disconnect_device(self._device)
            except Exception:
                pass
            self._device = None
            self._connected = False

    def is_connected(self) -> bool:
        """Check if device is connected"""
        return self._connected and self._device is not None

    @property
    def display_info(self) -> DeviceDisplayInfo:
        """Get display info"""
        if not self._display_info:
            self._update_display_info()
        return self._display_info or DeviceDisplayInfo(1080, 2400, 3.0, 0, 0)

    def take_screenshot(self) -> bytes:
        """
        Take screenshot and return as PNG bytes

        Returns:
            PNG image bytes, or empty bytes on failure
        """
        if not self.is_connected():
            return b""

        try:
            # snapshot() returns numpy array
            img_array = self._device.snapshot()
            if img_array is None:
                return b""

            # Convert to PIL Image
            img = Image.fromarray(img_array)

            # Save to bytes
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            return buffer.getvalue()

        except Exception as e:
            print(f"[DeviceController] Screenshot failed: {e}")
            return b""

    def take_screenshot_base64(self) -> str:
        """Take screenshot and return as base64 string"""
        return base64.b64encode(self.take_screenshot()).decode()

    def get_control_tree(self) -> str:
        """
        Get UI control tree as XML string

        Uses uiautomator dump to get UI hierarchy.
        """
        if not self.is_connected():
            return "{}"

        try:
            result = self._device.adb.shell("uiautomator dump /sdcard/ui.xml")
            time.sleep(0.5)
            dump_data = self._device.adb.shell("cat /sdcard/ui.xml")
            return dump_data
        except Exception as e:
            print(f"[DeviceController] Failed to get control tree: {e}")
            return "{}"

    def find_element_by_text(self, text: str) -> Optional[Tuple[int, int]]:
        """
        Find UI element by text content using uiautomator dump.

        Returns:
            (x, y) center coordinates of the element, or None if not found.
        """
        try:
            import xml.etree.ElementTree as ET
            xml_str = self.get_control_tree()
            if not xml_str or xml_str == "{}":
                return None

            root = ET.fromstring(xml_str)
            for node in root.iter("node"):
                node_text = node.get("text", "")
                node_content_desc = node.get("content-desc", "")
                if text in node_text or text in node_content_desc:
                    bounds = node.get("bounds", "")
                    if bounds:
                        coords = bounds.replace("][", ",").replace("[", "").replace("]", "").split(",")
                        if len(coords) == 4:
                            x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
                            center_x = (x1 + x2) // 2
                            center_y = (y1 + y2) // 2
                            return (center_x, center_y)
            return None
        except Exception as e:
            print(f"[DeviceController] find_element_by_text failed: {e}")
            return None

    def click_by_text(self, text: str) -> bool:
        """Click an element identified by its text content."""
        coords = self.find_element_by_text(text)
        if coords:
            print(f"[DeviceController] 找到文本 '{text}' 的控件，坐标 {coords}")
            return self.click(coords[0], coords[1])
        print(f"[DeviceController] 未找到文本 '{text}' 的控件")
        return False

    # ============= Basic Operations =============

    def click(self, x: int, y: int) -> bool:
        """Click at coordinates"""
        if not self.is_connected():
            return False

        try:
            touch((x, y))
            return True
        except Exception as e:
            print(f"[DeviceController] Click failed: {e}")
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = None) -> bool:
        """
        Swipe from (x1, y1) to (x2, y2)

        Args:
            x1, y1: Start coordinates
            x2, y2: End coordinates
            duration: Optional swipe duration in ms
        """
        if not self.is_connected():
            return False

        try:
            if duration:
                # AirTest swipe uses duration in seconds as float
                swipe((x1, y1), (x2, y2), duration=duration / 1000)
            else:
                swipe((x1, y1), (x2, y2))
            return True
        except Exception as e:
            print(f"[DeviceController] Swipe failed: {e}")
            return False

    def text_input(self, text: str) -> bool:
        """Input text"""
        if not self.is_connected():
            return False

        try:
            text(text)
            return True
        except Exception as e:
            print(f"[DeviceController] Text input failed: {e}")
            return False

    def press_back(self) -> bool:
        """Press back button"""
        if not self.is_connected():
            return False

        try:
            keyevent("BACK")
            return True
        except Exception as e:
            print(f"[DeviceController] Back key failed: {e}")
            return False

    def press_home(self) -> bool:
        """Press home button"""
        if not self.is_connected():
            return False

        try:
            keyevent("HOME")
            return True
        except Exception as e:
            print(f"[DeviceController] Home key failed: {e}")
            return False

    def press_enter(self) -> bool:
        """Press enter key"""
        if not self.is_connected():
            return False

        try:
            keyevent("ENTER")
            return True
        except Exception as e:
            print(f"[DeviceController] Enter key failed: {e}")
            return False

    # ============= App Management =============

    def start_app(self, package: str = None) -> bool:
        """Start an app"""
        if not self.is_connected():
            return False

        package = package or self.XIAOHONGSHU_PACKAGE

        try:
            start_app(package)
            time.sleep(1)  # Wait for app to start
            return True
        except Exception as e:
            print(f"[DeviceController] Start app failed: {e}")
            return False

    def stop_app(self, package: str = None) -> bool:
        """Stop an app"""
        if not self.is_connected():
            return False

        package = package or self.XIAOHONGSHU_PACKAGE

        try:
            stop_app(package)
            return True
        except Exception as e:
            print(f"[DeviceController] Stop app failed: {e}")
            return False

    def restart_app(self, package: str = None) -> bool:
        """Restart an app"""
        package = package or self.XIAOHONGSHU_PACKAGE
        self.stop_app(package)
        time.sleep(0.5)
        return self.start_app(package)

    def is_app_running(self, package: str = None) -> bool:
        """Check if app is running in foreground (top activity)"""
        if not self.is_connected():
            return False

        package = package or self.XIAOHONGSHU_PACKAGE

        try:
            # 只检查最顶层（前台）activity
            result = self._device.adb.shell("dumpsys activity top | grep ACTIVITY | head -1")
            return package in result
        except Exception:
            return False

    def wake_screen(self) -> bool:
        """Wake up the screen"""
        if not self.is_connected():
            return False

        try:
            self._device.wake()
            return True
        except Exception as e:
            print(f"[DeviceController] Wake screen failed: {e}")
            return False


class XiaohongshuController(DeviceController):
    """
    Specialized controller for Xiaohongshu app

    Provides high-level operations specific to Xiaohongshu
    """

    # Common Xiaohongshu UI element selectors (by text/name)
    # These may vary by app version
    UI_ELEMENTS = {
        'like_button': ['点赞', 'like'],
        'collect_button': ['收藏', 'collect', '收藏按钮'],
        'comment_button': ['评论', 'comment'],
        'share_button': ['分享', 'share'],
        'back': ['返回', 'back'],
        'close': ['关闭', 'close', 'x'],
        'follow': ['关注', 'follow'],
        'profile': ['我', '我的', 'profile'],
        'discovery': ['发现', '首页', 'home'],
        'login': ['登录', 'login'],
        'password': ['密码', 'password'],
        'search': ['搜索', 'search'],
    }

    def __init__(self, device_id: str):
        super().__init__(device_id)
        self.package = self.XIAOHONGSHU_PACKAGE

    def start_xiaohongshu(self) -> bool:
        """Start Xiaohongshu app"""
        return self.start_app(self.package)

    def restart_xiaohongshu(self) -> bool:
        """Restart Xiaohongshu app"""
        return self.restart_app(self.package)

    def open_discovery(self) -> bool:
        """Open discovery page"""
        # First ensure app is running
        if not self.is_app_running():
            self.start_xiaohongshu()
            time.sleep(2)

        # Try to find and click discovery tab
        # The exact element may vary - try common patterns
        # For now, just ensure we're on the app
        return True

    def close_popup(self) -> bool:
        """Close any popup dialog"""
        # Try clicking common close patterns
        # First try coordinates that typically work for close buttons
        display = self.display_info

        # Close button is usually top-right
        close_x = display.width - 50
        close_y = 100

        # Try clicking
        if self.click(close_x, close_y):
            time.sleep(0.3)
            return True

        # Try pressing back as fallback
        return self.press_back()

    def scroll_up(self, duration: int = 300) -> bool:
        """Scroll up (swipe from bottom to top)"""
        display = self.display_info
        center_x = display.width // 2
        start_y = int(display.height * 0.75)
        end_y = int(display.height * 0.25)
        return self.swipe(center_x, start_y, center_x, end_y, duration)

    def scroll_down(self, duration: int = 300) -> bool:
        """Scroll down (swipe from top to bottom)"""
        display = self.display_info
        center_x = display.width // 2
        start_y = int(display.height * 0.25)
        end_y = int(display.height * 0.75)
        return self.swipe(center_x, start_y, center_x, end_y, duration)


# Global controller registry
_controllers: Dict[str, DeviceController] = {}


def get_device_controller(device_id: str) -> DeviceController:
    """
    Get or create device controller

    Args:
        device_id: Android device serial number

    Returns:
        DeviceController instance
    """
    if device_id not in _controllers:
        _controllers[device_id] = XiaohongshuController(device_id)
        _controllers[device_id].connect()
    return _controllers[device_id]


def list_connected_devices() -> List[str]:
    """
    List all connected Android devices via ADB

    Returns:
        List of device serial numbers
    """
    try:
        from airtest.core.android.adb import ADB
        adb = ADB()
        devices = adb.devices()
        return [d[0] for d in devices]
    except Exception as e:
        print(f"[DeviceController] Failed to list devices: {e}")
        return []
