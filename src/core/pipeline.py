# by UBAI
"""
pipeline.py
核心管线 - 精简版
"""
import asyncio
from datetime import datetime
from dataclasses import dataclass

from src.core import weight_manager
from ..cognition.persona import Persona
from .llm import LLMClient, dlog
from ..interaction.prompt import PromptAssembler
from ..memory.memory import BufferMemory
from ..memory.ledger import MemoryLedger
from ..cognition.emotion import EmotionAnalyzer
from ..multimodal.sticker import StickerManager
from ..memory.context import ContextAnalyzer
from ..cognition.growth import GrowthSystem
from ..cognition.evolution import EvolutionEngine
from ..cognition.psychology import PsychologyAnalyzer
from ..interaction.time_awareness import TimeAwareness, get_current_time
from ..cognition.life import LifeSystem
from .scene import SceneDetector
from ..multimodal.search import WebSearcher
from ..memory.long_memory import LongTermMemory
from ..memory.episodic_memory import EpisodicMemoryManager
from ..cognition.pad_persona_bridge import PADPersonaBridge
from ..cognition.persona_drift import PersonaDriftDetector
from ..cognition.persona_control import PersonaController
from ..cognition.account_binding import AccountBindingManager
from ..interaction.narrative import NarrativeEngine
from ..mcp import ToolRegistry
from ..mcp.mcp_tools import setup_tools
from ..multimodal.url_reader import extract_urls, read_url, format_for_prompt as url_format_for_prompt
from ..interaction.content_policy import ContentPolicy
from ..cognition.relationship import RelationshipManager
from ..cognition.relationship_bridge import get_relationship_bridge
from ..safety.safety_monitor import SafetyMonitor
from .context_builder import PipelineContextBuilder
from .critic_coordinator import PipelineCriticCoordinator
from .growth_coordinator import PipelineGrowthCoordinator
from .intent_focus import IntentFocusManager
from .memory_coordinator import PipelineMemoryCoordinator
from .safety_coordinator import PipelineSafetyCoordinator
from .tool_router import PipelineToolRouter


@dataclass
class Session:
    user_id: str = ""
    memory: BufferMemory = None
    memory_ledger: MemoryLedger = None
    long_memory: LongTermMemory = None
    episodic_memory: EpisodicMemoryManager = None
    pad_bridge: PADPersonaBridge = None
    persona_controller: PersonaController = None
    current_persona_key: str = "Theresa"
    # MCP工具调用结果缓存
    pending_tool_results: list = None

    def __post_init__(self):
        if self.pending_tool_results is None:
            self.pending_tool_results = []


class MessagePipeline:
    def __init__(
        self,
        llm: LLMClient,
        personas: dict[str, Persona],
        default_persona: str = "default",
        life_system: LifeSystem = None,
        sticker_manager: StickerManager = None,
        searcher: WebSearcher = None,
    ):
        self.llm = llm
        self.personas = personas
        self.default_persona = default_persona
        self.emotion = EmotionAnalyzer()
        self.context = ContextAnalyzer()
        self.growth = GrowthSystem()
        self.evolution = EvolutionEngine()
        self.psychology = PsychologyAnalyzer(llm)
        self.time_awareness = TimeAwareness()
        self._task_detection_counter: dict[str, int] = {}
        self.life = life_system

        # 设置数据库人设隔离
        from ..memory.database import Database
        self.db = Database()
        self.db.set_persona(default_persona)
        # 读取心理画像共享配置
        try:
            from ..utils.config import get_config
            config = get_config()
            psych_shared = config.get("modules", {}).get("psychology", {}).get("shared", True)
            self.db.set_psychology_shared(psych_shared)
        except Exception:
            pass
        self.sticker = sticker_manager
        self.searcher = searcher
        self.scene = SceneDetector(llm)
        self.weight_manager = weight_manager.WeightManager()

        self.content_policy = ContentPolicy()
        self.safety_monitor = SafetyMonitor(self.db)
        self.safety = PipelineSafetyCoordinator(self.safety_monitor)
        self.memory_ops = PipelineMemoryCoordinator(self)
        self.growth_ops = PipelineGrowthCoordinator(self)
        self.critic = PipelineCriticCoordinator(self)
        self.intent_focus = IntentFocusManager()
        self.tool_router = PipelineToolRouter(self)
        self.context_builder = PipelineContextBuilder(self)
        self.input_filters: list = []

        # 关系定制系统
        self.relationship = RelationshipManager()
        self.account_binding = AccountBindingManager()

        # 关系桥接系统（仅特定人设启用）
        self.relationship_bridge = get_relationship_bridge("personas", llm)

        # 将关系管理器注入成长系统
        self.growth.set_relationship_manager(self.relationship)

        # 新增模块初始化
        self.drift_detector = PersonaDriftDetector(llm)
        self.narrative_engine = NarrativeEngine(llm)
        self.tool_registry = setup_tools(searcher=searcher)

        self.sessions: dict[str, Session] = {}
        self._pending: dict[str, list[str]] = {}
        self._timers: dict[str, asyncio.Task] = {}
        self.debounce_seconds = 7.0
        self._background_tasks: set[asyncio.Task] = set()
        self._flush_lock = None  # 延迟创建
        self._max_sessions = 200  # LRU 淘汰阈值

        # 分析频率控制
        self._scene_counter: dict[str, int] = {}
        self._psych_counter: dict[str, int] = {}
        self._scene_cache: dict[str, str] = {}

    def _spawn_bg(self, coro):
        """安全地创建后台任务，保存引用防止 GC 回收"""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def _get_lock(self):
        """延迟创建锁，绑定到正确的事件循环"""
        if self._flush_lock is None:
            self._flush_lock = asyncio.Lock()
        return self._flush_lock

    def get_session(self, user_id: str) -> Session:
        # 先设置用户路由，再创建 BufferMemory/长期记忆，避免从默认库加载成“刚说就忘”。
        self.db.set_user(user_id)
        if user_id not in self.sessions:
            # LRU 淘汰：超过阈值时清理最久未活跃的 session
            if len(self.sessions) >= self._max_sessions:
                oldest_key = min(self.sessions, key=lambda k: getattr(self.sessions[k].memory, 'messages', [])[-1].timestamp if self.sessions[k].memory and self.sessions[k].memory.messages else datetime.min)
                self.sessions.pop(oldest_key, None)
                self._scene_counter.pop(oldest_key, None)
                self._psych_counter.pop(oldest_key, None)
                self._scene_cache.pop(oldest_key, None)
            self.sessions[user_id] = Session(
                user_id=user_id,
                memory=BufferMemory(user_id=user_id, max_turns=20),
                memory_ledger=MemoryLedger(user_id=user_id, persona=self.default_persona, db=self.db),
                long_memory=LongTermMemory(user_id),
                episodic_memory=EpisodicMemoryManager(user_id),
                pad_bridge=PADPersonaBridge(user_id),
                persona_controller=PersonaController(user_id, self.llm),
                current_persona_key=self.default_persona,
            )
        return self.sessions[user_id]



    def _get_persona(self, session: Session) -> Persona:
        persona = self.personas.get(session.current_persona_key, list(self.personas.values())[0])
        return persona

    async def _ensure_relationship_loaded(self, session: Session):
        """确保关系上下文已加载（仅特定人设触发）"""
        persona = self.personas.get(session.current_persona_key)
        if not persona:
            return
        if not self.relationship_bridge.should_activate(persona.name):
            return
        if persona.relationship_context:
            return  # 已加载
        # 找到人设文件路径
        persona_file = f"personas/{session.current_persona_key}.yaml"
        try:
            context = await self.relationship_bridge.generate_relationship(
                current_persona=session.current_persona_key,
                current_persona_file=persona_file,
                llm_client=self.llm,
            )
            if context:
                persona.relationship_context = context
        except Exception:
            pass  # 关系加载失败不影响正常对话

    def _get_assembler(self, session: Session) -> PromptAssembler:
        return PromptAssembler(self._get_persona(session))

    # ========== 防抖 ==========
    async def process_with_debounce(self, user_id: str, user_input: str, extra_context: str = "") -> str | None:
        async with self._get_lock():
            if user_id not in self._pending:
                self._pending[user_id] = []
            self._pending[user_id].append(user_input)

            if user_id in self._timers:
                self._timers[user_id].cancel()
                self._timers.pop(user_id, None)

            self._timers[user_id] = asyncio.create_task(
                self._debounce_wait(user_id, extra_context)
            )
        return None

    async def _debounce_wait(self, user_id: str, extra_context: str = "") -> str:
        try:
            await asyncio.sleep(self.debounce_seconds)
        except asyncio.CancelledError:
            return ""
        async with self._get_lock():
            self._timers.pop(user_id, None)
        try:
            return await self._flush_messages(user_id, extra_context)
        except Exception as e:
            import traceback
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"[debounce err] {e}\n")
                f.write(traceback.format_exc() + "\n")
            return ""

    async def _flush_messages(self, user_id: str, extra_context: str = "") -> str:
        async with self._get_lock():
            messages = self._pending.pop(user_id, [])
            self._timers.pop(user_id, None)
        if not messages:
            return ""
        if len(messages) == 1:
            combined = messages[0]
        else:
            combined = "\n".join(f"[第{i+1}条] {msg}" for i, msg in enumerate(messages))
        return await self.process(user_id, combined, extra_context)

    def get_pending_count(self, user_id: str) -> int:
        return len(self._pending.get(user_id, []))

    # ========== 构建上下文（精简版）==========
    async def _build_context(self, session: Session, text: str, extra_context: str = "") -> str:
        """构建对话上下文；具体分层逻辑由 PipelineContextBuilder 负责。"""
        return await self.context_builder.build(session, text, extra_context)

    # ========== 成长事件分类 ==========
    def _classify_growth_event(self, text: str, emotion: str) -> str:
        return self.growth_ops.classify_event(text, emotion)

    # ========== 定时任务检测 ==========
    async def detect_and_schedule_task(self, user_id: str, text: str) -> str | None:
        """
        检测用户消息中的定时任务意图，自动创建定时任务。
        返回确认消息或 None。
        """
        task_info = self.time_awareness.detect_scheduled_task(text)
        if not task_info:
            return None

        now = get_current_time()
        parse_prompt = (
            f"当前时间：{now.strftime('%Y-%m-%d %H:%M')}\n"
            f"用户说：{text}\n\n"
            f"请提取用户想要提醒的时间和内容，输出 JSON：\n"
            f'{{"content": "提醒内容", "trigger_time": "YYYY-MM-DD HH:MM", "recurring": false, "interval": ""}}\n'
            f"如果用户说'每天'则 recurring=true, interval=daily；'每周'则 interval=weekly。\n"
            f"如果无法确定具体时间，输出 {{\"error\": \"无法确定\"}}"
        )

        try:
            result = await self.llm.generate_json(parse_prompt, "你是时间解析助手。只输出JSON。", use_light=True)
            if result and "error" not in result:
                trigger_time = datetime.strptime(result["trigger_time"], "%Y-%m-%d %H:%M")
                task = self.time_awareness.add_task(
                    user_id=user_id,
                    content=result.get("content", text[:30]),
                    trigger_time=trigger_time,
                    task_type="reminder",
                    recurring=result.get("recurring", False),
                    recurring_interval=result.get("interval", ""),
                )
                return f"已记录：{task.content}，{task.trigger_time.strftime('%m月%d日 %H:%M')}提醒你"
        except Exception as e:
            dlog(f"[task] 定时任务解析失败: {e}")

        return None

    def _maybe_record_memory_ledger(self, session: Session, text: str, safety_result=None) -> None:
        """把明确的偏好、目标和风险写入统一记忆账本 v1。"""
        self.memory_ops.record_memory_ledger(session, text, safety_result)

    # ========== 主动消息 ==========
    async def generate_proactive_reply(self, user_id: str, extra_context: str = "") -> str:
        session = self.get_session(user_id)
        persona = self._get_persona(session)
        allowed, safety_reason = self.safety.proactive_precheck(user_id)
        if not allowed:
            return ""
        if self.intent_focus.should_quiet_proactive(user_id):
            dlog(f"[intent-focus] proactive quiet: user={user_id}")
            return ""

        # 获取生活事件
        life_hint = ""
        if self.life:
            event = self.life.get_shareable_event()
            if event:
                life_hint = f"\n最近发生了一件事：{event.content}（{event.mood}）\n你可以自然地提起这件事，但不要每次都提。"
                self.life.mark_shared(event)

        # 获取时间感知
        time_hint = self.time_awareness.get_proactive_time_hint()

        # 检查定时任务
        task_prompt = self.time_awareness.get_pending_tasks_prompt(user_id)

        # 获取 PAD 情感惯性上下文
        pad_context = session.pad_bridge.get_prompt_context()

        # 构建上下文（只注入 LLM 不知道的信息）
        full_context = await self._build_context(session, "", extra_context)

        # 获取关系信息
        growth_hint = self.growth.get_context_hint(user_id)

        # 构建 prompt
        prompt_parts = [
            "你正在判断现在是否适合主动找用户聊天，以及该做什么。",
            "请根据当前时间、关系状态、最近上下文、定时任务和人设，决定是问候、关心、分享日常、接续之前的话题、提醒事项、安静陪伴，还是暂时不打扰。",
            "回复长度和消息条数由你自然决定；如果你想分开发送，可以使用 ||| 分隔。",
            "如果你判断此刻明显不适合打扰用户，可以只输出空内容。",
        ]
        if life_hint:
            prompt_parts.append(life_hint)
        if time_hint:
            prompt_parts.append(f"当前时间风格：{time_hint}")
        if growth_hint:
            prompt_parts.append(f"你们的关系：{growth_hint}")
        if pad_context:
            prompt_parts.append(f"你当前的情感状态：{pad_context}")
        if task_prompt:
            prompt_parts.append(task_prompt)
        if extra_context:
            prompt_parts.append(extra_context)
        if safety_reason:
            prompt_parts.append(safety_reason)

        prompt_parts.append("直接输出你要发的消息，不要加任何前缀。")

        messages = [
            {"role": "system", "content": persona.to_system_prompt()},
            {"role": "system", "content": full_context},
            {"role": "user", "content": "\n".join(prompt_parts)},
        ]

        reply = await self.llm.chat(messages)
        if not reply:
            return ""
        reply = self.safety.guard_proactive_reply(user_id, reply)

        # 存入记忆
        self.memory_ops.add_short_reply(session, "(主动找用户聊天)", reply, learn_every=0)

        return reply

    # ========== 表情包回复 ==========
    async def process_sticker(self, user_id: str, sticker_url: str, text: str = ""):
        session = self.get_session(user_id)
        persona = self._get_persona(session)
        assembler = self._get_assembler(session)

        emotion_result = self.emotion.analyze(text or "表情包")
        full_context = await self._build_context(session, text or "表情包", "")
        full_context += f"\n用户发送了一个表情包。{emotion_result.context_hint}"

        desc = f"[用户发送了表情包]"
        if text:
            desc += f" 附带文字: {text}"

        messages = assembler.assemble(memory=session.memory, user_input=desc, extra_context=full_context)
        reply = await self.llm.chat(messages)
        if not reply:
            reply = "我在"

        self.memory_ops.add_short_reply(session, desc, reply, learn_every=0)
        return reply, emotion_result

    # ========== 图片回复 ==========
    async def process_with_image(self, user_id: str, text: str, images: list[str]) -> str:
        session = self.get_session(user_id)
        persona = self._get_persona(session)
        assembler = self._get_assembler(session)

        full_context = await self._build_context(session, text or "图片", "")

        memory_context = session.long_memory.get_context_text("表情包")
        if memory_context:
            full_context += "\n\n" + memory_context

        desc = f"(用户发送了一张图片)"
        if text:
            desc += f" 附带文字: {text}"

        base_messages = assembler.assemble(memory=session.memory, user_input="(用户发送了一张图片)", extra_context=full_context)

        # 替换最后一条为多模态消息
        vision_content = []
        if text:
            vision_content.append({"type": "text", "text": text})
        for url in images:
            vision_content.append({"type": "image_url", "image_url": {"url": url}})

        if base_messages and base_messages[-1]["role"] == "user":
            base_messages[-1]["content"] = vision_content

        result = await self.llm.chat_multimodal(base_messages)
        if not result:
            result = "我看到了"

        self.memory_ops.add_short_reply(session, desc, result, learn_every=0)
        return result

    # ========== 主处理 ==========
    async def process(self, user_id: str, user_input: str, extra_context: str = "") -> str:
        # 设置数据库用户路由（确保写入正确的 per-user 数据库）
        self.db.set_user(user_id)
        session = self.get_session(user_id)

        # 关系桥接：首次使用特定人设时自动加载关系上下文
        await self._ensure_relationship_loaded(session)

        text = user_input
        for f in self.input_filters:
            result = f(text)
            if result is None:
                return ""
            text = result

        cmd = self._handle_command(session, text)
        if cmd is not None:
            return cmd

        safety_result = self.safety.assess_input(
            user_id,
            text,
            session.memory.get_context_text(),
        )
        direct_safety_reply = self.safety.direct_reply_if_needed(session, text, safety_result)
        if direct_safety_reply:
            return direct_safety_reply

        # ========== 定时任务检测 ==========
        task_result = await self.detect_and_schedule_task(user_id, text)
        if task_result:
            return task_result

        self.memory_ops.prepare_user_memory(session, text, safety_result)

        # 联网搜索
        search_context = ""
        if self.searcher and should_search(text):
            query = extract_search_query(text)
            search_result = await self.searcher.search(query)
            if search_result.success:
                search_context = self.searcher.format_for_prompt(search_result)
                # 生活系统单向输出，不注入搜索结果

        # ========== URL链接读取 ==========
        url_context = ""
        urls = extract_urls(text)
        if urls:
            url_results = []
            for url in urls[:3]:
                url_result = await read_url(url, max_chars=2000)
                url_results.append(url_result)
            url_context = url_format_for_prompt(url_results)

        # 构建上下文（只注入 LLM 不知道的信息）
        full_context = await self._build_context(session, text, extra_context)
        full_context = self.safety.append_prompt_context(user_id, full_context, safety_result)
        if search_context:
            full_context += f"\n\n[联网搜索结果]\n{search_context}\n\n请基于以上搜索结果回答，但要保持角色人设和说话风格。"
        if url_context:
            full_context += f"\n\n{url_context}"

        # ========== 人格漂移修正注入 ==========
        full_context = self.critic.append_drift_hint(user_id, full_context)

        # ========== MCP工具描述注入 ==========
        full_context = self.tool_router.append_tools_prompt(full_context)

        # 组装消息（历史对话通过 messages 传给 LLM）
        assembler = self._get_assembler(session)
        messages = assembler.assemble(memory=session.memory, user_input=text, extra_context=full_context)
        dlog(
            f"[memory] 组装短期记忆: user={user_id}, "
            f"items={len(session.memory.messages)}, prompt_messages={len(messages)}"
        )

        # 调用 LLM
        result = await self.llm.chat(messages)
        if not result:
            result = "我在"
        result = self.safety.guard_output(text, result, safety_result)

        # ========== MCP工具调用检测 ==========
        result = await self.tool_router.maybe_refine_reply_with_tool(
            text, result, messages, safety_result
        )

        # ========== 缓存回复用于漂移检测 ==========
        self.critic.cache_reply(user_id, result)

        # 存入对话记忆，并按频率触发长期记忆 AI 抽取
        self.memory_ops.add_short_reply(session, text, result)

        # 词条权重自动学习
        self.weight_manager.learn_from_text(text)

        # 更新成长系统基础数据
        emotion_result = self.emotion.analyze(text)
        event_type = self.growth_ops.update_after_reply(session, text, result, emotion_result)

        # ========== 存储情景记忆 ==========
        self.memory_ops.store_episodic_if_needed(
            session,
            text,
            result,
            event_type,
            emotion_result.primary,
            scene=self._scene_cache.get(user_id, "日常闲聊"),
        )

        # 心理画像缓存
        self.psychology.cache_message(user_id, "user", text)
        self.psychology.cache_message(user_id, "assistant", result)

        self.critic.post_reply_checks(session, text, result, emotion_result.primary)

        return result

    # ========== 流式处理 ==========
    async def process_stream(self, user_id: str, user_input: str, extra_context: str = ""):
        session = self.get_session(user_id)

        # 设置数据库用户路由
        self.db.set_user(user_id)

        text = user_input
        for f in self.input_filters:
            result = f(text)
            if result is None:
                yield ""
                return
            text = result

        cmd = self._handle_command(session, text)
        if cmd is not None:
            yield cmd
            return

        safety_result = self.safety.assess_input(
            user_id,
            text,
            session.memory.get_context_text(),
        )
        direct_safety_reply = self.safety.direct_reply_if_needed(session, text, safety_result, stream=True)
        if direct_safety_reply:
            yield direct_safety_reply
            return

        # ========== 定时任务检测 ==========
        task_result = await self.detect_and_schedule_task(user_id, text)
        if task_result:
            yield task_result
            return

        self.memory_ops.prepare_user_memory(session, text, safety_result)

        # 联网搜索
        search_context = ""
        if self.searcher and should_search(text):
            query = extract_search_query(text)
            search_result = await self.searcher.search(query)
            if search_result.success:
                search_context = self.searcher.format_for_prompt(search_result)
                # 生活系统单向输出，不注入搜索结果

        # 构建上下文（只注入 LLM 不知道的信息）
        full_context = await self._build_context(session, text, extra_context)
        full_context = self.safety.append_prompt_context(user_id, full_context, safety_result)
        if search_context:
            full_context += f"\n\n[联网搜索结果]\n{search_context}\n\n请基于以上搜索结果回答，但要保持角色人设和说话风格。"

        # 组装消息（历史对话通过 messages 传给 LLM）
        assembler = self._get_assembler(session)
        messages = assembler.assemble(memory=session.memory, user_input=text, extra_context=full_context)

        # 记录最终的内容拼接
        full_response = ""
        
        # 流式入口先走统一 LLM 网关，保证安全后置检查能在发出前生效。
        try:
            full_response = await self.llm.chat(messages)
            if full_response:
                full_response = self.safety.guard_output(text, full_response, safety_result)
                yield full_response
        except Exception as e:
            error_code = type(e).__name__
            if str(e).startswith("HTTP_"):
                error_code = str(e)
            
            error_msg = f"[错误:{error_code}] 我在"
            if not full_response:
                yield error_msg
                full_response = error_msg
            else:
                yield f"\n[附加错误:{error_code}]"

        if not full_response:
            full_response = "我在"
            yield full_response
            
        # 后续的记忆和情感处理与普通 process 一样
        self.memory_ops.add_short_reply(session, text, full_response)

        # 词条权重自动学习
        self.weight_manager.learn_from_text(text)

        emotion_result = self.emotion.analyze(text)
        event_type = self.growth_ops.update_after_reply(session, text, full_response, emotion_result, stream=True)

        # ========== 存储情景记忆（流式版本）==========
        self.memory_ops.store_episodic_if_needed(
            session,
            text,
            full_response,
            event_type,
            emotion_result.primary,
            stream=True,
        )

        self.psychology.cache_message(user_id, "user", text)
        self.psychology.cache_message(user_id, "assistant", full_response)

    # ========== 命令处理 ==========
    def _handle_command(self, session: Session, text: str) -> str | None:
        cmd = text.strip()

        if cmd in ("/clear", "/reset", "清空对话"):
            session.memory.clear()
            return "对话已清空，我们重新开始吧。"

        if cmd == "/memory":
            memories = session.long_memory.get_all_memories()
            if not memories:
                return "还没有记住关于你的事情。"
            lines = [f"共记住了 {len(memories)} 件事："]
            for m in memories[-15:]:
                lines.append(f"- [{m.category}] {m.content}（重要度:{m.importance} 访问:{m.access_count}次）")
            return "\n".join(lines)

        if cmd == "/profile":
            profile = self.growth.get_profile(session.user_id)
            level_info = self.growth._check_level_info(profile)
            lines = [
                f"亲密度：{level_info['name']}（{profile.relationship_level}/10）",
                f"经验值：{profile.relationship_exp}/{level_info['exp_needed']}",
                f"认识天数：{profile.total_days}",
                f"消息总数：{profile.total_messages}",
                f"共同经历：{profile.shared_experiences} 次",
                f"情感共鸣：{profile.emotional_bonds} 次",
            ]
            if profile.favorite_topics:
                sorted_topics = sorted(profile.favorite_topics.items(), key=lambda x: x[1], reverse=True)[:5]
                topics = "、".join(f"{t[0]}({t[1]})" for t in sorted_topics)
                lines.append(f"常聊话题：{topics}")
            if profile.growth_memories:
                lines.append(f"\n最近的成长记忆：")
                for m in profile.growth_memories[-5:]:
                    emotion_str = f"（{m['emotion']}）" if m.get("emotion") and m["emotion"] != "平静" else ""
                    lines.append(f"  - [{m['category']}] {m['event']}{emotion_str}")
            return "\n".join(lines)

        if cmd.startswith("/forget "):
            keyword = cmd[8:].strip()
            if session.long_memory.forget(keyword):
                return f"已忘记关于「{keyword}」的记忆。"
            return f"没有找到关于「{keyword}」的记忆。"

        return None


# ========== 联网搜索辅助 ==========
def should_search(text: str) -> bool:
    search_keywords = ["搜索", "查一下", "搜一下", "帮我查", "最新", "新闻", "今天", "天气", "是什么", "怎么", "多少钱"]
    return any(kw in text for kw in search_keywords)


def extract_search_query(text: str) -> str:
    for prefix in ["帮我搜索", "帮我查一下", "搜索一下", "查一下", "搜一下", "帮我搜"]:
        if prefix in text:
            return text.split(prefix, 1)[1].strip()
    return text.strip()

# [0.0.4 PATCH FIX] Applied requested modifications here.

