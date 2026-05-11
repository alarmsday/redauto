## Context

**项目背景**：小红书多设备自动化运营系统，实现10台以内安卓设备并发自动化操作小红书，完成发现页目标用户帖子的自动识别、点赞、收藏、截图等操作。内置AI Agent引擎自主处理执行过程中的异常卡壳情况。

**技术栈**：
- Python 3.10+ / AirTest / Poco / ADB
- PaddleOCR 本地版
- 火山引擎豆包 Seed 2.0 Pro (volcengine/doubao-seed-2-0-pro-260215)
- Flask + Vue3 监控面板
- multiprocessing 多进程调度
- SQLite（进程间共享数据）
- asyncio（异步状态推送）

**约束条件**：
- 仅支持安卓设备，无需ROOT
- 单设备独立进程，CPU占用≤30%，内存≤8GB
- 使用OpenClaw现有模型配置

## Goals / Non-Goals

**Goals:**
- 实现多设备并发执行任务，支持轮询分配策略
- 实现小红书核心业务流程：发现页用户识别、帖子浏览、点赞收藏
- 实现AI Agent执行引擎，异常自动处理无需人工介入
- 实现真人操作模拟，降低被识别风险
- 实现可视化监控面板和统计报告

**Non-Goals:**
- 不支持iOS设备
- 不支持自动评论、关注、私信
- 不支持定时任务
- 不支持多平台扩展（抖音、快手等）

## Decisions

### 1. 多设备并发架构
**决策**：采用 multiprocessing 单进程单设备模式 + SQLite共享数据
**原因**：进程隔离避免设备间相互干扰，SQLite支持多进程读写且无需额外服务
**替代方案**：考虑过asyncio/threading，但Android设备控制涉及socket长连接，进程隔离更稳定

### 2. 设备控制框架
**决策**：使用 AirTest + Poco
**原因**：国内团队开发对小红书等国内APP适配好，无需ROOT，支持Poco UI控件识别
**替代方案**：考虑Appium但对国内APP适配不如AirTest

### 3. OCR识别
**决策**：使用 PaddleOCR 本地版
**原因**：中文识别准确率高，本地运行无需调用外部API，延迟低
**替代方案**：考虑百度OCR/腾讯OCR，但需要网络调用和额外申请

### 4. AI决策方案
**决策**：火山引擎豆包 Seed 2.0 Pro，通过OpenClaw环境调用
**原因**：已配置在OpenClaw环境中，无需额外申请API，支持图片输入理解
**替代方案**：考虑GPT-4V但需要额外API配置和成本

### 5. 异常处理策略
**决策**：已知异常预设规则自动处理，未知异常交给AI Agent
**原因**：平衡处理速度和泛化能力，常见弹窗预设规则高效处理，AI Agent处理未知情况
**替代方案**：考虑全部交给AI Agent但响应延迟高、成本高

### 6. 存储方案
**决策**：本地文件系统存储截图/日志 + SQLite存储共享状态
**原因**：截图日志量大用文件，跨进程共享状态用SQLite
**替代方案**：考虑Redis但增加部署复杂度无明显收益

### 7. 进程间通信方案
**决策**：SQLite + asyncio.WebSocket推送
**原因**：
- SQLite多进程安全，支持并发读写
- asyncio推送状态到Web面板，无需轮询
- 无需额外消息队列服务

### 8. LLM并发控制
**决策**：Semaphore信号量限制并发数
**原因**：限制同时调用LLM的进程数，避免API限流
**替代方案**：考虑独立LLM调用服务但增加复杂度

## AI Agent 执行引擎详细设计

### 8.1 系统提示词模板

```
你是小红书自动化运营系统的AI执行引擎。你的职责是在自动化流程遇到异常时，根据提供的屏幕截图、控件树信息、操作日志，分析当前状态，给出下一步操作指令。

【当前异常上下文】
- 异常类型：{exception_type}
- 异常描述：{exception_description}
- 已重试次数：{retry_count}/3

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
```

### 8.2 案例库设计

**存储格式**：SQLite数据库 `case_library.db`

```sql
CREATE TABLE cases (
    id INTEGER PRIMARY KEY,
    exception_type TEXT,           -- 异常类型
    screen_hash TEXT,              -- 屏幕截图hash（快速比对）
    screen_embedding BLOB,         -- 截图特征向量（用于相似度检索）
    control_tree TEXT,             -- 控件树快照
    context_summary TEXT,          -- 上下文摘要
    action_taken TEXT,             -- 采取的行动（JSON）
    success BOOLEAN,               -- 是否成功
    created_at TIMESTAMP,
    used_count INTEGER DEFAULT 0   -- 使用次数
);

CREATE INDEX idx_exception_type ON cases(exception_type);
CREATE INDEX idx_screen_hash ON cases(screen_hash);
```

**检索算法**：
1. 精确匹配：screen_hash完全相同 → 直接使用
2. 相似度匹配：exception_type相同 + screen_embedding余弦相似度 > 0.85 → 使用最成功案例
3. 新案例：无可用案例时调用LLM

**更新机制**：
- 成功案例：used_count + 1
- 失败案例：标记success=false，后续检索时降低优先级
- 定期清理：used_count < 3 且创建超过30天的案例可考虑淘汰

### 8.3 LLM调用限流

```python
import asyncio
from threading import Semaphore

# 全局限流信号量，最多3个并发LLM调用
llm_semaphore = Semaphore(3)

async def call_llm_with_limit(prompt, image_base64):
    async with llm_semaphore:
        # 调用LLM，5秒超时
        result = await asyncio.wait_for(
            openclaw_llm_service.generate(prompt, image=image_base64),
            timeout=5.0
        )
        return result
```

### 8.4 AI决策校验与回滚

**校验层**：执行前必须通过校验
```python
VALID_ACTIONS = {"click", "swipe", "back", "restart_app", "wait", "human_alert", "skip"}
VALID_RANGES = {
    "x": (0, 1440), "y": (0, 3200),  # 根据设备分辨率
    "duration": (100, 2000)
}

def validate_action(action: dict) -> bool:
    if action.get("action") not in VALID_ACTIONS:
        return False
    if action["action"] == "click":
        return validate_coords(action, ["x", "y"])
    if action["action"] == "swipe":
        return validate_coords(action, ["x1", "y1", "x2", "y2"]) and \
               VALID_RANGES["duration"][0] <= action.get("duration", 0) <= VALID_RANGES["duration"][1]
    return True
```

**回滚机制**：
- 不支持真正的"回滚"（点击无法撤销）
- 记录每个操作到日志，失败时记录并跳过
- 连续3次AI决策失败，触发人工告警而非继续尝试

## 多进程通信设计

### 9.1 共享数据结构（SQLite）

```sql
-- 任务队列
CREATE TABLE task_queue (
    id INTEGER PRIMARY KEY,
    target_user_id TEXT,
    target_nickname TEXT,
    device_id TEXT,
    status TEXT,  -- pending/running/completed/failed
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 操作记录（用于频率控制）
CREATE TABLE operation_records (
    id INTEGER PRIMARY KEY,
    target_user_id TEXT,
    device_id TEXT,
    operation_type TEXT,
    operated_at TIMESTAMP
);

-- 设备状态
CREATE TABLE device_status (
    device_id TEXT PRIMARY KEY,
    status TEXT,  -- online/offline/running/error
    current_task_id INTEGER,
    last_heartbeat TIMESTAMP
);
```

### 9.2 进程间状态推送（asyncio）

```python
# 主控进程运行WebSocket服务器
async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    subscribers.add(ws)
    try:
        async for msg in ws:
            pass
    finally:
        subscribers.remove(ws)

# 设备进程上报状态
async def report_status(device_id, status, progress):
    payload = json.dumps({
        "device_id": device_id,
        "status": status,
        "progress": progress,
        "timestamp": datetime.now().isoformat()
    })
    for ws in subscribers:
        await ws.send_str(payload)
```

## Risks / Trade-offs

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 小红书版本更新UI变化 | 控件识别失败 | AI Agent自动适配，定期更新识别规则 |
| 账号被限流/封禁 | 无法继续操作 | 反爬策略保护，新账号养号7天 |
| 设备批量断开 | 任务中断 | 独立供电USB集线器，自动重连机制 |
| OCR识别准确率低 | 用户匹配失败 | 裁剪优化区域，AI Agent辅助识别 |
| LLM调用限流导致等待 | 异常处理延迟 | 3秒超时降级为预设策略 |
| 案例库检索不准确 | AI决策错误 | 3次失败触发人工告警 |

## Open Questions

1. 设备连接稳定性：WiFi连接 vs USB连接的实际稳定性需要测试验证
2. AI Agent决策准确率：需要实际运行测试后优化提示词
3. 账号登录验证码频率：验证码触发人工提醒的频率需要实际观察
4. 系统容量上限：10台并发是目标上限，实际最佳并发数需要压测确定
5. 火山引擎豆包模型是否支持function calling structured output
