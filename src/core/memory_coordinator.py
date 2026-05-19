# by UBAI
"""
memory_coordinator.py
记忆协调器。

把聊天主流程中的短期记忆、长期记忆、MemoryLedger 和情景记忆写入动作集中管理。
"""
from typing import Any

from .llm import dlog


class PipelineMemoryCoordinator:
    """MessagePipeline 的记忆写入门面。"""

    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    def prepare_user_memory(self, session, text: str, safety_result=None) -> None:
        """在生成回复前抽取用户输入中的长期记忆和账本记忆。"""
        session.long_memory.extract_and_store(text)
        self.record_memory_ledger(session, text, safety_result)

    def record_memory_ledger(self, session, text: str, safety_result=None) -> None:
        """把明确的偏好、目标、事实和风险写入统一记忆账本 v1。"""
        ledger = getattr(session, "memory_ledger", None)
        if not ledger or not text or len(text.strip()) < 4:
            return

        memory_type = ""
        confidence = 0.65
        sensitivity = ""
        if safety_result and safety_result.risk_score >= 3:
            memory_type = "risk"
            confidence = max(0.75, safety_result.confidence)
            sensitivity = "high"
        elif any(kw in text for kw in ["我喜欢", "我不喜欢", "我讨厌", "我偏好", "更喜欢"]):
            memory_type = "preference"
        elif any(kw in text for kw in ["计划", "目标", "打算", "准备", "想要完成", "要更新"]):
            memory_type = "goal"
        elif any(kw in text for kw in ["我叫", "我是", "我的生日", "我在", "我住"]):
            memory_type = "fact"

        if not memory_type:
            return

        try:
            item = ledger.add(
                content=text[:300],
                memory_type=memory_type,
                source="chat",
                confidence=confidence,
                sensitivity=sensitivity,
                evidence=text[:500],
            )
            dlog(
                f"[memory-ledger] 写入: user={session.user_id}, "
                f"type={item.type}, sensitivity={item.sensitivity}, consent={item.consent_status}"
            )
        except Exception as e:
            dlog(f"[memory-ledger] 写入失败: user={session.user_id}, err={e}")

    def add_short_reply(self, session, user_text: str, ai_reply: str, learn_every: int = 15) -> None:
        """写入短期记忆，并按频率触发长期记忆 AI 抽取。"""
        session.memory.add(user_text, ai_reply)
        dlog(
            f"[memory] 已写入短期记忆: user={session.user_id}, "
            f"items={len(session.memory.messages)}"
        )
        if learn_every <= 0:
            return
        session.memory._msg_counter = getattr(session.memory, "_msg_counter", 0) + 1
        if session.memory._msg_counter >= learn_every:
            session.memory._msg_counter = 0
            self.pipeline._spawn_bg(session.long_memory.ai_extract_and_store(self.pipeline.llm))

    def store_episodic_if_needed(
        self,
        session,
        user_text: str,
        ai_reply: str,
        event_type: str,
        emotion: str,
        scene: str = "",
        stream: bool = False,
    ) -> None:
        """根据事件类型和情绪强度决定是否存储情景记忆。"""
        if stream:
            should_store = event_type in ["分享秘密", "情感共鸣", "关心回应"] or emotion in ["难过", "生气", "感动", "兴奋"]
            if not should_store:
                return
            importance = 5 if event_type == "分享秘密" else 4 if event_type == "情感共鸣" else 3
            session.episodic_memory.store(
                content=f"用户说：{user_text[:80]}，我回了：{ai_reply[:80]}",
                category=event_type,
                emotion=emotion,
                importance=importance,
            )
            return

        should_store = False
        importance = 2
        if event_type == "分享秘密":
            should_store = True
            importance = 5
        elif event_type == "情感共鸣":
            should_store = True
            importance = 4
        elif event_type == "关心回应":
            should_store = True
            importance = 3
        elif event_type == "日常分享" and len(user_text) > 30:
            should_store = True
            importance = 3
        elif emotion in ["难过", "生气", "感动", "兴奋"]:
            should_store = True
            importance = 3

        if not should_store:
            return

        causal = ""
        if emotion in ["难过", "生气", "焦虑"]:
            causal = f"用户当时情绪{emotion}"

        session.episodic_memory.store(
            content=f"用户说：{user_text[:80]}，我回了：{ai_reply[:80]}",
            category=event_type,
            emotion=emotion,
            scene=scene[:30] if scene else "",
            causal_link=causal,
            importance=importance,
        )
