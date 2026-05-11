"""生产流程测试 - 只跑10轮，加flush"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from workflow.xiaohongshu import XiaohongshuWorkflow

# 强制stdout不缓冲
import functools
print = functools.partial(print, flush=True)

async def main():
    wf = XiaohongshuWorkflow(device_id='NABDU20330005550', test_mode=False)
    ctrl = wf._get_controller()
    if not ctrl.is_connected():
        ctrl.connect()

    await wf._ensure_xiaohongshu_loaded()

    print('[1] 确保在发现页...')
    await wf._ensure_discovery_page()

    on_page = await wf._is_on_discovery_page()
    print(f'    页面状态: {"发现页" if on_page else "同城页"}')

    # 主循环 - 最多10轮
    for i in range(10):
        print(f'\n=== 第 {i+1}/10 轮 ===')

        # 纠错
        on_page = await wf._is_on_discovery_page()
        if not on_page:
            print('    不在发现页，纠错...')
            await wf._ensure_discovery_page()

        # 滑动查找目标
        target_info = await wf._find_target_post()

        if target_info is None:
            print('    当前页无目标用户，滑动...')
            await wf._random_scroll()
            await asyncio.sleep(2)
            continue

        print(f'    找到目标: {target_info["nickname"]}')

        # 进入帖子
        await wf._enter_post(target_info)

        # 浏览
        await wf._browse_post()

        # 点赞收藏
        await wf._like_and_collect()

        # 返回
        await wf._return_to_discovery()

        # 返回后纠错
        on_page = await wf._is_on_discovery_page()
        if not on_page:
            print('    返回后不在发现页，纠错...')
            await wf._ensure_discovery_page()

        print(f'    第{i+1}轮完成')
        await asyncio.sleep(2)

    print('\n生产流程测试结束!')

if __name__ == "__main__":
    asyncio.run(main())
