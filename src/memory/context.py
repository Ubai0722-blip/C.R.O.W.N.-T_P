# by UBAI
"""
context.py
上下文联系模块 - 理解指代、省略、追问
作为基础功能，每条消息都经过分析。
"""
import re
from dataclasses import dataclass


@dataclass
class ContextAnalysis:
    """上下文分析结果"""
    has_reference: bool       # 是否包含上下文引用
    reference_type: str       # 引用类型
    resolved_hint: str        # 给 AI 的提示（帮它理解用户在说什么）
    needs_history: bool       # 是否需要历史对话来理解


# ========== 指代词库 ==========

# 代词：指代上文提到的事物
PRONOUNS = [
    "它", "他", "她", "这个", "那个", "这些", "那些",
    "这边", "那边", "这里", "那里", "这种", "那种",
    "前者", "后者", "此事", "此事", "这个东西", "那个东西",
    "这个人", "那个人", "这件事情", "那件事情",
]

# 追问词：对上文内容的追问
FOLLOW_UP_WORDS = [
    "然后呢", "后来呢", "接着呢", "再然后",
    "为什么", "怎么这样", "是真的吗", "你确定吗",
    "详细说说", "具体一点", "展开讲讲", "说详细点",
    "什么意思", "怎么理解", "能解释一下吗",
    "还有吗", "还有其他的吗", "除此之外", "另外",
    "那", "所以", "因此", "这样的话",
]

# 省略主语：消息很短但不是敷衍，而是在延续对话
SHORT_FOLLOW_UPS = [
    "那", "所以", "然后", "接着", "但是", "不过",
    "可是", "而且", "而且", "对了", "话说",
    "对", "嗯对", "是的", "没错", "确实",
    "好的", "好吧", "行吧", "算了",
]

# 时间指代
TIME_REFERENCES = [
    "刚才", "刚刚", "之前", "上次", "之前说的",
    "前面说的", "你刚才说的", "你之前说的",
    "昨天说的", "上次说的", "前两天",
]

# 比较指代
COMPARISON_REFERENCES = [
    "比那个", "跟那个比", "和那个一样", "比之前",
    "跟之前比", "跟刚才比", "比刚才",
]

# 话题延续
TOPIC_CONTINUATION = [
    "那", "那那个", "那个", "对了那个",
    "回到刚才", "继续刚才的", "刚才的话题",
    "回到之前", "之前那个",
]


class ContextAnalyzer:
    """上下文分析器"""

    def analyze(self, text: str, history: list[dict] = None) -> ContextAnalysis:
        """
        分析用户消息中的上下文引用。
        text: 当前用户消息
        history: 最近的历史对话 [{"role": "user/assistant", "content": "..."}]
        """
        if not text:
            return ContextAnalysis(
                has_reference=False,
                reference_type="none",
                resolved_hint="",
                needs_history=False,
            )

        text = text.strip()

        # 提取上一轮对话的关键词
        last_context = self._extract_last_context(history)

        # 检测各种引用类型
        checks = [
            self._check_pronoun(text),
            self._check_follow_up(text),
            self._check_short_follow_up(text, history),
            self._check_time_reference(text),
            self._check_comparison(text),
            self._check_topic_continuation(text),
            self._check_ellipsis_subject(text, history),
            self._check_topic_switch_back(text, history),
        ]

        # 取第一个匹配到的结果
        for result in checks:
            if result.has_reference:
                # 补充上文信息到提示中
                if last_context and result.needs_history:
                    result.resolved_hint += f"\n上一轮对话：{last_context}"
                return result

        return ContextAnalysis(
            has_reference=False,
            reference_type="none",
            resolved_hint="",
            needs_history=False,
        )

    def _extract_last_context(self, history: list[dict] | None) -> str:
        """提取上一轮对话的摘要"""
        if not history or len(history) < 2:
            return ""

        # 取最后一条用户消息和最后一条 AI 回复
        last_user = ""
        last_assistant = ""

        for msg in reversed(history):
            if msg["role"] == "assistant" and not last_assistant:
                last_assistant = msg["content"][:100]
            elif msg["role"] == "user" and not last_user:
                last_user = msg["content"][:100]
            if last_user and last_assistant:
                break

        if last_user and last_assistant:
            return f"用户：{last_user}\nAI：{last_assistant}"
        return ""

    def _check_pronoun(self, text: str) -> ContextAnalysis:
        """检测代词引用"""
        for pronoun in PRONOUNS:
            if pronoun in text:
                # 排除太长的消息（长消息一般不是纯指代）
                if len(text) <= 15:
                    return ContextAnalysis(
                        has_reference=True,
                        reference_type="pronoun",
                        resolved_hint=f"用户说的「{pronoun}」指的是上文提到的某个事物，请结合上下文理解",
                        needs_history=True,
                    )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_follow_up(self, text: str) -> ContextAnalysis:
        """检测追问"""
        for word in FOLLOW_UP_WORDS:
            if text.startswith(word) or text == word:
                return ContextAnalysis(
                    has_reference=True,
                    reference_type="follow_up",
                    resolved_hint=f"用户在追问上文的内容（「{word}」），请结合上一轮对话回答",
                    needs_history=True,
                )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_short_follow_up(self, text: str, history: list[dict] | None) -> ContextAnalysis:
        """检测简短的延续性回复"""
        if not history or len(history) < 2:
            return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

        # 消息很短（3-8字）且不是敷衍词
        if 2 <= len(text) <= 8:
            for word in SHORT_FOLLOW_UPS:
                if text.startswith(word):
                    return ContextAnalysis(
                        has_reference=True,
                        reference_type="continuation",
                        resolved_hint="用户在延续上一轮对话，请结合上下文理解",
                        needs_history=True,
                    )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_time_reference(self, text: str) -> ContextAnalysis:
        """检测时间指代"""
        for word in TIME_REFERENCES:
            if word in text:
                return ContextAnalysis(
                    has_reference=True,
                    reference_type="time_ref",
                    resolved_hint=f"用户提到了「{word}」，是在引用之前的对话内容",
                    needs_history=True,
                )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_comparison(self, text: str) -> ContextAnalysis:
        """检测比较指代"""
        for word in COMPARISON_REFERENCES:
            if word in text:
                return ContextAnalysis(
                    has_reference=True,
                    reference_type="comparison",
                    resolved_hint="用户在拿当前话题和上文的某个内容做比较",
                    needs_history=True,
                )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_topic_continuation(self, text: str) -> ContextAnalysis:
        """检测话题延续"""
        for word in TOPIC_CONTINUATION:
            if text.startswith(word) and len(text) <= 20:
                return ContextAnalysis(
                    has_reference=True,
                    reference_type="topic_continuation",
                    resolved_hint="用户在延续或回到之前的话题",
                    needs_history=True,
                )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_ellipsis_subject(self, text: str, history: list[dict] | None) -> ContextAnalysis:
        """
        检测省略主语。
        如果上一轮 AI 在提问或给出选项，用户的简短回复可能是省略了主语。
        """
        if not history or len(history) < 2:
            return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

        # 上一轮 AI 回复中包含问句
        last_assistant = ""
        for msg in reversed(history):
            if msg["role"] == "assistant":
                last_assistant = msg["content"]
                break

        question_indicators = ["？", "?", "吗", "呢", "吧", "要不要", "想不想", "喜不喜欢"]
        if any(q in last_assistant for q in question_indicators):
            # 当前消息很短（1-10字），可能是回答上一个问题
            if 1 <= len(text) <= 10:
                # 排除明确的新话题
                new_topic_words = ["帮我", "搜一下", "查一下", "对了", "话说", "另外"]
                if not any(w in text for w in new_topic_words):
                    return ContextAnalysis(
                        has_reference=True,
                        reference_type="ellipsis",
                        resolved_hint="用户在回答上一轮 AI 提出的问题，可能省略了主语，请结合上下文理解",
                        needs_history=True,
                    )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)

    def _check_topic_switch_back(self, text: str, history: list[dict] | None) -> ContextAnalysis:
        """检测话题切换回之前的主题"""
        switch_back_words = [
            "回到刚才", "刚才说到哪了", "之前聊到哪了",
            "回到之前的话题", "继续之前的话题",
            "刚才那个", "之前那个",
        ]
        for word in switch_back_words:
            if word in text:
                return ContextAnalysis(
                    has_reference=True,
                    reference_type="switch_back",
                    resolved_hint="用户想回到之前聊过的话题，请回忆之前的对话内容",
                    needs_history=True,
                )
        return ContextAnalysis(has_reference=False, reference_type="none", resolved_hint="", needs_history=False)
