"""LLM调用模块 - 支持火山引擎豆包(OpenAI兼容接口)"""

import asyncio
import os
import json
from typing import Optional


# 全局限流信号量，最多3个并发LLM调用
llm_semaphore = asyncio.Semaphore(3)


def get_llm_config() -> dict:
    """从配置文件获取LLM配置"""
    try:
        import yaml
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "configs", "system.yaml"
        )
        with open(config_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
            return data.get('llm', {})
    except Exception:
        pass

    # 默认配置
    return {
        'api_key': os.environ.get('LLM_API_KEY', ''),
        'base_url': os.environ.get('LLM_BASE_URL', 'https://ark.cn-beijing.volces.com/api/coding/v1'),
        'model': os.environ.get('LLM_MODEL', 'Doubao-Seed-2.0-pro'),
        'max_tokens': 1000
    }


def create_llm_client():
    """创建LLM客户端"""
    config = get_llm_config()

    try:
        from openai import OpenAI
        client = OpenAI(
            api_key=config.get('api_key', ''),
            base_url=config.get('base_url', 'https://ark.cn-beijing.volces.com/api/coding/v1')
        )
        return client
    except ImportError:
        print("[LLM] OpenAI package not installed. Run: pip install openai")
        return None


# 全局客户端实例
_llm_client = None
_client_lock = asyncio.Lock()


async def get_llm_client():
    """获取LLM客户端（异步创建）"""
    global _llm_client
    if _llm_client is None:
        async with _client_lock:
            if _llm_client is None:
                _llm_client = create_llm_client()
    return _llm_client


async def call_llm_with_limit(
    prompt: str,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    带限流的LLM调用

    Args:
        prompt: 用户提示词
        image_base64: 图片base64编码（可选）
        system_prompt: 系统提示词（可选）

    Returns:
        LLM响应文本
    """
    async with llm_semaphore:
        return await _call_llm(prompt, image_base64, system_prompt)


async def _call_llm(
    prompt: str,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None
) -> str:
    """
    实际LLM调用实现
    """
    config = get_llm_config()
    client = await get_llm_client()

    if client is None:
        raise RuntimeError("LLM client not available")

    # 构建消息
    messages = []

    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})

    if image_base64:
        # 图片+文本输入
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{image_base64}"
                }
            }
        ]
    else:
        # 纯文本输入
        content = prompt

    messages.append({"role": "user", "content": content})

    try:
        # 超时控制
        response = await asyncio.wait_for(
            asyncio.to_thread(
                client.chat.completions.create,
                model=config.get('model', 'Doubao-Seed-2.0-pro'),
                messages=messages,
                max_tokens=config.get('max_tokens', 1000)
            ),
            timeout=config.get('llm_timeout', 30)
        )

        return response.choices[0].message.content

    except asyncio.TimeoutError:
        print(f"[LLM] LLM调用超时（{config.get('llm_timeout', 30)}秒）")
        raise
    except Exception as e:
        print(f"[LLM] LLM调用异常: {e}")
        raise


async def call_llm_with_retry(
    prompt: str,
    image_base64: Optional[str] = None,
    system_prompt: Optional[str] = None,
    max_retries: int = 2
) -> Optional[str]:
    """
    带重试的LLM调用

    Args:
        prompt: 提示词
        image_base64: 图片base64编码（可选）
        system_prompt: 系统提示词（可选）
        max_retries: 最大重试次数

    Returns:
        LLM响应文本，失败返回None
    """
    for attempt in range(max_retries + 1):
        try:
            return await call_llm_with_limit(prompt, image_base64, system_prompt)
        except asyncio.TimeoutError:
            if attempt < max_retries:
                print(f"LLM调用超时，重试第{attempt + 1}次...")
                await asyncio.sleep(1)
            else:
                print("LLM调用失败，已达到最大重试次数")
                return None
        except Exception as e:
            print(f"LLM调用异常: {e}")
            if attempt < max_retries:
                await asyncio.sleep(1)
            else:
                return None

    return None


async def test_llm_connection() -> bool:
    """测试LLM连接"""
    try:
        response = await call_llm_with_limit("Say 'OK' in one word")
        success = response and 'ok' in response.lower()
        print(f"[LLM] Connection test: {'SUCCESS' if success else 'FAILED'}")
        return success
    except Exception as e:
        print(f"[LLM] Connection test FAILED: {e}")
        return False
