# by UBAI
"""
growth_coordinator.py

Coordinator for growth stats, goal creation, summary triggers, and
conversation event classification used by MessagePipeline.
"""
from typing import Any

from .llm import dlog


class PipelineGrowthCoordinator:
    """Growth-system facade for MessagePipeline."""

    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    def classify_event(self, text: str, emotion: str) -> str:
        if not text:
            return "\u65e5\u5e38\u95ee\u5019"

        share_keywords = [
            "\u4eca\u5929",
            "\u6628\u5929",
            "\u521a\u624d",
            "\u6211\u53d1\u73b0",
            "\u4f60\u77e5\u9053\u5417",
            "\u544a\u8bc9\u4f60",
        ]
        if any(kw in text for kw in share_keywords):
            return "\u65e5\u5e38\u5206\u4eab"

        secret_keywords = [
            "\u6211\u53eb",
            "\u6211\u4f4f",
            "\u6211\u5728",
            "\u6211\u517b\u4e86",
            "\u6211\u8ba8\u538c",
            "\u6211\u5bb3\u6015",
            "\u79d8\u5bc6",
            "\u4ece\u6ca1\u8ddf\u4eba\u8bf4\u8fc7",
        ]
        if any(kw in text for kw in secret_keywords):
            return "\u5206\u4eab\u79d8\u5bc6"

        care_keywords = [
            "\u4f60\u8fd8\u597d\u5417",
            "\u4f60\u6ca1\u4e8b\u5427",
            "\u6ce8\u610f\u4f11\u606f",
            "\u522b\u592a\u7d2f\u4e86",
            "\u5fc3\u75bc",
            "\u8f9b\u82e6\u4e86",
            "\u8c22\u8c22\u4f60",
        ]
        if any(kw in text for kw in care_keywords):
            return "\u5173\u5fc3\u56de\u5e94"

        if emotion in ["\u96be\u8fc7", "\u5f00\u5fc3", "\u611f\u52a8", "\u751f\u6c14"]:
            return "\u60c5\u611f\u5171\u9e23"

        return "\u65e5\u5e38\u95ee\u5019"

    def update_after_reply(self, session, user_text: str, ai_reply: str, emotion_result, stream: bool = False) -> str:
        """Update growth state and return the classified event type."""
        p = self.pipeline
        user_id = session.user_id

        profile = p.growth.update_basic_stats(user_id, user_text)

        goal = None
        if hasattr(p.growth, "maybe_create_goal_from_text"):
            goal = p.growth.maybe_create_goal_from_text(user_id, user_text)
        if goal:
            prefix = "\u6d41\u5f0f\u81ea\u52a8\u521b\u5efa" if stream else "\u81ea\u52a8\u521b\u5efa"
            dlog(f"[growth-goal] {prefix}: user={user_id}, type={goal.goal_type}, title={goal.title[:40]}")

        if hasattr(p.growth, "handle_goal_feedback_from_text"):
            feedback = p.growth.handle_goal_feedback_from_text(user_id, user_text)
            if isinstance(feedback, dict) and feedback.get("touched", 0) > 0:
                dlog(
                    "[growth-goal] reply-feedback: "
                    f"user={user_id}, touched={feedback.get('touched', 0)}, "
                    f"completed={feedback.get('completed', 0)}, deleted={feedback.get('deleted', 0)}, "
                    f"paused={feedback.get('paused', 0)}, refreshed={feedback.get('refreshed', 0)}"
                )

        if hasattr(p.growth, "ensure_goal_followup_windows"):
            refreshed = p.growth.ensure_goal_followup_windows(user_id, default_hours=16)
            if refreshed > 0:
                dlog(f"[growth-goal] followup-refresh: user={user_id}, refreshed={refreshed}")

        if profile.total_messages > 0 and profile.total_messages % 10 == 0:
            history = session.memory.messages[-50:]
            p._spawn_bg(p.growth.summarize_growth(user_id, p.llm, history))

        emotion = getattr(emotion_result, "primary", "\u5e73\u9759")
        event_type = self.classify_event(user_text, emotion)
        p.evolution.log_conversation(user_id, user_text, ai_reply, emotion, event_type)
        return event_type
