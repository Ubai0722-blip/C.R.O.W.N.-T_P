# by UBAI
"""
life.py
生活事件系统 - AI 驱动，无模板
"""
import json
import random
from datetime import datetime
from dataclasses import dataclass
from ..memory.database import Database
from ..core.llm import LLMClient


@dataclass
class LifeEvent:
    time: str
    category: str
    content: str
    mood: str
    expire_hours: int = 72
    shared: bool = False


GENERATE_SYSTEM_PROMPT = """你是一个生活事件生成器。你需要模拟一个自由插画师的日常生活，生成一件最近可能发生的小事。

要求：
1. 事件要真实、自然、贴近日常生活
2. 不要太戏剧化，就是普通人的普通一天
3. 根据当前时间段生成合理的事件（早上不会半夜吃夜宵，深夜不会去上班）
4. 不要每次都生成同样的类型，要多样化
5. 内容要具体，不要太笼统
6. 用第一人称描述，像在跟朋友说"我今天xxx"

你可以生成的事件类型包括但不限于：
画画、打游戏、小卡（猫）、吃饭、喝咖啡、听歌、看书、出门、收拾房间、
买东西、天气、心情、工作、社交、刷手机、发呆、运动、做饭、理发、
看剧、试新东西、遇到小意外、想起某件事、被什么事触动……

输出 JSON 格式：
{
  "event": "事件描述（一句话，用第一人称）",
  "mood": "当时的情绪",
  "category": "事件分类（一个词）"
}"""


class LifeSystem:
    """生活事件管理器 - AI 驱动"""

    def __init__(self, persona_name: str = "Theresa", llm: LLMClient = None):
        self.persona_name = persona_name
        self.llm = llm
        self.db = Database()
        self.current_mood: str = "平静"
        self.events: list[LifeEvent] = []
        self._load()

    def _load(self):
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT time, category, content, mood, expire_hours, shared "
                "FROM life_events WHERE persona = ? ORDER BY time DESC LIMIT 100",
                (self.persona_name,),
            ).fetchall()

            self.events = []
            for row in reversed(rows):
                self.events.append(LifeEvent(
                    time=row["time"],
                    category=row["category"],
                    content=row["content"],
                    mood=row["mood"],
                    expire_hours=row["expire_hours"],
                    shared=bool(row["shared"]),
                ))

            if self.events:
                self.current_mood = self.events[-1].mood

    async def generate_event(self) -> LifeEvent | None:
        """
        用 AI 生成一条生活事件。纯独立生成，不接受外部输入。
        """
        if not self.llm:
            return None

        now = datetime.now()
        hour = now.hour

        if 6 <= hour < 12:
            time_desc = "上午"
        elif 12 <= hour < 14:
            time_desc = "中午"
        elif 14 <= hour < 18:
            time_desc = "下午"
        elif 18 <= hour < 23:
            time_desc = "晚上"
        else:
            time_desc = "深夜/凌晨"

        recent_events = ""
        if self.events:
            recent_list = []
            for e in self.events[-5:]:
                recent_list.append(f"- {e.content}（{e.mood}）")
            recent_events = "最近已经发生过的事情（不要重复）：\n" + "\n".join(recent_list)

        mood_hint = f"当前心情：{self.current_mood}" if self.current_mood != "平静" else ""

        prompt = (
            f"现在是{time_desc}（{hour}点）。\n"
            f"{mood_hint}\n"
            f"{recent_events}\n\n"
            f"请生成一件最近可能发生的小事。"
        )

        result = await self.llm.generate_json(prompt, GENERATE_SYSTEM_PROMPT, use_light=True)

        if not result or "event" not in result:
            return None

        event_content = result.get("event", "")
        event_mood = result.get("mood", "平静")
        event_category = result.get("category", "日常")

        if not event_content:
            return None

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

        event = LifeEvent(
            time=now_str,
            category=event_category,
            content=event_content,
            mood=event_mood,
            expire_hours=72,
            shared=False,
        )

        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO life_events (persona, category, content, mood, time, expire_hours, shared) "
                "VALUES (?, ?, ?, ?, ?, ?, 0)",
                (self.persona_name, event_category, event_content, event_mood, now_str, 72),
            )

        self.events.append(event)
        self.current_mood = event_mood

        with self.db.get_conn() as conn:
            conn.execute(
                "DELETE FROM life_events WHERE persona = ? AND id NOT IN "
                "(SELECT id FROM life_events WHERE persona = ? ORDER BY time DESC LIMIT 200)",
                (self.persona_name, self.persona_name),
            )

        return event


    def get_shareable_event(self) -> LifeEvent | None:
        """获取一条还没有分享给用户的事件"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT time, category, content, mood, expire_hours, shared "
                "FROM life_events WHERE persona = ? AND shared = 0",
                (self.persona_name,),
            ).fetchall()

        if not rows:
            return None

        unshared = []
        for row in rows:
            unshared.append(LifeEvent(
                time=row["time"],
                category=row["category"],
                content=row["content"],
                mood=row["mood"],
                expire_hours=row["expire_hours"],
                shared=False,
            ))

        scored = []
        for e in unshared:
            score = 1
            if e.mood in ["开心", "兴奋", "惊喜", "崩溃", "治愈", "好笑", "感动"]:
                score += 2
            scored.append((score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:3]
        return random.choice(top)[1]

    def mark_shared(self, event: LifeEvent):
        """标记事件已分享"""
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE life_events SET shared = 1 "
                "WHERE persona = ? AND time = ? AND content = ?",
                (self.persona_name, event.time, event.content),
            )
        for e in self.events:
            if e.time == event.time and e.content == event.content:
                e.shared = True
                break

    def inject_news_event(self, news_title: str, news_summary: str):
        """联网功能接入"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        content = f"看到一条新闻：{news_title}，{news_summary[:50]}"

        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO life_events (persona, category, content, mood, time, expire_hours, shared) "
                "VALUES (?, ?, ?, ?, ?, ?, 0)",
                (self.persona_name, "时事", content, "思考", now, 48),
            )

        self.events.append(LifeEvent(
            time=now, category="时事", content=content,
            mood="思考", expire_hours=48, shared=False,
        ))

    def get_recent_context(self, max_events: int = 8) -> str:
        """获取最近的生活事件"""
        now = datetime.now()
        recent = []

        for e in reversed(self.events):
            event_time = datetime.strptime(e.time, "%Y-%m-%d %H:%M")
            hours_ago = (now - event_time).total_seconds() / 3600
            if hours_ago < e.expire_hours:
                recent.append(e)
            if len(recent) >= max_events:
                break

        if not recent:
            return ""

        lines = [f"当前心情：{self.current_mood}", "最近的生活："]
        for e in reversed(recent):
            shared_mark = "（已分享）" if e.shared else "（未分享，可以自然地提起）"
            lines.append(f"- [{e.category}] {e.content}（{e.mood}）{shared_mark}")

        return "\n".join(lines)

    def get_current_mood(self) -> str:
        return self.current_mood


class LifeScheduler:
    """定时生成生活事件"""

    def __init__(self, life_system: LifeSystem, min_interval: int = 1800, max_interval: int = 3600):
        self.life = life_system
        self.min_interval = min_interval
        self.max_interval = max_interval
        self._running = False

    async def start(self):
        import asyncio
        self._running = True

        if not self.life.events:
            await self.life.generate_event()
            await self.life.generate_event()

        while self._running:
            wait = random.randint(self.min_interval, self.max_interval)
            await asyncio.sleep(wait)
            if self._running:
                event = await self.life.generate_event()
                if event:
                    with open("debug.log", "a", encoding="utf-8") as f:
                        f.write(f"[life] AI生成事件 [{event.category}]: {event.content}（{event.mood}）\n")

    def stop(self):
        self._running = False

