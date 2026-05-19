# C.R.O.W.N. Persona Bot - Copilot 指南

本文档为在 **C.R.O.W.N.** 工作区中运行的 AI 助手（如 GitHub Copilot）提供架构背景、编码规范和操作方向。

## 1. 项目概述
**C.R.O.W.N.** 是一个以 LLM 为核心驱动、具有高度交互性的虚拟人设（Persona）机器人。底层依托 NoneBot2 消息框架（通过 OneBot v11 协议连接 NapCatQQ），并调用兼容 OpenAI 格式的 API 来实现认知、对话生成与逻辑推理。

核心目标是模拟一个逼真、能够不断成长且具备长期记忆、情绪状态、多模态能力（图像/语音）及主动沟通能力的角色。

### 技术栈
- **开发语言**: Python 3.9+ (全面使用异步 `asyncio` 生态)
- **Bot 框架**: NoneBot2 + OneBot V11 适配器 (`nonebot2[fastapi]`)
- **LLM API**: `openai` 官方 Python 库
- **数据库**: SQLite (`sqlite3`)，使用异步或同步的封装，结合本地 JSON/YAML 作为配置文件。
- **音频处理**: `pilk` (用于 Silk 语音消息的编解码)。
- **定时任务**: `nonebot-plugin-apscheduler` (用于主动发送消息及定时认知任务)。

---

## 2. 架构与目录结构

- **`/` (根目录)**
  - `qq_bot.py`: NoneBot2 入口及应用初始化逻辑。
  - `db_manager.py`: 数据库操作与 SQL 管理。
  - `config.yaml` / `requirements.txt`: 环境变量与依赖配置。
  - `启动机器人.bat`: 一键启动脚本。
- **`/data`**: 存储运行时状态、Prompt 切片、表情包图库、音频缓存及辅助人设定义（如 `scenes.yaml`, `tones.yaml`）。
- **`/personas`**: 角色配置文件（如 `C.R.O.W.N..yaml`）。
- **`/logs`**: 系统运行日志。
- **`/src/` (核心业务逻辑)**
  - `core/`: 核心引擎，包含全局消息钩子与任务队列 (`pipeline.py`)。负责在交由认知模型前对消息进行主干拦截。
  - `cognition/`: “大脑”模块。涵盖心理分析 (`psych.py` / `psychology.py`)、角色进化/演进 (`evolution.py`) 及好感度/关系成长 (`growth.py`)。 
    *注：进化与成长采取消息定期批量结算的方式（例如每满 50 条消息归纳一次），以节省 LLM Token 并防止阻塞。*
  - `memory/`: 短期上下文滑动窗口，以及长期向量/摘要记忆等存取操作。
  - `interaction/`: 对外交互行为层，如主动发言系统 (`proactive.py`)。
  - `multimodal/`: 图文 OCR、图片发送、TTS (文本转语音)、STT (语音转文本) 以及语音消息处理。
  - `plugins/`: Nonebot 插件层 (`mychat/` 模块)。负责将 Nonebot 收到的事件和正则匹配路由到核心 Pipeline 执行阶段。
  - `utils/`: 通用工具类、配置加载器、辅助函数。

---

## 3. 开发规范

### 异步与并发
- 所有的 I/O 密集型任务（LLM 调用、数据库查询、文件读写、`httpx` 网络请求）**必须**使用 `async` 和 `await`。
- 主处理流程中严禁使用阻塞性库（例如 `requests` 或 同步的 `time.sleep()`）。请统一替换为 `httpx.AsyncClient()` 和 `asyncio.sleep()`。

### 核心代码修改原则
- **单一职责原则**: 确保 Prompt 组装、LLM 请求调用以及数据库持久化各司其职、互不耦合。切勿在仅负责 LLM 生成的函数内部直接嵌套复杂的 DB 查询（应置于 `db_manager.py` 这个业务中）。
- **规范导入**: 采用基于 `src.*` 命名空间的模块化导入（例如：`from src.interaction.proactive import ProactiveSystem`）。*需要时可采用延迟加载以免死锁循环依赖。*
- **系统周期性任务**: 诸如 `growth.py` 和 `evolution.py` 皆依赖批量触发（例如满 50 条消息）。必须遵循此架构模式，避免针对单条消息执行高频复杂调用，总是检查类似 `msg_counter % 50 == 0` 来验证触发条件。

### 状态与 Prompt 处理
- AI 的行为规则及 Prompt 必须从标准的配置文件（如 `C.R.O.W.N..yaml`）抓取。严禁在 Python 代码逻辑中硬编码具体的人格特征。若需调整角色语气或规则，请直接编辑受管理的 YAML 等配置文件。

## 4. 给 Copilot 的建议协作流程
进行代码检查或变更时：
1. **分析先行**: 在代码重构前，请先了解诸如 `db_manager.py` 的数据结构或 `src/core/pipeline.py` 的中央机制。
2. **核心层级理解**: 厘清 `cognition`（后台心理与思考逻辑）、`memory`（记忆存取模块）与 `interaction`（实际与用户的 QQ 通讯与触发交互）这三者的职责边界。
3. **精准处理依赖**: 若涉及变更或检查依赖库，只需通过 `import` 与 `from ... import` 列表来审视当前被用到的库文件，绝不乱主观假设需要安装任何不相关的包。