# by UBAI
"""
context_builder.py
对话上下文构建器。

第一阶段只从 pipeline.py 拆出上下文拼装职责，不改变聊天策略。
"""
import random
from datetime import datetime
from typing import Any

from .llm import dlog


class PipelineContextBuilder:
    """集中构建 LLM 需要但自身不知道的上下文。"""

    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    async def build(self, session, text: str, extra_context: str = "") -> str:
        p = self.pipeline
        context_parts: list[str] = []
        uid = session.user_id
        focus_signal = p.intent_focus.update(uid, text)
        focus_mode = focus_signal.triggered or (p.intent_focus.get_active_window(uid) is not None)
        focus_hint = p.intent_focus.build_prompt_hint_for_user(uid, text)
        if focus_hint:
            context_parts.append(focus_hint)

        life_context_for_time = ""
        if p.life:
            life_context_for_time = p.life.get_recent_context()
        time_context = p.time_awareness.get_context(life_context_for_time)
        context_parts.append(f"[时间感知]\n{time_context}")

        if not focus_mode:
            recall = None
            roll = random.random()
            if roll < 0.35:
                recall = session.long_memory.get_related_recall(text)
            elif roll < 0.50:
                recall = session.long_memory.get_random_recall()
            if recall:
                context_parts.append(f"[记忆回忆] 你突然想起了这件事，可以自然地提起：\n{recall}")

        ledger = getattr(session, "memory_ledger", None)
        if not focus_mode and ledger and text:
            try:
                ledger_rows = ledger.search(text, limit=5)
                ledger_hint = ledger.format_for_prompt(ledger_rows)
                if ledger_hint:
                    context_parts.append(ledger_hint)
            except Exception as e:
                dlog(f"[memory-ledger] 检索失败: user={uid}, err={e}")

        emotion_result = await p.emotion.analyze_and_update_with_llm(uid, text, p.llm)

        mood_hint = p.emotion.get_mood_hint(uid)
        if mood_hint:
            context_parts.append(f"[情绪状态] {mood_hint}")

        if p.life:
            life_context = p.life.get_recent_context()
            if life_context:
                context_parts.append(f"[角色当前生活状态]\n{life_context}")

        if not focus_mode:
            episodic_recall = None
            episodic_roll = random.random()
            if episodic_roll < 0.30:
                episodic_recall = session.episodic_memory.recall_by_context(
                    text, current_emotion=emotion_result.primary, max_items=2
                )
            elif episodic_roll < 0.40:
                episodic_recall = session.episodic_memory.recall_by_emotion(
                    emotion_result.primary, max_items=1
                )
            if episodic_recall:
                episodic_hint = session.episodic_memory.format_for_prompt(episodic_recall)
                if episodic_hint:
                    context_parts.append(episodic_hint)

        session.pad_bridge.receive_emotion_stimulus(
            emotion_result.primary, emotion_result.intensity
        )
        pad_context = session.pad_bridge.get_prompt_context()
        if pad_context:
            context_parts.append(pad_context)

        p._scene_counter[uid] = p._scene_counter.get(uid, 0) + 1
        if p._scene_counter[uid] >= 10 or uid not in p._scene_cache:
            p._scene_counter[uid] = 0

            async def _update_scene():
                try:
                    hour = datetime.now().hour
                    growth_profile = p.growth.get_profile(uid)
                    scene_ctx = await p.scene.detect(
                        text,
                        emotion=emotion_result.primary,
                        hour=hour,
                        relationship_level=growth_profile.relationship_level,
                    )
                    p._scene_cache[uid] = p.scene.format_for_prompt(scene_ctx)
                except Exception:
                    pass

            p._spawn_bg(_update_scene())
            if uid not in p._scene_cache:
                p._scene_cache[uid] = ""

        scene_hint = p._scene_cache.get(uid, "")
        if scene_hint:
            context_parts.append(f"[场景识别]\n{scene_hint}")

        top_weights = p.weight_manager.get_all()[:3]
        if top_weights:
            weight_hint = "用户感兴趣的高频话题：" + "、".join(
                f"{w['word']}({w['weight']:.1f})" for w in top_weights
            )
            context_parts.append(weight_hint)

        profile = p.growth.get_profile(uid)
        relationship_hint = p.relationship.get_relationship_hint(uid, profile.relationship_level)
        if relationship_hint:
            context_parts.append(f"[关系定制模块]\n{relationship_hint}")

        binding = p.account_binding.get_binding(uid, session.current_persona_key)
        if binding:
            context_parts.append(self._format_account_binding(session, binding))

        if not focus_mode:
            growth_context = p.growth.get_context_hint(uid)
            if growth_context:
                context_parts.append(f"[用户关系]\n{growth_context}")

        p._psych_counter[uid] = p._psych_counter.get(uid, 0) + 1
        if p._psych_counter[uid] >= 15:
            p._psych_counter[uid] = 0
            p._spawn_bg(p.psychology.analyze(uid, text, emotion_result.primary))

        psych_context = p.psychology.get_context_hint(uid)
        if psych_context:
            context_parts.append(psych_context)

        if not focus_mode:
            evolution_context = p.evolution.get_evolution_context(uid)
            if evolution_context:
                context_parts.append(evolution_context)

        persona_ctrl = session.persona_controller
        if persona_ctrl:
            control_ctx = persona_ctrl.get_control_context()
            if control_ctx:
                context_parts.append(control_ctx)

        policy_hint = p.content_policy.get_system_hint()
        if policy_hint:
            context_parts.append(policy_hint)

        if "[聊天记录]" in text:
            context_parts.append("[聊天记录] 用一句话评论，不要逐条复述")

        if not focus_mode:
            db_summary = self._build_periodic_db_summary(uid)
            if db_summary:
                context_parts.append("[用户数据]\n" + "\n".join(db_summary))

        if extra_context:
            context_parts.append(extra_context)

        return "\n\n".join(context_parts)

    def _format_account_binding(self, session, binding: dict) -> str:
        rel_type = binding.get("relationship_type", "朋友")
        custom_name = binding.get("custom_name", "")
        intimacy = binding.get("intimacy_level", 50)
        trust = binding.get("trust_level", 50)
        interaction = binding.get("interaction_style", "默认")
        boundaries = binding.get("boundaries", {}) or {}
        notes = binding.get("notes", "")

        binding_parts = [
            f"[账号关系绑定模块] 当前账号与人设「{session.current_persona_key}」的绑定关系是「{rel_type}」"
        ]
        if custom_name:
            binding_parts.append(f"你应该称呼用户为「{custom_name}」")
        binding_parts.append(f"亲密度等级：{intimacy}/100，信任度：{trust}/100")
        if intimacy >= 80:
            binding_parts.append("你们关系非常亲密。可以更自然地撒娇、吃醋、说心里话，也可以主动关心对方；回复长度和条数按当下情境自己判断。")
        elif intimacy >= 60:
            binding_parts.append("你们关系比较亲近。可以分享日常和心事，偶尔开玩笑，也可以主动关心；不要套固定回复条数。")
        elif intimacy >= 40:
            binding_parts.append("你们关系还不错，会自然聊天，但不必每次都聊得很深入。")
        else:
            binding_parts.append("你们刚认识不久，保持礼貌和适度距离；是否简短由当前话题决定。")
        if interaction and interaction != "默认":
            binding_parts.append(f"互动风格：{interaction}")
        if boundaries:
            binding_parts.append(f"边界与偏好：{boundaries}")
        if notes:
            binding_parts.append(f"备注：{notes}")
        return "\n".join(binding_parts)

    def _build_periodic_db_summary(self, uid: str) -> list[str]:
        p = self.pipeline
        db_summary: list[str] = []
        p._db_summary_counter = getattr(p, "_db_summary_counter", 0) + 1
        if p._db_summary_counter < 5:
            return db_summary
        p._db_summary_counter = 0

        profile = p.growth.get_profile(uid)
        if profile.total_messages > 5:
            db_summary.append(f"已聊 {profile.total_messages} 条，认识 {profile.total_days} 天")

        if profile.mood_history:
            recent_moods = [m.split(":")[1] for m in profile.mood_history[-3:]]
            db_summary.append(f"情绪：{'→'.join(recent_moods)}")

        if profile.favorite_topics:
            sorted_topics = sorted(profile.favorite_topics.items(), key=lambda x: x[1], reverse=True)[:2]
            topics = "、".join(f"{t[0]}({t[1]})" for t in sorted_topics)
            db_summary.append(f"话题：{topics}")

        try:
            with p.growth.db.get_conn() as conn:
                recent_chats = conn.execute(
                    "SELECT user_msg, ai_reply FROM chat_history "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT 2",
                    (uid,),
                ).fetchall()
            for r in reversed(recent_chats or []):
                db_summary.append(f"用户:{r['user_msg'][:30]} 回:{r['ai_reply'][:30]}")
        except Exception:
            pass
        return db_summary
