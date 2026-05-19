# by UBAI
"""
persona_hub.py
人格统一管理中心 - 整合所有人格相关模块

一级菜单（核心维度）：
├── 1. 人格定义 (Persona Definition)
│   ├── 1.1 角色设定加载 (persona.py)
│   ├── 1.2 行为准则 (Behavior Rules)
│   └── 1.3 说话风格 (Speaking Style)
│
├── 2. 人格稳定性 (Persona Stability)
│   ├── 2.1 漂移检测 (persona_drift.py)
│   ├── 2.2 残差分析 (persona_control.py)
│   └── 2.3 修正参数生成 (Correction Parameters)
│
├── 3. 人格动态 (Persona Dynamics)
│   ├── 3.1 情感惯性 (PAD Emotion Bridge)
│   ├── 3.2 成长演化 (Growth/Evolution)
│   └── 3.3 叙事自我表露 (Narrative)
│
├── 4. 人格记忆 (Persona Memory)
│   ├── 4.1 情景记忆 (Episodic Memory)
│   ├── 4.2 长期记忆 (Long-term Memory)
│   └── 4.3 记忆发酵 (Memory Fermentation)
│
└── 5. 人格控制 (Persona Control)
    ├── 5.1 可采纳性判定 (Adoptability)
    ├── 5.2 累计偏差管理 (Cumulative Deviation)
    └── 5.3 Prompt组装策略 (Prompt Assembly)
"""

from dataclasses import dataclass, field
from datetime import datetime

from .persona import Persona, PersonaLoader, SpeakingStyle, Behavior
from .persona_drift import PersonaDriftDetector, DriftReport
from .persona_control import PersonaController, AdoptabilityVerdict, CorrectionParameters
from .pad_persona_bridge import PADPersonaBridge, PersonaAdjustment
from .emotion import EmotionAnalyzer, EmotionResult
from .growth import GrowthSystem, UserProfile
from .evolution import EvolutionEngine
from .psychology import PsychologyAnalyzer, PsychologyProfile
from ..interaction.narrative import NarrativeEngine
from ..memory.episodic_memory import EpisodicMemoryManager
from ..memory.long_memory import LongTermMemory


@dataclass
class PersonaState:
    """
    人格完整状态快照
    在每轮对话中被构建，包含所有人格维度的当前值。
    """
    # === 一级：人格定义 ===
    persona: Persona = None               # 当前角色设定
    persona_key: str = "default"           # 当前角色key
    
    # === 一级：人格稳定性 ===
    drift_report: DriftReport = None       # 最近的漂移检测报告
    adoptability: AdoptabilityVerdict = None  # 可采纳性判定
    correction: CorrectionParameters = None   # 修正参数（如果需要）
    residual_magnitude: float = 0.0        # 当前残差幅度
    
    # === 一级：人格动态 ===
    pad_adjustment: PersonaAdjustment = None  # PAD驱动的人格调整
    growth_profile: UserProfile = None      # 成长档案
    psychology: PsychologyProfile = None    # 心理画像
    
    # === 一级：人格记忆 ===
    episodic_count: int = 0               # 情景记忆数量
    long_memory_count: int = 0            # 长期记忆数量
    
    # === 一级：人格控制 ===
    control_context: str = ""             # 人格控制的Prompt注入文本
    is_stable: bool = True                # 人格是否稳定


class PersonaHub:
    """
    人格统一管理中心
    
    整合所有人格相关模块，提供统一的接口：
    - 加载/切换人格
    - 计算人格状态快照
    - 生成人格相关的Prompt注入文本
    - 管理人格稳定性
    """

    def __init__(self, user_id: str, llm=None):
        self.user_id = user_id
        self.llm = llm
        
        # === 一级：人格定义 ===
        self._personas: dict[str, Persona] = {}
        self._current_key: str = "default"
        
        # === 一级：人格稳定性 ===
        self.drift_detector = PersonaDriftDetector(llm)
        self.controller = PersonaController(user_id, llm)
        self.controller.load_state()
        
        # === 一级：人格动态 ===
        self.pad_bridge = PADPersonaBridge(user_id)
        self.emotion = EmotionAnalyzer()
        self.growth = GrowthSystem()
        self.evolution = EvolutionEngine()
        self.psychology = PsychologyAnalyzer(llm)
        self.narrative = NarrativeEngine(llm)
        
        # === 一级：人格记忆 ===
        self.episodic = EpisodicMemoryManager(user_id)
        self.long_memory = LongTermMemory(user_id)

    # ========== 1. 人格定义 ==========

    def load_personas(self, directory: str):
        """加载目录下所有人格YAML"""
        self._personas = PersonaLoader.load_all(directory)

    def set_persona(self, key: str):
        """切换当前人格"""
        if key in self._personas:
            self._current_key = key

    def get_persona(self) -> Persona:
        """获取当前人格"""
        return self._personas.get(self._current_key, list(self._personas.values())[0])

    def get_persona_key(self) -> str:
        return self._current_key

    def get_all_persona_keys(self) -> list[str]:
        return list(self._personas.keys())

    # ========== 2. 人格稳定性 ==========

    def check_drift(self, recent_replies: list[str]) -> DriftReport | None:
        """
        检查人格漂移。
        返回 None 表示不需要检测。
        """
        for reply in recent_replies:
            self.drift_detector.cache_reply(self.user_id, reply)
        
        persona = self.get_persona()
        return self.drift_detector.check(
            user_id=self.user_id,
            persona_name=persona.name,
            persona_description=persona.description,
            persona_personality=persona.personality,
            persona_rules=persona.behavior.rules,
        )

    def compute_residual(self, reply: str, user_text: str = "", emotion: str = "平静"):
        """计算残差标签并更新累计偏差"""
        persona = self.get_persona()
        persona_dict = {
            "speaking_style": {
                "tone": persona.speaking_style.tone,
                "sentence_length": persona.speaking_style.sentence_length,
            },
        }
        return self.controller.compute_residual(
            current_reply=reply,
            expected_persona=persona_dict,
            user_text=user_text,
            emotion=emotion,
        )

    def get_stability_context(self) -> str:
        """
        获取人格稳定性的Prompt注入文本。
        包含：漂移修正 + 残差修正
        """
        parts = []
        
        # 漂移修正
        drift_hint = self.drift_detector.get_correction_hint(self.user_id)
        if drift_hint:
            parts.append(drift_hint)
        
        # 残差/累计偏差修正
        control_hint = self.controller.get_control_context()
        if control_hint:
            parts.append(control_hint)
        
        return "\n\n".join(parts) if parts else ""

    # ========== 3. 人格动态 ==========

    def update_emotion(self, text: str) -> EmotionResult:
        """分析情绪并更新PAD状态"""
        result = self.emotion.analyze_and_update(self.user_id, text)
        # 联动PAD模型
        self.pad_bridge.receive_emotion_stimulus(
            result.primary, result.intensity
        )
        return result

    def get_dynamics_context(self) -> str:
        """
        获取人格动态的Prompt注入文本。
        包含：PAD调整 + 成长状态 + 心理画像 + 叙事上下文
        """
        parts = []
        
        # PAD调整
        pad_ctx = self.pad_bridge.get_prompt_context()
        if pad_ctx:
            parts.append(pad_ctx)
        
        # 成长状态
        growth_ctx = self.growth.get_context_hint(self.user_id)
        if growth_ctx:
            parts.append(f"[用户关系]\n{growth_ctx}")
        
        # 恋人模式
        lover_hint = self.growth.get_lover_hint(self.user_id)
        if lover_hint:
            parts.append(lover_hint)
        
        # 心理画像
        psych_ctx = self.psychology.get_context_hint(self.user_id)
        if psych_ctx:
            parts.append(psych_ctx)
        
        # 进化引擎
        evo_ctx = self.evolution.get_evolution_context(self.user_id)
        if evo_ctx:
            parts.append(evo_ctx)
        
        # 叙事历史（避免重复）
        narrative_ctx = self.narrative.get_narrative_context(self.user_id)
        if narrative_ctx:
            parts.append(narrative_ctx)
        
        return "\n\n".join(parts) if parts else ""

    # ========== 4. 人格记忆 ==========

    def get_memory_context(self, text: str, emotion: str = "平静") -> str:
        """
        获取人格记忆的Prompt注入文本。
        包含：情景记忆 + 长期记忆回忆
        """
        import random
        parts = []
        
        # 情景记忆（30%概率根据话题召回，10%概率根据情感召回）
        roll = random.random()
        episodic_recall = None
        if roll < 0.30:
            episodic_recall = self.episodic.recall_by_context(
                text, current_emotion=emotion, max_items=2
            )
        elif roll < 0.40:
            episodic_recall = self.episodic.recall_by_emotion(emotion, max_items=1)
        
        if episodic_recall:
            hint = self.episodic.format_for_prompt(episodic_recall)
            if hint:
                parts.append(hint)
        
        # 长期记忆（35%概率话题相关，15%概率随机）
        roll2 = random.random()
        recall = None
        if roll2 < 0.35:
            recall = self.long_memory.get_related_recall(text)
        elif roll2 < 0.50:
            recall = self.long_memory.get_random_recall()
        
        if recall:
            parts.append(f"[记忆回忆] 你突然想起了这件事，可以自然地提起：\n{recall}")
        
        return "\n\n".join(parts) if parts else ""

    def store_episodic(
        self, content: str, category: str = "日常",
        emotion: str = "平静", scene: str = "",
        causal_link: str = "", importance: int = 3,
    ):
        """存储一条情景记忆"""
        self.episodic.store(
            content=content, category=category,
            emotion=emotion, scene=scene,
            causal_link=causal_link, importance=importance,
        )

    # ========== 5. 人格控制 ==========

    def get_full_persona_context(
        self, text: str, emotion: str = "平静",
    ) -> str:
        """
        获取完整的人格相关Prompt注入文本。
        这是对外的主接口，pipeline._build_context() 调用此方法。
        
        返回的所有内容都会被注入到LLM的system prompt中。
        """
        parts = []
        
        # 人格稳定性（漂移修正 + 残差修正）
        stability = self.get_stability_context()
        if stability:
            parts.append(stability)
        
        # 人格动态（PAD + 成长 + 心理 + 进化）
        dynamics = self.get_dynamics_context()
        if dynamics:
            parts.append(dynamics)
        
        # 人格记忆（情景 + 长期）
        memory = self.get_memory_context(text, emotion)
        if memory:
            parts.append(memory)
        
        return "\n\n".join(parts) if parts else ""

    def on_reply_generated(self, reply: str, user_text: str, emotion: str):
        """
        每轮回复生成后的回调。
        更新所有需要基于回复内容的状态。
        """
        # 计算残差标签
        self.compute_residual(reply, user_text, emotion)
        
        # 缓存回复用于漂移检测
        self.drift_detector.cache_reply(self.user_id, reply)
        
        # 缓存心理画像消息
        self.psychology.cache_message(self.user_id, "user", user_text)
        self.psychology.cache_message(self.user_id, "assistant", reply)

    def should_narrate(self, context: str = "proactive") -> bool:
        """判断是否应该触发叙事"""
        return self.narrative.should_narrate(self.user_id, context)

    async def generate_narrative(self, context: str = "proactive") -> str | None:
        """生成一段叙事内容"""
        narrative_type = self.narrative.pick_narrative_type(context)
        persona = self.get_persona()
        
        # 获取最近生活事件
        recent_events = ""
        if hasattr(self, 'life') and self.life:
            recent_events = self.life.get_recent_context(max_events=3)
        
        return await self.narrative.generate_narrative(
            user_id=self.user_id,
            narrative_type=narrative_type,
            persona_name=persona.name,
            recent_events=recent_events,
            current_emotion=self.emotion.get_mood_hint(self.user_id) or "平静",
        )

    # ========== 统计与调试 ==========

    def get_all_status(self) -> str:
        """获取所有人格相关模块的状态"""
        lines = ["=" * 40, "人格统一管理中心 - 状态报告", "=" * 40]
        
        # 1. 人格定义
        persona = self.get_persona()
        lines.append(f"\n【一级：人格定义】")
        lines.append(f"  当前角色: {persona.name} (key={self._current_key})")
        lines.append(f"  可用角色: {', '.join(self._personas.keys())}")
        lines.append(f"  语气: {persona.speaking_style.tone}")
        lines.append(f"  句长: {persona.speaking_style.sentence_length}")
        
        # 2. 人格稳定性
        lines.append(f"\n【一级：人格稳定性】")
        lines.append(self.controller.get_status_text())
        drift_stats = self.drift_detector.get_stats(self.user_id)
        lines.append(drift_stats)
        
        # 3. 人格动态
        lines.append(f"\n【一级：人格动态】")
        lines.append(self.pad_bridge.get_status())
        profile = self.growth.get_profile(self.user_id)
        lines.append(f"  亲密度: Lv.{profile.relationship_level} ({profile.total_days}天)")
        lines.append(f"  消息数: {profile.total_messages}")
        
        # 4. 人格记忆
        lines.append(f"\n【一级：人格记忆】")
        epi_stats = self.episodic.get_stats()
        lines.append(f"  情景记忆: {epi_stats['total']}条")
        if epi_stats['categories']:
            for cat, cnt in epi_stats['categories'].items():
                lines.append(f"    {cat}: {cnt}")
        lines.append(f"  叙事统计: {self.narrative.get_stats(self.user_id)}")
        
        # 5. 人格控制
        lines.append(f"\n【一级：人格控制】")
        verdict = self.controller.judge_adoptability()
        lines.append(f"  可采纳: {'✅' if verdict.is_adoptable else '❌'}")
        lines.append(f"  严重程度: {verdict.severity}")
        lines.append(f"  置信度: {verdict.confidence:.2f}")
        
        return "\n".join(lines)
