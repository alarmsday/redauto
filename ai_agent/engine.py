"""AI Agent执行引擎 - 核心模块"""

import asyncio
import json
import base64
import hashlib
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum
from threading import Semaphore
import traceback

from data.shared_state import (
    find_exact_match, find_similar_case,
    add_case, increment_case_usage, mark_case_failed,
    record_operation
)
from ai_agent.llm_client import call_llm_with_limit
from ai_agent.action_validator import validate_action, ActionValidationError
from ai_agent.executor import execute_action
from ai_agent.self_learner import SelfLearner
from ai_agent.human_alert import trigger_human_alert


class ExceptionType(Enum):
    UI_ELEMENT_NOT_FOUND = "ui_element_not_found"
    PAGE_LOAD_TIMEOUT = "page_load_timeout"
    UNKNOWN_POPUP = "unknown_popup"
    NETWORK_ERROR = "network_error"
    APP_CRASH = "app_crash"
    ACCOUNT_LIMITED = "account_limited"
    VERIFICATION_REQUIRED = "verification_required"
    UNKNOWN = "unknown"


@dataclass
class ExceptionContext:
    exception_type: ExceptionType
    description: str
    retry_count: int
    screenshot_base64: str
    screen_hash: str
    control_tree: str
    recent_logs: list


class AIAgentEngine:
    """AI Agent执行引擎"""

    def __init__(self, device_id: str, max_retries: int = 3):
        self.device_id = device_id
        self.max_retries = max_retries
        self.self_learner = SelfLearner()
        self._consecutive_failures = 0
        self._current_exception: Optional[ExceptionContext] = None

    async def handle_exception(
        self,
        exception_type: ExceptionType,
        description: str,
        screenshot_func: Callable[[], bytes],
        control_tree_func: Callable[[], str],
        logs_func: Callable[[], list],
        operation_context: Dict[str, Any] = None
    ) -> bool:
        """
        处理异常的入口函数

        Args:
            exception_type: 异常类型
            description: 异常描述
            screenshot_func: 获取屏幕截图的函数
            control_tree_func: 获取控件树的函数
            logs_func: 获取最近日志的函数
            operation_context: 操作上下文

        Returns:
            True if exception was handled successfully
        """
        self._consecutive_failures += 1

        # 1. 采集异常上下文
        screenshot = screenshot_func()
        screenshot_b64 = base64.b64encode(screenshot).decode()
        screen_hash = hashlib.sha256(screenshot).hexdigest()
        control_tree = control_tree_func()
        recent_logs = logs_func()

        context = ExceptionContext(
            exception_type=exception_type,
            description=description,
            retry_count=self._consecutive_failures,
            screenshot_base64=screenshot_b64,
            screen_hash=screen_hash,
            control_tree=control_tree,
            recent_logs=recent_logs
        )
        self._current_exception = context

        # 2. 案例库检索
        case = self._search_case_library(screen_hash, exception_type.value)
        if case:
            action = json.loads(case['action_taken'])
            if await self._apply_action(action, context):
                return True
            # 案例失败，更新并继续
            mark_case_failed(case['id'])

        # 3. 调用LLM获取决策
        if self._consecutive_failures >= self.max_retries:
            # 超过最大重试次数，触发人工告警
            await self._trigger_human_intervention(context, operation_context)
            return False

        action = await self._get_llm_decision(context)
        if not action:
            return False

        # 4. 执行action
        if await self._apply_action(action, context):
            # 5. 记录成功案例
            await self._record_success_case(context, action)
            self._consecutive_failures = 0
            return True

        return False

    def _search_case_library(self, screen_hash: str, exception_type: str) -> Optional[Dict[str, Any]]:
        """搜索案例库"""
        # 精确匹配
        case = find_exact_match(screen_hash)
        if case:
            increment_case_usage(case['id'])
            return case

        # 相似匹配
        case = find_similar_case(exception_type)
        if case:
            increment_case_usage(case['id'])
            return case

        return None

    async def _get_llm_decision(self, context: ExceptionContext) -> Optional[Dict[str, Any]]:
        """调用LLM获取决策"""
        prompt = self._build_prompt(context)

        try:
            response = await call_llm_with_limit(
                prompt=prompt,
                image_base64=context.screenshot_base64
            )

            # 解析JSON响应
            action = self._parse_llm_response(response)
            if action and validate_action(action):
                return action

            # 无效响应，重试
            return None

        except asyncio.TimeoutError:
            # 超时，降级为预设策略
            return self._get_fallback_action(context.exception_type)
        except Exception as e:
            print(f"LLM调用失败: {e}")
            traceback.print_exc()
            return None

    def _build_prompt(self, context: ExceptionContext) -> str:
        """构建LLM提示词"""
        logs_text = "\n".join([f"- {log}" for log in context.recent_logs[-10:]])

        return f"""你是小红书自动化运营系统的AI执行引擎。你的职责是在自动化流程遇到异常时，根据提供的屏幕截图、控件树信息、操作日志，分析当前状态，给出下一步操作指令。

【当前异常上下文】
- 异常类型：{context.exception_type.value}
- 异常描述：{context.description}
- 已重试次数：{context.retry_count}/{self.max_retries}

【最近操作日志】
{logs_text}

【可用操作指令】（只返回JSON，不要其他内容）
{{"action": "click", "x": 数字, "y": 数字}} - 点击屏幕坐标
{{"action": "swipe", "x1": 数字, "y1": 数字, "x2": 数字, "y2": 数字, "duration": 数字}} - 滑动屏幕
{{"action": "back"}} - 返回上一页
{{"action": "restart_app"}} - 重启小红书APP
{{"action": "wait", "seconds": 数字}} - 等待N秒
{{"action": "human_alert", "reason": "原因描述"}} - 触发人工告警
{{"action": "skip", "reason": "跳过原因"}} - 跳过当前任务

【决策规则】
1. 优先尝试关闭弹窗（广告、更新提示等）
2. 如果页面加载卡住，先等待，仍无变化则返回重新进入
3. 如果找不到目标控件，尝试滑动页面后重新查找
4. 连续3次相同操作失败，触发人工告警
5. 只操作目标用户帖子，不要随意操作其他内容

请分析截图和控件树，返回下一步应该执行的指令（JSON格式）。
"""

    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """解析LLM响应"""
        try:
            # 尝试提取JSON
            if "```json" in response:
                response = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                response = response.split("```")[1].split("```")[0]

            response = response.strip()
            return json.loads(response)
        except json.JSONDecodeError:
            return None

    def _get_fallback_action(self, exception_type: ExceptionType) -> Dict[str, Any]:
        """获取降级策略"""
        fallback_map = {
            ExceptionType.UI_ELEMENT_NOT_FOUND: {"action": "swipe", "x1": 360, "y1": 800, "x2": 360, "y2": 400, "duration": 300},
            ExceptionType.PAGE_LOAD_TIMEOUT: {"action": "wait", "seconds": 3},
            ExceptionType.UNKNOWN_POPUP: {"action": "back"},
            ExceptionType.NETWORK_ERROR: {"action": "wait", "seconds": 5},
            ExceptionType.APP_CRASH: {"action": "restart_app"},
            ExceptionType.ACCOUNT_LIMITED: {"action": "human_alert", "reason": "账号被限制"},
            ExceptionType.VERIFICATION_REQUIRED: {"action": "human_alert", "reason": "需要验证码"},
        }
        return fallback_map.get(exception_type, {"action": "wait", "seconds": 2})

    async def _apply_action(self, action: Dict[str, Any], context: ExceptionContext) -> bool:
        """应用action"""
        try:
            result = await execute_action(action, self.device_id)
            return result

        except ActionValidationError as e:
            print(f"Action校验失败: {e}")
            return False
        except Exception as e:
            print(f"Action执行失败: {e}")
            traceback.print_exc()
            return False

    async def _record_success_case(self, context: ExceptionContext, action: Dict[str, Any]):
        """记录成功案例"""
        try:
            add_case(
                exception_type=context.exception_type.value,
                screen_hash=context.screen_hash,
                control_tree=context.control_tree,
                action_taken=json.dumps(action),
                success=True,
                context_summary=context.description
            )
        except Exception as e:
            print(f"记录成功案例失败: {e}")

    async def _trigger_human_intervention(self, context: ExceptionContext,
                                          operation_context: Dict[str, Any] = None):
        """触发人工干预"""
        reason = f"设备{self.device_id}连续{self.max_retries}次异常处理失败\n" \
                f"异常类型: {context.exception_type.value}\n" \
                f"异常描述: {context.description}\n" \
                f"最后操作: {context.recent_logs[-1] if context.recent_logs else 'N/A'}"

        await trigger_human_alert(
            device_id=self.device_id,
            reason=reason,
            screenshot_base64=context.screenshot_base64,
            operation_context=operation_context
        )

    def reset_failure_count(self):
        """重置失败计数"""
        self._consecutive_failures = 0


# 全局限流信号量
llm_semaphore = Semaphore(3)
