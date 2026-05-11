# 小红书多设备自动化运营系统

实现10台以内安卓设备并发自动化操作小红书，完成发现页目标用户帖子的自动识别、点赞、收藏、截图等操作。内置AI Agent引擎自主处理执行过程中的异常卡点情况。

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 初始化系统
python main.py init

# 启动完整系统（含监控面板）
python main.py all
# 访问 http://localhost:8080 查看实时状态
```

详细使用说明请查看 [使用文档](使用文档.md)

## 核心功能

- **多设备并发**: SQLite WAL模式 + 单进程单设备隔离，支持10台设备同时运行
- **内容类型识别**: 自动区分图文帖和视频帖，采用不同浏览策略
- **目标用户匹配**: OCR识别发现页用户昵称，支持精确/模糊匹配
- **图像模板匹配**: OpenCV多尺度模板匹配定位按钮，设备分辨率无关
- **行为多样性**: 每个设备有独特的行为画像，模拟不同用户习惯
- **AI异常处理**: 火山引擎豆包模型Vision分析，案例库自学习
- **账号保护**: 养号期策略 + 每日操作限制，降低风控风险
- **反爬规避**: 随机延迟、S型轨迹、行为随机化
- **监控面板**: Flask + WebSocket实时推送，Web界面监控
- **账号管理**: 自动登录、验证码人工提醒、账号轮换

## 配置

### 系统配置 `configs/system.yaml`

```yaml
system:
  max_devices: 10
  operations_per_minute: 8          # 每分钟最多8次
  daily_limit_per_user: 3           # 每目标用户每日3次

llm:
  api_key: "your-api-key"
  model: "Doubao-Seed-2.0-pro"
```

### 账号配置 `configs/accounts.yaml`

```yaml
accounts:
  - account: "手机号"
    password: "密码"
    status: "active"
```

### 目标用户 `configs/targets.yaml`

```yaml
target_users:
  - nickname: "目标用户昵称"
    match_mode: "exact"
```

## 项目结构

```
├── main.py                    # 主入口
├── configs/                   # 配置文件
├── device_manager/            # 设备管理
├── account_manager/           # 账号管理
├── human_simulation/          # 真人模拟
├── workflow/                  # 核心业务流程
├── ai_agent/                  # AI Agent引擎
├── task_scheduler/            # 任务调度
├── storage/                   # 数据存储
├── data/                      # 共享状态（SQLite）
├── dashboard/                 # 监控面板
├── templates/                 # 图像模板
├── outputs/                   # 输出截图
└── openspec/                  # 设计文档
```

## 进度

**全部任务已完成** - 核心功能已就绪，详见 [tasks.md](openspec/changes/xiaohongshu-auto-ops-system/tasks.md)
