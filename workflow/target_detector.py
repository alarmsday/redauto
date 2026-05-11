"""目标用户识别模块

策略：
1. 优先使用 EasyOCR 本地识别（安装后）
2. LLM兜底（已验证可用的成熟方案）
"""

import asyncio
import base64
import re
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass

# OCR引擎
_use_easyocr = True
_ocr_engine = None


def _init_easyocr():
    """初始化EasyOCR"""
    global _ocr_engine, _use_easyocr
    if _ocr_engine is None and _use_easyocr:
        try:
            import easyocr
            _ocr_engine = easyocr.Reader(['ch_sim', 'en'])
            print("[目标识别] EasyOCR 初始化成功")
        except Exception as e:
            print(f"[目标识别] EasyOCR 初始化失败: {e}")
            _use_easyocr = False


async def local_ocr_text(screenshot: bytes) -> List[str]:
    """
    使用本地OCR提取文字

    Args:
        screenshot: 截图bytes

    Returns:
        识别出的文字列表
    """
    if not _use_easyocr:
        return []

    # 初始化（如果还没初始化）
    _init_easyocr()
    if _ocr_engine is None:
        return []

    try:
        import numpy as np
        import cv2

        # 将bytes转为numpy数组
        nparr = np.frombuffer(screenshot, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if img is None:
            return []

        # 直接传numpy数组，不需要临时文件
        results = _ocr_engine.readtext(img)

        texts = []
        for bbox, text, confidence in results:
            if text and confidence > 0.3:
                texts.append(text)

        if texts:
            print(f"[目标识别] EasyOCR 识别到 {len(texts)} 段文字")
        return texts

    except Exception as e:
        print(f"[目标识别] EasyOCR 识别失败: {e}")
        return []


def _normalize_text(text: str) -> str:
    """
    标准化文本用于匹配

    处理emoji和特殊字符
    """
    import unicodedata
    # 移除emoji表情符号（保留文字）
    cleaned = []
    for char in text:
        if unicodedata.category(char)[0] != 'So':  # 不是符号
            cleaned.append(char)
        elif char in [' ', '...', '…']:  # 保留常见分隔符
            cleaned.append(char)
    return ''.join(cleaned).strip()


def _match_nickname(nickname: str, text: str, match_mode: str) -> bool:
    """
    匹配昵称和识别出的文本

    处理截断情况：首页显示的昵称可能被截断（通常显示前6-10个字符）
    匹配策略（fuzzy模式）：
    1. 完全相等
    2. OCR文本是昵称的前缀（昵称被截断，至少2字符）
    3. 昵称是OCR文本的前缀（昵称短，OCR识别到昵称+后续文字）
    4. 前3个字符相同（足够长的前缀才能确认是同一个昵称）
    """
    # 过滤：纯数字不是昵称（如点赞数、粉丝数）
    if text.strip().isdigit():
        return False

    if match_mode == "exact":
        return nickname.strip() == text.strip()

    # fuzzy模式
    nick = nickname.strip()
    txt = text.strip()

    if not nick or not txt:
        return False

    # 策略1：完全相等
    if nick == txt:
        return True

    # 策略2：OCR文本是昵称的前缀（昵称被截断）
    # 要求至少2个字符，避免单字误匹配
    if nick.startswith(txt) and len(txt) >= 2:
        return True

    # 策略3：昵称是OCR文本的前缀（昵称短，OCR识别到昵称+后续文字）
    if txt.startswith(nick) and len(nick) >= 2:
        return True

    # 策略4：前3个字符相同（足够长的前缀才能确认）
    prefix_len = min(3, len(nick), len(txt))
    if prefix_len >= 3:
        nick_prefix = nick[:prefix_len]
        txt_prefix = txt[:prefix_len]
        if nick_prefix == txt_prefix:
            return True

    return False


def match_target_user(texts: List[str], target_users: List["TargetUser"]) -> Tuple[bool, Optional["TargetUser"]]:
    """在识别出的文字中匹配目标用户"""
    for text in texts:
        for user in target_users:
            if _match_nickname(user.nickname, text, user.match_mode):
                return True, user
    return False, None


@dataclass
class TargetUser:
    """目标用户"""
    xiaohongshu_id: str
    nickname: str
    match_mode: str  # "exact" or "fuzzy"
    daily_like_limit: int = 3  # 每日点赞收藏上限


def load_target_users() -> List[TargetUser]:
    """从Excel配置文件加载目标用户"""
    try:
        import openpyxl
        import os

        excel_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "targets.xlsx")
        wb = openpyxl.load_workbook(excel_path)
        ws = wb.active

        users = []
        for row in ws.iter_rows(min_row=2, values_only=True):  # skip header
            nickname = row[2]  # 昵称 column
            if nickname is None or str(nickname).strip() == '':
                continue

            users.append(TargetUser(
                xiaohongshu_id=str(row[1]) if row[1] else "",  # 小红书号
                nickname=str(nickname).strip(),
                match_mode=str(row[3]).strip() if row[3] else "fuzzy",  # 匹配模式
                daily_like_limit=int(row[4]) if row[4] else 3  # 每日点赞收藏上限
            ))

        wb.close()
        print(f"[目标识别] 从Excel加载 {len(users)} 个目标用户")
        return users
    except Exception as e:
        print(f"[目标识别] 加载配置失败: {e}")
        return []


async def check_discovery_page_for_targets(
    screenshot: bytes,
    target_users: List[TargetUser]
) -> Tuple[bool, Optional[Dict]]:
    """
    检查发现页截图是否包含目标用户

    优先使用本地OCR（EasyOCR），失败时使用LLM兜底

    Args:
        screenshot: 截图bytes
        target_users: 目标用户列表

    Returns:
        (found, target_info) - 是否找到目标用户及信息
    """
    if not target_users:
        return False, None

    # 1. 尝试使用本地EasyOCR
    texts = await local_ocr_text(screenshot)
    if texts:
        found, user = match_target_user(texts, target_users)
        if found:
            print(f"[目标识别] 本地OCR找到目标用户: {user.nickname}")
            return True, {
                'user_id': user.xiaohongshu_id or user.nickname,
                'nickname': user.nickname,
                'post_id': f'post_{hash(user.nickname) % 10000}',
                'is_video': False
            }

    # 2. LLM兜底
    print("[目标识别] 使用LLM检测目标用户...")
    return await _check_with_llm(screenshot, target_users)


async def _check_with_llm(
    screenshot: bytes,
    target_users: List[TargetUser]
) -> Tuple[bool, Optional[Dict]]:
    """使用LLM检查目标用户"""
    from ai_agent.llm_client import call_llm_with_limit

    nicknames = [u.nickname for u in target_users]
    nicknames_str = "、".join(nicknames)

    prompt = f"""这是小红书发现页截图。请检查是否显示以下目标用户的内容：
{nicknames_str}

注意：
1. 首页显示的昵称可能被截断（只显示前几个字符）
2. 昵称可能包含emoji表情符号
3. fuzzy模式：即使只匹配昵称的前几个字符也可视为匹配

请返回JSON格式：
{{"found": true/false, "nickname": "匹配到的用户名（完整昵称）"}}

如果没有找到任何目标用户，返回：{{"found": false}}"""

    try:
        response = await call_llm_with_limit(
            prompt=prompt,
            image_base64=base64.b64encode(screenshot).decode()
        )

        match = re.search(r'\{[^}]+\}', response)
        if match:
            import json
            result = json.loads(match.group())
            if result.get("found"):
                matched_nickname = result.get("nickname", "")
                # 使用改进的匹配逻辑
                for u in target_users:
                    if _match_nickname(u.nickname, matched_nickname, u.match_mode):
                        return True, {
                            'user_id': u.xiaohongshu_id or u.nickname,
                            'nickname': u.nickname,
                            'post_id': f'post_{hash(matched_nickname) % 10000}',
                            'is_video': False
                        }
        return False, None

    except Exception as e:
        print(f"[目标识别] LLM检测失败: {e}")
        return False, None


# 单例缓存
_cached_targets: Optional[List[TargetUser]] = None


def get_target_users() -> List[TargetUser]:
    """获取目标用户列表（带缓存）"""
    global _cached_targets
    if _cached_targets is None:
        _cached_targets = load_target_users()
    return _cached_targets


def reload_targets():
    """重新加载目标用户配置"""
    global _cached_targets
    _cached_targets = None
