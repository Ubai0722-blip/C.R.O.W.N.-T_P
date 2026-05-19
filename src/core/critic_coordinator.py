# by UBAI
"""
critic_coordinator.py

Post-reply critic coordinator for persona stability:
- drift hint injection before generation
- drift cache/update after generation
- residual/adoptability checks
"""
from typing import Any

from .llm import dlog


class PipelineCriticCoordinator:
    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    def append_drift_hint(self, user_id: str, full_context: str) -> str:
        hint = self.pipeline.drift_detector.get_correction_hint(user_id)
        if not hint:
            return full_context
        return full_context + f"\n\n{hint}"

    def cache_reply(self, user_id: str, reply: str) -> None:
        self.pipeline.drift_detector.cache_reply(user_id, reply)

    def post_reply_checks(self, session, user_text: str, reply: str, emotion: str) -> None:
        p = self.pipeline
        persona = p._get_persona(session)

        p._spawn_bg(
            p.drift_detector.check(
                user_id=session.user_id,
                persona_name=persona.name,
                persona_description=persona.description,
                persona_personality=persona.personality,
                persona_rules=persona.behavior.rules,
            )
        )

        persona_dict = {
            "speaking_style": {
                "tone": persona.speaking_style.tone,
                "sentence_length": persona.speaking_style.sentence_length,
            },
        }
        session.persona_controller.compute_residual(
            current_reply=reply,
            expected_persona=persona_dict,
            user_text=user_text,
            emotion=emotion,
        )
        verdict = session.persona_controller.judge_adoptability()
        if verdict.is_adoptable:
            return
        correction = session.persona_controller.generate_correction()
        if correction.correction_prompts:
            dlog(f"[persona] 可采纳性判定: {verdict.severity}, 触发{correction.strategy}修正")
