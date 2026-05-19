# by UBAI
"""
intent_focus.py

Detect clear "closing / disengage" user intents and provide high-priority
focus hints so the assistant does not drag old tasks into the current turn.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class FocusSignal:
    triggered: bool = False
    intent_type: str = ""
    summary: str = ""
    quiet_minutes: int = 0


@dataclass
class FocusWindow:
    intent_type: str
    until: datetime
    source_text: str


class IntentFocusManager:
    """Track short-lived user intent windows and build prompt constraints."""

    REST_KEYWORDS = (
        "我睡了",
        "睡了",
        "先睡",
        "去睡",
        "要睡了",
        "晚安",
        "先休息",
        "我困了",
    )

    BUSY_KEYWORDS = (
        "去忙了",
        "我要忙",
        "我去忙",
        "我先忙",
        "先忙",
        "先去忙",
        "去干活",
        "去上班",
        "去学习",
        "先去处理",
        "先处理点事",
    )

    LEAVE_KEYWORDS = (
        "先走了",
        "先下了",
        "先不聊了",
        "回头聊",
        "等会聊",
        "晚点聊",
        "先撤了",
    )

    def __init__(self):
        self._windows: dict[str, FocusWindow] = {}

    NEGATIVE_PATTERNS = (
        "你睡了吗",
        "你睡了没",
        "你睡没睡",
        "你去忙吗",
        "你先忙吗",
    )

    @staticmethod
    def _normalize(text: str) -> str:
        return (text or "").strip().lower().replace(" ", "")

    def detect(self, text: str) -> FocusSignal:
        t = self._normalize(text)
        if not t:
            return FocusSignal()
        if any(k in t for k in self.NEGATIVE_PATTERNS):
            return FocusSignal()
        if any(k in t for k in self.REST_KEYWORDS):
            return FocusSignal(
                triggered=True,
                intent_type="rest",
                summary="用户明确表示要休息/睡觉",
                quiet_minutes=8 * 60,
            )
        if any(k in t for k in self.BUSY_KEYWORDS):
            return FocusSignal(
                triggered=True,
                intent_type="busy",
                summary="用户明确表示要去忙当前事务",
                quiet_minutes=120,
            )
        if any(k in t for k in self.LEAVE_KEYWORDS):
            return FocusSignal(
                triggered=True,
                intent_type="leave",
                summary="用户明确表示要暂时离开对话",
                quiet_minutes=60,
            )
        return FocusSignal()

    def update(self, user_id: str, text: str) -> FocusSignal:
        signal = self.detect(text)
        if signal.triggered:
            self._windows[user_id] = FocusWindow(
                intent_type=signal.intent_type,
                until=datetime.now() + timedelta(minutes=signal.quiet_minutes),
                source_text=(text or "")[:120],
            )
        return signal

    def get_active_window(self, user_id: str) -> FocusWindow | None:
        w = self._windows.get(user_id)
        if not w:
            return None
        if w.until < datetime.now():
            self._windows.pop(user_id, None)
            return None
        return w

    def should_quiet_proactive(self, user_id: str) -> bool:
        w = self.get_active_window(user_id)
        if not w:
            return False
        return w.intent_type in ("rest", "busy", "leave")

    def build_prompt_hint(self, signal: FocusSignal) -> str:
        if not signal.triggered:
            return ""
        return (
            "[当前用户意图]\n"
            f"{signal.summary}。\n"
            "本轮请只围绕用户刚提到的这件事回应：\n"
            "1) 先确认和关心当下状态。\n"
            "2) 不要再提起之前未完成的任务、旧提醒、旧目标或旧话题。\n"
            "3) 不要追问其他安排，回复自然收束。"
        )

    def build_prompt_hint_for_user(self, user_id: str, latest_text: str = "") -> str:
        signal = self.detect(latest_text)
        if signal.triggered:
            return self.build_prompt_hint(signal)
        w = self.get_active_window(user_id)
        if not w:
            return ""
        summary_map = {
            "rest": "用户处于休息/睡觉意图窗口",
            "busy": "用户处于忙碌意图窗口",
            "leave": "用户处于暂离意图窗口",
        }
        summary = summary_map.get(w.intent_type, "用户处于短期离线意图窗口")
        return (
            "[当前用户意图]\n"
            f"{summary}（来源：{w.source_text[:40]}）。\n"
            "本轮请继续只围绕用户刚提到的事情回应：\n"
            "1) 不主动拉回旧任务、旧提醒、旧目标。\n"
            "2) 语气简洁自然，优先确认用户当前状态。"
        )
