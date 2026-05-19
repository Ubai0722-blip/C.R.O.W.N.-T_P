# by UBAI
"""
safety_coordinator.py
安全协调器。

负责把 pipeline 中的安全评估、危机直回、提示注入和输出护栏收拢到一处。
"""
from typing import Any

from .llm import dlog
from ..safety.safety_monitor import SafetyMonitor


class PipelineSafetyCoordinator:
    """MessagePipeline 的安全门面，保持 SafetyMonitor 行为不变。"""

    def __init__(self, monitor: SafetyMonitor):
        self.monitor = monitor

    def assess_input(self, user_id: str, text: str, memory_context: str = ""):
        return self.monitor.assess_input(user_id, text, memory_context)

    def direct_reply_if_needed(self, session: Any, text: str, safety_result, stream: bool = False) -> str | None:
        reply = self.monitor.direct_reply_if_needed(safety_result)
        if not reply:
            return None
        session.memory.add(text, reply)
        prefix = "流式直接危机回复" if stream else "直接危机回复"
        evidence = getattr(safety_result, "evidence", "")
        dlog(
            f"[safety] {prefix}: user={session.user_id}, "
            f"risk={safety_result.risk_level}, evidence={evidence}"
        )
        return reply

    def append_prompt_context(self, user_id: str, full_context: str, safety_result) -> str:
        safety_context = self.monitor.build_prompt_context(safety_result)
        if not safety_context:
            return full_context
        dlog(f"[safety] 注入回复协议: user={user_id}, risk={safety_result.risk_level}")
        return f"{full_context}\n\n{safety_context}" if full_context else safety_context

    def guard_output(self, user_input: str, reply: str, safety_result) -> str:
        return self.monitor.apply_output_guard(user_input, reply, safety_result)

    def proactive_precheck(self, user_id: str):
        allowed, reason = self.monitor.proactive_precheck(user_id)
        if not allowed:
            dlog(f"[safety] 主动消息拦截: user={user_id}, reason={reason}")
        return allowed, reason

    def guard_proactive_reply(self, user_id: str, reply: str) -> str:
        current_safety = self.monitor.get_current_assessment(user_id)
        if not current_safety:
            return reply
        return self.monitor.apply_output_guard("(主动找用户聊天)", reply, current_safety)
