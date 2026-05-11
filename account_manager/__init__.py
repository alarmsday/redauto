"""Account manager module"""

import yaml
import os
import asyncio
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class AccountStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOGGING_IN = "logging_in"
    LOGGED_IN = "logged_in"
    VERIFICATION_REQUIRED = "verification_required"
    ERROR = "error"


@dataclass
class Account:
    account: str
    password: str
    device: Optional[str] = None
    status: AccountStatus = AccountStatus.INACTIVE


class AccountPool:
    """Account pool manager"""

    def __init__(self, config_path: str):
        self.config_path = config_path
        self._accounts: List[Account] = []
        self._last_account: Optional[str] = None  # 上一次使用的账号，用于轮询切换
        self._load_config()

    def _load_config(self):
        """Load account configuration from YAML"""
        if not os.path.exists(self.config_path):
            self._accounts = []
            return

        with open(self.config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        accounts_data = data.get('accounts', [])
        self._accounts = [
            Account(
                account=a.get('account', ''),
                password=a.get('password', ''),
                device=a.get('device'),
                status=AccountStatus.ACTIVE if a.get('status') == 'active' else AccountStatus.INACTIVE
            )
            for a in accounts_data
        ]

    def get_account(self, account: str) -> Optional[Account]:
        """Get account by account ID"""
        for acc in self._accounts:
            if acc.account == account:
                return acc
        return None

    def get_account_for_device(self, device_id: str) -> Optional[Account]:
        """Get account assigned to device, or first available active account"""
        # First try device-specific account
        for acc in self._accounts:
            if acc.device == device_id and acc.status == AccountStatus.ACTIVE:
                return acc

        # Then try first available active account not assigned to any device
        for acc in self._accounts:
            if acc.status == AccountStatus.ACTIVE and acc.device is None:
                return acc

        return None

    def get_all_accounts(self) -> List[Account]:
        """Get all accounts"""
        return self._accounts

    def get_active_accounts(self) -> List[Account]:
        """Get all active accounts"""
        return [acc for acc in self._accounts if acc.status == AccountStatus.ACTIVE]

    def update_account_status(self, account: str, status: AccountStatus):
        """Update account status"""
        acc = self.get_account(account)
        if acc:
            acc.status = status

    def reload(self):
        """Reload configuration"""
        self._load_config()

    async def auto_login(self, device_controller, account: Account) -> bool:
        """自动登录小红书
        Args:
            device_controller: 设备控制器实例
            account: 要登录的账号
        Returns:
            登录是否成功
        """
        try:
            ctrl = device_controller
            display = ctrl.display_info

            # 1. 确保小红书在前台
            if not ctrl.is_app_running():
                ctrl.start_xiaohongshu()
                await asyncio.sleep(5)
            else:
                try:
                    current_focus = ctrl._device.adb.shell("dumpsys activity top | grep ACTIVITY")
                    if "com.xingin.xhs" not in current_focus:
                        ctrl.start_xiaohongshu()
                        await asyncio.sleep(3)
                except Exception as e:
                    print(f"检查前台应用失败: {e}")

            # 2. 点击"我" tab进入个人页面
            me_tab_x = int(display.width * 0.875)  # 底部最右侧
            me_tab_y = int(display.height * 0.96)
            ctrl.click(me_tab_x, me_tab_y)
            await asyncio.sleep(2)

            # 3. 检查是否已经登录（如果有头像/用户名说明已登录）
            # TODO: 实现更准确的登录状态检测，当前简化处理
            screenshot = ctrl.take_screenshot()
            is_logged_in = await self._check_login_state(screenshot)
            if is_logged_in:
                print(f"账号 {account.account} 已经登录")
                self.update_account_status(account.account, AccountStatus.LOGGED_IN)
                return True

            # 4. 点击登录/注册按钮
            login_btn_x = int(display.width * 0.5)
            login_btn_y = int(display.height * 0.6)
            ctrl.click(login_btn_x, login_btn_y)
            await asyncio.sleep(2)

            # 5. 选择手机号登录
            phone_login_x = int(display.width * 0.3)
            phone_login_y = int(display.height * 0.3)
            ctrl.click(phone_login_x, phone_login_y)
            await asyncio.sleep(1)

            # 6. 点击手机号输入框
            phone_input_x = int(display.width * 0.5)
            phone_input_y = int(display.height * 0.4)
            ctrl.click(phone_input_x, phone_input_y)
            await asyncio.sleep(0.5)

            # 7. 清空输入框并输入手机号
            ctrl.clear_input()
            await asyncio.sleep(0.5)
            ctrl.input_text(account.account)
            await asyncio.sleep(0.5)

            # 8. 点击密码输入框
            password_input_x = int(display.width * 0.5)
            password_input_y = int(display.height * 0.5)
            ctrl.click(password_input_x, password_input_y)
            await asyncio.sleep(0.5)

            # 9. 输入密码
            ctrl.clear_input()
            await asyncio.sleep(0.5)
            ctrl.input_text(account.password)
            await asyncio.sleep(0.5)

            # 10. 点击登录按钮
            login_submit_x = int(display.width * 0.5)
            login_submit_y = int(display.height * 0.7)
            ctrl.click(login_submit_x, login_submit_y)
            await asyncio.sleep(3)

            # 11. 检查是否需要验证码
            screenshot = ctrl.take_screenshot()
            need_verification = await self._check_verification_required(screenshot)
            if need_verification:
                print(f"账号 {account.account} 登录需要验证码")
                self.update_account_status(account.account, AccountStatus.VERIFICATION_REQUIRED)
                # 触发人工告警
                from ai_agent.human_alert import trigger_human_alert
                await trigger_human_alert(
                    device_id=ctrl.device_id,
                    reason=f"账号 {account.account} 登录需要验证码，请输入验证码后继续",
                    screenshot_base64=screenshot
                )
                # 等待人工输入完成后继续
                await asyncio.sleep(5)
                # 重新检查登录状态
                screenshot = ctrl.take_screenshot()
                is_logged_in = await self._check_login_state(screenshot)
                if not is_logged_in:
                    print(f"账号 {account.account} 验证码输入后登录失败")
                    self.update_account_status(account.account, AccountStatus.ERROR)
                    return False

            # 12. 登录成功
            print(f"账号 {account.account} 登录成功")
            self.update_account_status(account.account, AccountStatus.LOGGED_IN)
            return True

        except Exception as e:
            print(f"自动登录失败: {e}")
            self.update_account_status(account.account, AccountStatus.ERROR)
            return False

    async def validate_login_state(self, device_controller, account: Account) -> bool:
        """校验登录状态是否有效
        Returns:
            True表示已登录，False表示需要重新登录
        """
        try:
            ctrl = device_controller
            display = ctrl.display_info

            # 点击"我" tab
            me_tab_x = int(display.width * 0.875)
            me_tab_y = int(display.height * 0.96)
            ctrl.click(me_tab_x, me_tab_y)
            await asyncio.sleep(1)

            # 截图检查登录状态
            screenshot = ctrl.take_screenshot()
            is_logged_in = await self._check_login_state(screenshot)

            if is_logged_in:
                print(f"账号 {account.account} 登录状态有效")
                return True
            else:
                print(f"账号 {account.account} 登录状态已失效")
                self.update_account_status(account.account, AccountStatus.INACTIVE)
                return False

        except Exception as e:
            print(f"登录状态校验失败: {e}")
            return False

    async def _check_login_state(self, screenshot: bytes) -> bool:
        """检查是否已经登录
        通过截图识别是否有登录按钮/用户名等元素
        TODO: 实现更准确的图像识别，当前简化返回True
        """
        # 暂时简化处理，默认认为已登录
        # 实际项目中可以使用模板匹配/OCR识别用户名是否存在
        return True

    async def _check_verification_required(self, screenshot: bytes) -> bool:
        """检查是否需要验证码
        通过截图识别是否有验证码输入框等元素
        TODO: 实现更准确的图像识别，当前简化返回False
        """
        # 暂时简化处理，默认不需要验证码
        return False

    async def switch_account(self, device_controller, current_account: Account) -> Optional[Account]:
        """切换到下一个账号
        Args:
            device_controller: 设备控制器实例
            current_account: 当前登录的账号
        Returns:
            新登录的账号，如果切换失败返回None
        """
        try:
            ctrl = device_controller
            print(f"开始切换账号，当前账号: {current_account.account}")

            # 1. 退出当前账号
            await self._logout(ctrl)
            await asyncio.sleep(2)

            # 2. 获取下一个账号
            next_account = self.get_next_account()
            print(f"切换到新账号: {next_account.account}")

            # 3. 登录新账号
            login_success = await self.auto_login(ctrl, next_account)
            if not login_success:
                print(f"新账号 {next_account.account} 登录失败")
                return None

            print(f"账号切换成功，从 {current_account.account} 切换到 {next_account.account}")
            return next_account

        except Exception as e:
            print(f"账号切换失败: {e}")
            return None

    async def _logout(self, device_controller) -> bool:
        """退出当前登录的账号
        Args:
            device_controller: 设备控制器实例
        Returns:
            退出是否成功
        """
        try:
            ctrl = device_controller
            display = ctrl.display_info

            # 1. 进入"我"页面
            me_tab_x = int(display.width * 0.875)
            me_tab_y = int(display.height * 0.96)
            ctrl.click(me_tab_x, me_tab_y)
            await asyncio.sleep(1)

            # 2. 点击设置按钮（通常在右上角）
            settings_x = int(display.width * 0.92)
            settings_y = int(display.height * 0.07)
            ctrl.click(settings_x, settings_y)
            await asyncio.sleep(1)

            # 3. 滑动到页面底部，找到退出登录按钮
            ctrl.swipe(
                int(display.width * 0.5),
                int(display.height * 0.8),
                int(display.width * 0.5),
                int(display.height * 0.2),
                500
            )
            await asyncio.sleep(1)

            # 4. 点击退出登录按钮
            logout_x = int(display.width * 0.5)
            logout_y = int(display.height * 0.75)
            ctrl.click(logout_x, logout_y)
            await asyncio.sleep(1)

            # 5. 确认退出
            confirm_x = int(display.width * 0.6)
            confirm_y = int(display.height * 0.6)
            ctrl.click(confirm_x, confirm_y)
            await asyncio.sleep(2)

            print("退出登录成功")
            return True

        except Exception as e:
            print(f"退出登录失败: {e}")
            return False

    def get_next_account(self) -> Account:
        """获取下一个要切换的账号（轮询算法）"""
        # 获取所有活跃账号
        active_accounts = self.get_active_accounts()
        if not active_accounts:
            raise ValueError("没有可用的活跃账号")

        # 循环查找下一个账号
        current_idx = 0
        for i, acc in enumerate(active_accounts):
            if acc.account == self._last_account:
                current_idx = (i + 1) % len(active_accounts)
                break

        self._last_account = active_accounts[current_idx].account
        return active_accounts[current_idx]


# Global instance
_account_pool: AccountPool = None


def get_account_pool() -> AccountPool:
    global _account_pool
    if _account_pool is None:
        config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "accounts.yaml")
        _account_pool = AccountPool(config_path)
    return _account_pool
