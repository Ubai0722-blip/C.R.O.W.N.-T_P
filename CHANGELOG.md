# C.R.O.W.N 变更日志

## 2026-06-03 维护修复

### 修复
- 修复 WebUI「关系定制」页面在 `data/relationship_types.yaml` 缺失时接口 500 的问题；缺失时会自动生成默认关系配置。
- 关系类型保存、删除和切换接口改为使用同一套稳健读写逻辑，避免空文件或缺表导致页面报错。

### 调整
- 删除一键部署脚本，改为 README、零基础教程和使用说明中的手动部署流程。
- 文档补充从 0 开始安装 Python、创建虚拟环境、安装依赖、部署 NapCat、配置 API 和启动机器人的小白步骤。

## 2026-05-14 v0.0.5 劳伦缇娜人设重构 + 系统优化

### 🦈 人设重构（CROWN-L）
- **劳伦缇娜人设全面重写**：基于 laurentina.md 和鲨鲨详细分析.md，重构为现代社会雕塑家+舞者人设
- **20个语气组**：随意懒散、温柔安慰、真诚深聊、艺术狂热、舞蹈流体、锐利批评、冷淡打发、突然沉默、调侃戏谑、深夜缪斯、清晨迷糊、工作专注、稀有温柔、存在漂移、竞争锋芒、材料低语、哲学弯折、随意八卦、创作受阻、周末放松
- **22个场景组**：日常闲聊、安慰陪伴、深夜谈心、艺术讨论、舞蹈话题、审美批评、无聊对话、安静时刻、调侃模式、深夜创作、清晨问候、工作被打断、亲密时刻、存在感对话、被质疑、材料对话、哲学碎片、八卦时间、创作卡壳、周末状态、用户需要安慰、随机回忆
- **5次迭代打磨**：初稿→逻辑审查→口语化改造→边界设定→最终整合
- **原始人设备份**：`班味攻击性拉满的鲨鲨.zip`

### ⏰ 时间感知系统重构
- **去除催睡觉逻辑**：不再催促用户睡觉，尊重每个人的作息节奏
- **深夜语气调整**：凌晨和深夜时段语气轻但不特殊对待，不说“早点休息”
- **碎碎念时间联动**：碎碎念系统与时间感知深度联动，按时段生成不同风格的碎碎念提示
- **主动消息时间联动**：主动消息根据时段生成不同的问候风格

### 📋 定时任务系统（新增）
- **自动识别用户意图**：从聊天消息中自动检测定时任务意图（如“提醒我明天三点开会”）
- **LLM时间解析**：用轻量模型解析具体时间，支持一次性提醒和循环提醒（每天/每周/每小时）
- **到期提醒**：主动消息系统自动检查到期任务并提醒用户
- **任务持久化**：定时任务保存到 `data/scheduled_tasks.json`，重启不丢失

### 🔧 结构优化
- **语气组/场景组分文件管理**：从单一 YAML 改为 `data/tone_groups/` 和 `data/scene_groups/` 目录
- **模块读取优化**：场景检测从 config.yaml 读取活跃的语气组和场景组
- **ProactiveSystem v3**：主动消息系统重构，集成定时任务检查

### 📁 修改文件清单
- `personas/Laurentina.yaml` — 完全重写
- `data/tone_groups/laurentina.yaml` — 新增20个语气组
- `data/scene_groups/laurentina.yaml` — 新增22个场景组
- `src/interaction/time_awareness.py` — 完全重写，新增定时任务系统
- `src/interaction/proactive.py` — v3重构，集成定时任务+时间联动
- `src/core/pipeline.py` — 集成定时任务检测
- `config.yaml` — 更新场景组绑定

---

## 2026-05-11 全面重构

### 🔧 Bug修复
- **空文本过滤**：新增 `src/utils/text_filter.py`，过滤所有Unicode不可见字符（LRM/ZWNJ/ZWSP/ZWJ/ZWNBS等20+种），防止空白消息触发LLM调用
- **语气词频率控制**：在 `send_msg` 中添加后处理，语气词（嗯/啊/哦/噢/呃/额等）出现频率限制为≤0.2
- **主动消息完全重构**：重写 `proactive.py`，所有状态持久化到数据库（重启不丢失），修复主动消息完全不工作的问题

### ✨ 新功能
- **VLM图像识别API**：新增 `VLMClient` 类，通过API进行图像/表情包识别，替代本地模型（无需GPU）
- **关系系统增强**：
  - 新增夫妻（spouse）关系类型
  - 关系开关功能（enabled字段）
  - 互斥逻辑：激活一个关系时自动关闭其他关系
- **时间感知改进**：
  - 新增 `temp_time_mentions` 表，临时存储用户提到的时间
  - 12小时自动清理过期数据
  - 网络时间获取（带本地时间fallback）
- **WebUI配置页重设计**：
  - 分模块配置：主对话模型/轻量模型/VLM模型/TTS模型/搜索
  - 13个国内外AI平台预设（小米MiMo/通义千问/文心一言/智谱GLM/Kimi/DeepSeek/百川/MiniMax/OpenAI/Claude/Gemini/Mistral/Groq）
  - 选择平台后自动填充API地址
- **部署说明整理**：补充手动安装 Python、依赖和 NapCat 的步骤
- **使用说明**：`使用说明.txt`，超详细傻瓜式教程

### ⚙️ 配置变更
- `config.yaml`：
  - 默认温度从0.75改为1.1
  - 新增 `vlm` 配置段（api_base/api_key/model/max_tokens/temperature/timeout）
- `data/relationship_types.yaml`：新增spouse（夫妻）关系类型

### 📁 修改文件清单
- `src/utils/text_filter.py` — 新增
- `src/core/llm.py` — 新增VLMClient类
- `src/interaction/proactive.py` — 完全重写
- `src/interaction/time_awareness.py` — 网络时间获取
- `src/memory/database.py` — 新增temp_time_mentions表
- `src/multimodal/sticker.py` — VLM集成
- `src/cognition/relationship.py` — 开关+互斥逻辑
- `src/plugins/mychat/__init__.py` — 文本过滤/VLM/语气词控制/主动消息重构
- `config.yaml` — 温度+VLM配置
- `data/relationship_types.yaml` — 新增spouse
- `prts_config.py` — 配置页重设计
- `README.md` — 更新
- `README.md` / `使用说明.txt` — 补充部署说明
- `使用说明.txt` — 新增
