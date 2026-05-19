# by UBAI
"""
narrative.py
叙事自我表露系统 - 让角色能够讲故事、分享内心独白、回忆共同经历

设计理念（参考 Narrative Generation 理论）：
- 不只是报告事件（"我今天画画了"），而是用叙事结构讲故事
- 叙事结构：起因→经过→感受→反思
- 偶尔分享"内心独白"——深层想法、回忆、感慨
- 用第一人称视角回忆与用户的共同经历

参考项目：
- AI_StoryTeller (github.com/dhimiterq/AI_StoryTeller)
- Narraitor (github.com/jerseycheese/Narraitor)
"""

import random
from datetime import datetime
from dataclasses import dataclass
from ..memory.database import Database


@dataclass
class NarrativeMoment:
    """一个叙事时刻"""
    narrative_type: str    # 类型：story/monologue/recall/wonder
    content: str           # 叙事内容
    emotion: str           # 情感基调
    trigger: str           # 触发条件


# 叙事类型
NARRATIVE_TYPES = {
    "story": {
        "name": "生活故事",
        "description": "用叙事结构描述最近发生的事情",
        "prompt_hint": (
            "请用第一人称叙事的方式描述这件事，包含：\n"
            "1. 起因（为什么会发生）\n"
            "2. 经过（具体发生了什么）\n"
            "3. 感受（当时的心情）\n"
            "4. 反思（事后的想法）\n"
            "像在跟好朋友讲故事一样自然，不要太长，3-5句话。"
        ),
    },
    "monologue": {
        "name": "内心独白",
        "description": "分享深层想法、感慨、哲思",
        "prompt_hint": (
            "请分享一段内心独白，可以是：\n"
            "- 对某件事的深层思考\n"
            "- 突然的感慨或回忆\n"
            "- 对生活/世界的看法\n"
            "- 一些不好意思跟别人说的小想法\n"
            "语气要自然、真实，像是自言自语，2-3句话。"
        ),
    },
    "recall": {
        "name": "回忆共同经历",
        "description": "用第一人称视角回忆与用户的某段对话/经历",
        "prompt_hint": (
            "请回忆一段你和用户之间的经历，用第一人称描述：\n"
            "- 当时的情景\n"
            "- 你的感受\n"
            "- 现在想起来的感触\n"
            "像在跟老朋友回忆往事一样，2-3句话。"
        ),
    },
    "wonder": {
        "name": "好奇与想象",
        "description": "分享好奇心、想象、假设",
        "prompt_hint": (
            "请分享一个你好奇的事情或想象的场景：\n"
            "- '如果...'的假设\n"
            "- 对某件事的好奇\n"
            "- 想象中的一幅画面\n"
            "语气轻松有趣，1-2句话。"
        ),
    },
}


# 叙事触发时机配置
NARRATIVE_TRIGGERS = {
    "proactive": {
        "probability": 0.25,  # 主动消息时25%概率触发叙事
        "types": ["story", "monologue", "wonder"],
    },
    "after_emotion": {
        "probability": 0.15,  # 情感共鸣后15%概率触发回忆
        "types": ["recall", "monologue"],
        "emotions": ["感动", "难过", "开心"],
    },
    "quiet_moment": {
        "probability": 0.10,  # 平静对话中10%概率触发
        "types": ["wonder", "monologue"],
    },
}


class NarrativeEngine:
    """叙事自我表露引擎"""

    def __init__(self, llm=None):
        self.llm = llm
        self.db = Database()
        self._last_narrative: dict[str, datetime] = {}
        self._narrative_cooldown_hours = 4  # 同一用户至少间隔4小时
        self._init_table()

    def _init_table(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS narrative_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    narrative_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    emotion TEXT DEFAULT '平静',
                    trigger TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)

    def should_narrate(self, user_id: str, context: str = "proactive") -> bool:
        """
        判断是否应该触发叙事。
        context: "proactive" / "after_emotion" / "quiet_moment"
        """
        # 冷却检查
        last = self._last_narrative.get(user_id)
        if last:
            hours_since = (datetime.now() - last).total_seconds() / 3600
            if hours_since < self._narrative_cooldown_hours:
                return False

        trigger = NARRATIVE_TRIGGERS.get(context)
        if not trigger:
            return False

        return random.random() < trigger["probability"]

    def pick_narrative_type(self, context: str = "proactive") -> str:
        """选择叙事类型"""
        trigger = NARRATIVE_TRIGGERS.get(context, {})
        types = trigger.get("types", ["story", "monologue"])
        return random.choice(types)

    async def generate_narrative(
        self,
        user_id: str,
        narrative_type: str,
        persona_name: str,
        recent_events: str = "",
        shared_memories: str = "",
        current_emotion: str = "平静",
    ) -> str | None:
        """
        生成一段叙事内容。
        
        参数：
        - narrative_type: story/monologue/recall/wonder
        - recent_events: 最近的生活事件（来自 life.py）
        - shared_memories: 与用户的共同记忆（来自 episodic_memory）
        - current_emotion: 当前情感状态
        """
        if not self.llm:
            return None

        type_config = NARRATIVE_TYPES.get(narrative_type)
        if not type_config:
            return None

        # 构建 prompt
        prompt_parts = [
            f"你是{persona_name}。",
            f"当前情感状态：{current_emotion}",
        ]

        if recent_events:
            prompt_parts.append(f"最近发生的事情：\n{recent_events}")

        if shared_memories and narrative_type == "recall":
            prompt_parts.append(f"你和用户的共同记忆：\n{shared_memories}")

        prompt_parts.append(type_config["prompt_hint"])
        prompt_parts.append(
            "\n【重要】直接输出叙事内容，不要加任何前缀、标题或解释。"
            "保持你的人设和说话风格。"
        )

        prompt = "\n\n".join(prompt_parts)

        system_prompt = (
            f"你是{persona_name}，一个有血有肉的角色。"
            f"你需要用自然、真实的方式分享你的经历和想法。"
            f"不要像AI一样客观描述，要像真人一样有情感、有细节、有温度。"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        result = await self.llm.chat(messages, temperature=0.85)
        if not result or len(result) < 5:
            return None

        # 记录
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO narrative_log "
                "(user_id, narrative_type, content, emotion, trigger, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, narrative_type, result, current_emotion, "", now),
            )

        self._last_narrative[user_id] = datetime.now()

        return result

    def get_narrative_context(self, user_id: str) -> str:
        """获取叙事历史上下文（避免重复讲同样的故事）"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT narrative_type, content FROM narrative_log "
                "WHERE user_id = ? ORDER BY id DESC LIMIT 5",
                (user_id,),
            ).fetchall()

        if not rows:
            return ""

        lines = ["[叙事历史] 最近已经讲过的故事（避免重复）："]
        for r in rows:
            lines.append(f"- [{r['narrative_type']}] {r['content'][:50]}...")
        return "\n".join(lines)

    def get_stats(self, user_id: str) -> str:
        """获取叙事统计"""
        with self.db.get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM narrative_log WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]

            types = conn.execute(
                "SELECT narrative_type, COUNT(*) as cnt FROM narrative_log "
                "WHERE user_id = ? GROUP BY narrative_type ORDER BY cnt DESC",
                (user_id,),
            ).fetchall()

        lines = [f"叙事统计：共{total}次"]
        for t in types:
            type_name = NARRATIVE_TYPES.get(t["narrative_type"], {}).get("name", t["narrative_type"])
            lines.append(f"  {type_name}: {t['cnt']}次")
        return "\n".join(lines)
