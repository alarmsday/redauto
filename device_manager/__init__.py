"""设备管理模块"""

import subprocess
import time
import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import yaml
import os

import threading


class ConnectionType(Enum):
    USB = "usb"
    WIFI = "wifi"


class DeviceStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    RUNNING = "running"
    ERROR = "error"


@dataclass
class DeviceBehaviorProfile:
    """设备行为画像，每个设备有独特的行为特征，模拟不同用户的使用习惯"""
    # 滑动相关参数
    swipe_speed_factor: float  # 滑动速度系数，0.8-1.2，值越大滑动越快
    swipe_offset_factor: float  # 滑动轨迹偏移系数，0.5-1.5，值越大偏移越大
    # 延迟相关参数
    click_delay_factor: float  # 点击延迟系数，0.8-1.2，值越大点击前等待越久
    browse_time_factor: float  # 浏览时间系数，0.7-1.4，值越大浏览时间越长
    # 操作习惯
    prefer_video: bool  # 是否更喜欢看视频
    browse_speed: str  # 浏览速度：slow/normal/fast
    operation_frequency: float  # 操作频率系数，0.8-1.3，值越大操作越频繁


@dataclass
class DeviceInfo:
    device_id: str
    device_name: str
    status: DeviceStatus
    connection_type: ConnectionType
    last_heartbeat: float
    behavior_profile: Optional[DeviceBehaviorProfile] = None


class ADBDevice:
    """ADB设备封装"""

    def __init__(self, device_id: str):
        self.device_id = device_id
        self._connected = False

    def is_connected(self) -> bool:
        """检查设备是否连接"""
        try:
            result = subprocess.run(
                ["adb", "-s", self.device_id, "shell", "echo", "ok"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0 and b"ok" in result.stdout
        except Exception:
            return False

    def get_device_name(self) -> str:
        """获取设备名称"""
        try:
            result = subprocess.run(
                ["adb", "-s", self.device_id, "shell", "getprop", "ro.product.model"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.decode().strip()
        except Exception:
            pass
        return self.device_id

    def get_screen_resolution(self) -> Tuple[int, int]:
        """获取屏幕分辨率"""
        try:
            result = subprocess.run(
                ["adb", "-s", self.device_id, "shell", "wm", "size"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                output = result.stdout.decode().strip()
                # 格式: Physical size: 1080x2400
                if "x" in output:
                    parts = output.split(":")[-1].strip().split("x")
                    return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return (1080, 2400)  # 默认值


class DeviceManager:
    """设备管理器"""

    def __init__(self):
        self._devices: Dict[str, DeviceInfo] = {}
        self._lock = threading.Lock()
        self._reconnect_retries = 3
        self._device_profiles: Dict[str, DeviceBehaviorProfile] = {}  # 设备行为画像缓存

        # 加载设备黑白名单配置
        self._load_device_filters()

    def scan_devices(self) -> List[DeviceInfo]:
        """扫描所有连接的设备"""
        with self._lock:
            try:
                result = subprocess.run(
                    ["adb", "devices", "-l"],
                    capture_output=True,
                    timeout=10
                )
                if result.returncode != 0:
                    return []

                devices = []
                lines = result.stdout.decode().strip().split("\n")[1:]  # 跳过第一行标题

                for line in lines:
                    if not line.strip():
                        continue

                    parts = line.split()
                    if len(parts) < 2:
                        continue

                    device_id = parts[0]
                    status = parts[1]  # device or unauthorized

                    if status == "device":
                        adb_device = ADBDevice(device_id)
                        device_name = adb_device.get_device_name()

                        # 判断连接类型
                        conn_type = ConnectionType.USB
                        if "product:" in line:
                            # 可能通过wifi连接
                            pass

                        device_info = DeviceInfo(
                            device_id=device_id,
                            device_name=device_name,
                            status=DeviceStatus.ONLINE,
                            connection_type=conn_type,
                            last_heartbeat=time.time(),
                            behavior_profile=self._generate_behavior_profile(device_id)
                        )
                        # 应用黑白名单过滤
                        if self.is_device_allowed(device_id):
                            devices.append(device_info)
                            self._devices[device_id] = device_info
                        else:
                            print(f"设备 {device_id} 被过滤（白名单/黑名单规则）")

                return devices

            except Exception as e:
                print(f"扫描设备失败: {e}")
                return []

    def reconnect_device(self, device_id: str) -> bool:
        """尝试重连设备"""
        for attempt in range(self._reconnect_retries):
            try:
                # 先断开
                subprocess.run(["adb", "-s", device_id, "kill-server"],
                             capture_output=True, timeout=5)
                time.sleep(1)

                # 重新连接
                result = subprocess.run(["adb", "connect", device_id],
                                      capture_output=True, timeout=5)
                if result.returncode == 0 and b"connected" in result.stdout:
                    return True

            except Exception:
                pass

            time.sleep(2)

        return False

    def get_device(self, device_id: str) -> Optional[DeviceInfo]:
        """获取设备信息"""
        with self._lock:
            return self._devices.get(device_id)

    def get_all_devices(self) -> List[DeviceInfo]:
        """获取所有设备"""
        with self._lock:
            return list(self._devices.values())

    def get_online_devices(self) -> List[DeviceInfo]:
        """获取在线设备"""
        with self._lock:
            return [d for d in self._devices.values() if d.status == DeviceStatus.ONLINE]

    def _load_device_filters(self):
        """加载设备黑白名单配置"""
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "system.yaml")
        self.device_whitelist = []
        self.device_blacklist = []

        try:
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                system_config = config.get('system', {})
                self.device_whitelist = system_config.get('device_whitelist', [])
                self.device_blacklist = system_config.get('device_blacklist', [])
                print(f"设备白名单: {self.device_whitelist}")
                print(f"设备黑名单: {self.device_blacklist}")
        except Exception as e:
            print(f"加载设备过滤配置失败: {e}")

    def _generate_behavior_profile(self, device_id: str) -> DeviceBehaviorProfile:
        """为设备生成唯一的行为画像，基于设备ID哈希保证同一设备每次生成的画像一致"""
        # 基于设备ID生成稳定的随机种子
        seed = sum(ord(c) for c in device_id)
        rng = random.Random(seed)

        # 生成随机系数，范围符合真实用户差异
        return DeviceBehaviorProfile(
            swipe_speed_factor=rng.uniform(0.8, 1.2),
            swipe_offset_factor=rng.uniform(0.5, 1.5),
            click_delay_factor=rng.uniform(0.8, 1.2),
            browse_time_factor=rng.uniform(0.7, 1.4),
            prefer_video=rng.choice([True, False, False]),  # 2/3用户更喜欢图文，1/3更喜欢视频
            browse_speed=rng.choice(["slow", "normal", "normal", "fast"]),  # 正常速度占比更高
            operation_frequency=rng.uniform(0.8, 1.3)
        )

    def get_device_profile(self, device_id: str) -> DeviceBehaviorProfile:
        """获取设备的行为画像，不存在则生成"""
        with self._lock:
            if device_id not in self._device_profiles:
                self._device_profiles[device_id] = self._generate_behavior_profile(device_id)
                print(f"为设备 {device_id} 生成行为画像: 浏览速度={self._device_profiles[device_id].browse_speed}")
            return self._device_profiles[device_id]

    def is_device_allowed(self, device_id: str) -> bool:
        """检查设备是否允许使用
        规则：
        1. 如果白名单非空，只有在白名单中的设备允许
        2. 如果设备在黑名单中，一律禁止
        """
        # 黑名单优先
        if device_id in self.device_blacklist:
            return False

        # 白名单非空时，必须在白名单中
        if self.device_whitelist and device_id not in self.device_whitelist:
            return False

        return True


# 全局实例
_device_manager: DeviceManager = None


def get_device_manager() -> DeviceManager:
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
