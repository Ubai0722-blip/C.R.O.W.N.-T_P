# by UBAI
"""
tool_router.py

Pipeline-level tool routing coordinator.
It keeps tool prompt injection and tool-result re-reply logic out of pipeline.py.
"""
from typing import Any


class PipelineToolRouter:
    def __init__(self, pipeline: Any):
        self.pipeline = pipeline

    def append_tools_prompt(self, full_context: str) -> str:
        p = self.pipeline
        tools_prompt = p.tool_registry.get_tools_prompt()
        if not tools_prompt:
            return full_context
        return full_context + f"\n\n{tools_prompt}"

    async def maybe_refine_reply_with_tool(
        self,
        user_text: str,
        draft_reply: str,
        messages: list[dict],
        safety_result,
    ) -> str:
        p = self.pipeline
        tool_result = await p.tool_registry.execute_from_text(draft_reply)
        if not (tool_result and tool_result.success):
            return draft_reply

        tool_context = f"\n\n[工具调用结果] {tool_result.result}"
        messages.append({"role": "assistant", "content": draft_reply})
        messages.append(
            {"role": "user", "content": tool_context + "\n请基于以上工具结果回复用户。"}
        )
        refined = await p.llm.chat(messages)
        if not refined:
            refined = "我在"
        return p.safety.guard_output(user_text, refined, safety_result)
