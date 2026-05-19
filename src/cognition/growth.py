# by UBAI
"""
growth.py
成长系统 - 数据库版
"""
import json
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.database import Database


@dataclass
class GrowthMemory:
    time: str
    event: str
    category: str
    emotion: str
    user_involved: bool
    impact: int


@dataclass
class UserProfile:
    user_id: str
    nickname: str = ""
    relationship_level: int = 5
    relationship_exp: int = 0
    first_seen: str = ""
    last_seen: str = ""
    total_messages: int = 0
    total_days: int = 0
    active_days: list[str] = field(default_factory=list)
    favorite_topics: dict = field(default_factory=dict)
    mood_history: list[str] = field(default_factory=list)
    growth_memories: list[dict] = field(default_factory=list)
    shared_experiences: int = 0
    emotional_bonds: int = 0


RELATIONSHIP_LEVELS = {
    5: {
        "name": "好友",
        "exp_needed": 0,
        "hint": "关系不错的朋友，会自然地聊天，偶尔分享日常",
    },
    6: {
        "name": "亲近的朋友",
        "exp_needed": 50,
        "hint": "比较亲近，会主动分享心事和日常小事，偶尔开玩笑",
    },
    7: {
        "name": "好朋友",
        "exp_needed": 150,
        "hint": "很亲近，会吐槽和撒娇，记得对方的事情，会主动关心",
    },
    8: {
        "name": "挚友",
        "exp_needed": 300,
        "hint": "无话不谈，会认真给建议，遇到好事坏事第一个想告诉对方",
    },
    9: {
        "name": "最重要的人",
        "exp_needed": 600,
        "hint": "非常在意，会因为对方的情绪而影响自己的心情，几乎家人般的存在",
    },
    10: {
        "name": "无可替代",
        "exp_needed": 9999,
        "hint": "最亲密的关系，彼此是对方生命中不可或缺的存在",
    },
}


GROWTH_EVENT_EXP = {
    "日常分享": 3,
    "情感共鸣": 8,
    "共同经历": 5,
    "深夜陪伴": 6,
    "关心回应": 5,
    "分享秘密": 10,
    "矛盾和解": 8,
    "惊喜时刻": 7,
    "一起成长": 6,
    "日常问候": 1,
}

TOPIC_KEYWORDS = {
    "画画": ["画画", "画", "插画", "绘图", "板绘", "手绘", "上色", "线稿"],
    "游戏": ["游戏", "明日方舟", "方舟", "原神", "抽卡", "关卡", "活动"],
    "音乐": ["歌", "音乐", "听歌", "乐队", "专辑", "演唱会"],
    "美食": ["吃", "喝", "饭", "咖啡", "奶茶", "餐厅", "外卖", "做饭"],
    "旅行": ["旅游", "旅行", "出去玩", "景点", "酒店", "机票"],
    "工作": ["工作", "上班", "加班", "甲方", "稿子", "接稿", "收入", "面试"],
    "学习": ["学习", "考试", "考研", "上课", "作业", "毕业", "论文"],
    "宠物": ["猫", "狗", "宠物", "小卡", "铲屎"],
    "心情": ["心情", "开心", "难过", "累", "烦", "焦虑", "无聊", "崩溃"],
    "日常": ["今天", "昨天", "明天", "刚才", "晚上", "早上"],
    "感情": ["恋爱", "喜欢", "对象", "男朋友", "女朋友", "暗恋", "分手"],
    "书影": ["电影", "剧", "动漫", "番", "书", "小说", "阅读"],
    "健康": ["健身", "跑步", "减肥", "生病", "医院", "感冒", "失眠"],
    "社交": ["朋友", "聚会", "群", "聊天", "网友", "社交"],
    "购物": ["买", "购物", "快递", "淘宝", "剁手", "种草"],
    "技术": ["编程", "代码", "bug", "开发", "python", "AI", "技术"],
}


class GrowthSystem:
    """成长系统 - 数据库版（集成关系定制系统）"""

    def __init__(self, relationship_manager=None):
        self.db = Database()
        self._lover_mode: dict[str, bool] = {}
        self._load_lover_mode()
        self.relationship = relationship_manager  # 关系定制管理器（延迟注入）

    def set_relationship_manager(self, rm):
        """注入关系定制管理器"""
        self.relationship = rm

    def _load_lover_mode(self):
        """从数据库加载恋人模式状态"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT user_id FROM evolution_state WHERE key = 'lover_mode' AND value = 'true'"
            ).fetchall()
            for row in rows:
                self._lover_mode[row["user_id"]] = True

    def is_lover_mode(self, user_id: str) -> bool:
        """检查是否开启恋人模式"""
        return self._lover_mode.get(user_id, True)  # 默认开启

    def set_lover_mode(self, user_id: str, enabled: bool):
        """设置恋人模式"""
        self._lover_mode[user_id] = enabled
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO evolution_state (user_id, key, value, updated_at) "
                "VALUES (?, 'lover_mode', ?, ?)",
                (user_id, "true" if enabled else "false", now),
            )

            if enabled:
                conn.execute(
                    "INSERT INTO long_term_memory "
                    "(user_id, category, content, importance, access_count, created_at, last_accessed) "
                    "VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (
                        user_id,
                        "重要关系",
                        "我们在一起了，从今天开始是恋人关系",
                        5,
                        now,
                        now,
                    ),
                )
            # 关闭时不写记忆，自然回到朋友模式

    def get_lover_hint(self, user_id: str) -> str:
        """获取关系提示（优先使用关系定制系统）"""
        # 如果有关系定制管理器，优先使用它
        if self.relationship:
            profile = self.get_profile(user_id)
            hint = self.relationship.get_relationship_hint(
                user_id, profile.relationship_level
            )
            if hint:
                return hint

        # 回退到原有的恋人模式
        if not self.is_lover_mode(user_id):
            return ""

        return (
            "[恋人模式]\n"
            "你和用户是恋人关系。\n"
            "说话风格调整：\n"
            "- 可以撒娇、吃醋、说想对方\n"
            "- 可以用更亲密的称呼，比如'笨蛋'、'亲爱的'\n"
            "- 会因为对方不回消息而有点小情绪\n"
            "- 会主动说'想你了'、'在干嘛'\n"
            "- 关心对方的时候更直接，比如'早点睡'、'记得吃饭'\n"
            "- 偶尔会害羞，被夸的时候会否认但其实很开心\n"
            "- 可以正话反说，比如'才不想你呢'其实很想\n"
            "- 吵架的时候会嘴硬但很快就心软\n"
            "- 不要每条消息都很甜，偶尔平淡一点更真实\n"
            "- 保持你的人设，只是关系更亲密了\n"
        )

    def get_profile(self, user_id: str) -> UserProfile:
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_profiles WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if row:
                profile = UserProfile(
                    user_id=user_id,
                    nickname=row["nickname"],
                    relationship_level=row["relationship_level"],
                    relationship_exp=row["relationship_exp"],
                    first_seen=row["first_seen"],
                    last_seen=row["last_seen"],
                    total_messages=row["total_messages"],
                    total_days=row["total_days"],
                    shared_experiences=row["shared_experiences"],
                    emotional_bonds=row["emotional_bonds"],
                )
            else:
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                profile = UserProfile(
                    user_id=user_id,
                    first_seen=now,
                    last_seen=now,
                    relationship_level=5,
                    relationship_exp=0,
                )
                conn.execute(
                    "INSERT INTO user_profiles "
                    "(user_id, nickname, relationship_level, relationship_exp, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, "", 5, 0, now, now),
                )

            # 加载活跃天数
            days = conn.execute(
                "SELECT date FROM active_days WHERE user_id = ? ORDER BY date",
                (user_id,),
            ).fetchall()
            profile.active_days = [d["date"] for d in days]

            # 加载话题偏好
            topics = conn.execute(
                "SELECT category, count FROM favorite_topics WHERE user_id = ?",
                (user_id,),
            ).fetchall()
            profile.favorite_topics = {t["category"]: t["count"] for t in topics}

            # 加载情绪历史
            moods = conn.execute(
                "SELECT date, emotion FROM mood_history WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
            profile.mood_history = [f"{m['date']}:{m['emotion']}" for m in moods[-50:]]

            # 加载成长记忆
            memories = conn.execute(
                "SELECT time, event, category, emotion, user_involved, impact "
                "FROM growth_memories WHERE user_id = ? ORDER BY id",
                (user_id,),
            ).fetchall()
            profile.growth_memories = [
                {
                    "time": m["time"],
                    "event": m["event"],
                    "category": m["category"],
                    "emotion": m["emotion"],
                    "user_involved": bool(m["user_involved"]),
                    "impact": m["impact"],
                }
                for m in memories[-50:]
            ]

        return profile

    def save_profile(self, profile: UserProfile):
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE user_profiles SET "
                "nickname = ?, relationship_level = ?, relationship_exp = ?, "
                "last_seen = ?, total_messages = ?, total_days = ?, "
                "shared_experiences = ?, emotional_bonds = ? "
                "WHERE user_id = ?",
                (
                    profile.nickname,
                    profile.relationship_level,
                    profile.relationship_exp,
                    profile.last_seen,
                    profile.total_messages,
                    profile.total_days,
                    profile.shared_experiences,
                    profile.emotional_bonds,
                    profile.user_id,
                ),
            )

    def update_basic_stats(self, user_id: str, text: str):
        """只更新基础聊天统计和话题分布，使用 SQL 原子操作"""
        profile = self.get_profile(user_id)
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        # 使用 SQL 原子递增，避免 read-modify-write 竞态
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE user_profiles SET total_messages = total_messages + 1, last_seen = ? "
                "WHERE user_id = ?",
                (now.strftime("%Y-%m-%d %H:%M"), user_id),
            )

        # 活跃天数
        if today not in profile.active_days:
            with self.db.get_conn() as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO active_days (user_id, date) VALUES (?, ?)",
                    (user_id, today),
                )
            profile.active_days.append(today)
            profile.total_days = len(profile.active_days)
            
        # 话题偏好
        for category, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    with self.db.get_conn() as conn:
                        conn.execute(
                            "INSERT INTO favorite_topics (user_id, category, count) "
                            "VALUES (?, ?, 1) "
                            "ON CONFLICT(user_id, category) DO UPDATE SET count = count + 1",
                            (user_id, category),
                        )
                    break

        # 重新读取最新数据
        return self.get_profile(user_id)

    async def summarize_growth(self, user_id: str, llm, messages: list[dict]):
        """
        每 50 句调用此方法，AI生成关系变化总结，并根据总结计算获得的经验值
        """
        profile = self.get_profile(user_id)
        if not messages:
            return

        chat_history = ""
        for m in messages:
            role = "用户" if getattr(m, "role", "user") == "user" else "你"
            chat_history += f"{role}: {getattr(m, 'content', '')}\n"

        prompt = f"""
分析以下最新50句聊天记录，评估你和用户之间关系的发展。
[聊天记录]
{chat_history}

请以JSON格式返回评估结果，字段包括：
- "summary": 简单概括这段时间内的互动体验和关系变化（一到两句话）。
- "event": 如果其中有比较印象深刻的共享经验、讨论的重点或者引起情绪共鸣的事件，提炼成短句；如果没有填"无"。
- "emotion": 这段时间交流的主要情感基调（例如：开心、难过、期待、平静、感动、生气等）。
- "exp_gain": 综合评估增加的经验值（1到20的整数，依据对话的交心程度和活跃度打分，普通闲聊1-5，有情绪共鸣或深度交流可给10-20）。
- "bonds_inc": 整数，是否有明显的情感共鸣发生，是为1，不是为0。
- "shared_inc": 整数，是否一起探讨了重要经历或分享了秘密，是为1，不是为0。
"""
        try:
            res_str = await llm.chat_light([
                {"role": "system", "content": "你是一个情感与关系评估助理。请仅返回JSON格式。"},
                {"role": "user", "content": prompt}
            ])
            import json
            res_str = res_str.replace("```json", "").replace("```", "").strip()
            data = json.loads(res_str)

            exp = int(data.get("exp_gain", 0))
            if exp > 0:
                # 应用关系类型的经验倍率
                multiplier = 1.0
                if self.relationship:
                    multiplier = self.relationship.get_exp_multiplier(user_id)
                exp = int(exp * multiplier)
                profile.relationship_exp += exp
            
            bonds_inc = int(data.get("bonds_inc", 0))
            if bonds_inc > 0:
                profile.emotional_bonds += bonds_inc

            shared_inc = int(data.get("shared_inc", 0))
            if shared_inc > 0:
                profile.shared_experiences += shared_inc
                
            self._check_level_up(profile)

            event = data.get("event", "无")
            if event != "无":
                now = datetime.now().strftime("%Y-%m-%d %H:%M")
                with self.db.get_conn() as conn:
                    conn.execute(
                        "INSERT INTO growth_memories "
                        "(user_id, time, event, category, emotion, user_involved, impact) "
                        "VALUES (?, ?, ?, ?, ?, 1, ?)",
                        (user_id, now, event, "定期总结", data.get("emotion", "平静"), 3),
                    )

            self.save_profile(profile)

        except Exception as e:
            import traceback
            with open("debug.log", "a", encoding="utf-8") as f:
                f.write(f"[growth summary err] {e}\n")
                f.write(traceback.format_exc() + "\n")

    def record_life_event_response(
        self,
        user_id: str,
        life_event: str,
        user_response: str,
        shared_emotion: str = "",
    ):
        profile = self.get_profile(user_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        exp_gain = GROWTH_EVENT_EXP["日常分享"]
        profile.shared_experiences += 1

        if shared_emotion in ["开心", "难过", "感动", "生气", "焦虑"]:
            exp_gain = GROWTH_EVENT_EXP["情感共鸣"]
            profile.emotional_bonds += 1

        profile.relationship_exp += exp_gain
        self._check_level_up(profile)

        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO growth_memories "
                "(user_id, time, event, category, emotion, user_involved, impact) "
                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                (user_id, now, f"一起聊了「{life_event[:30]}」",
                 "共同经历", shared_emotion or "平静", 3 if shared_emotion else 2),
            )

        self.save_profile(profile)

    def _check_level_up(self, profile: UserProfile):
        for level in range(10, 4, -1):
            if level in RELATIONSHIP_LEVELS:
                info = RELATIONSHIP_LEVELS[level]
                if profile.relationship_exp >= info["exp_needed"]:
                    if level > profile.relationship_level:
                        old_level = profile.relationship_level
                        profile.relationship_level = level

                        # 使用关系定制系统的升级事件描述
                        event_desc = None
                        if self.relationship:
                            event_desc = self.relationship.get_level_up_event(
                                profile.user_id, level
                            )
                        if not event_desc:
                            event_desc = f"亲密度从{old_level}级升到{level}级"

                        with self.db.get_conn() as conn:
                            conn.execute(
                                "INSERT INTO growth_memories "
                                "(user_id, time, event, category, emotion, user_involved, impact) "
                                "VALUES (?, ?, ?, ?, ?, 1, ?)",
                                (profile.user_id,
                                 datetime.now().strftime("%Y-%m-%d %H:%M"),
                                 event_desc,
                                 "里程碑", "开心", 5),
                            )
                    break

    def get_context_hint(self, user_id: str) -> str:
        profile = self.get_profile(user_id)
        level = profile.relationship_level
        level_info = RELATIONSHIP_LEVELS.get(level, RELATIONSHIP_LEVELS[5])

        lines = []
        lines.append(f"你和这个用户的亲密度：{level_info['name']}（{level}/10）")
        lines.append(f"相处方式：{level_info['hint']}")

        if profile.total_days > 1:
            lines.append(f"你们已经认识 {profile.total_days} 天，共聊了 {profile.total_messages} 条消息")
        if profile.shared_experiences > 0:
            lines.append(f"共同经历了 {profile.shared_experiences} 件事")
        if profile.emotional_bonds > 0:
            lines.append(f"有过 {profile.emotional_bonds} 次情感共鸣")

        if profile.growth_memories:
            recent = profile.growth_memories[-5:]
            lines.append("你们一起经历的重要时刻：")
            for m in recent:
                emotion_str = f"（{m['emotion']}）" if m.get("emotion") and m["emotion"] != "平静" else ""
                lines.append(f"  - [{m['category']}] {m['event']}{emotion_str}")

        if profile.favorite_topics:
            sorted_topics = sorted(
                profile.favorite_topics.items(),
                key=lambda x: x[1], reverse=True,
            )[:3]
            topics = "、".join(t[0] for t in sorted_topics)
            lines.append(f"用户常聊的话题：{topics}")

        if len(profile.mood_history) >= 3:
            recent_moods = [m.split(":")[1] for m in profile.mood_history[-5:]]
            lines.append(f"用户最近的情绪趋势：{' → '.join(recent_moods)}")

        return "\n".join(lines)

    def get_growth_story(self, user_id: str) -> str:
        profile = self.get_profile(user_id)
        memories = profile.growth_memories

        if not memories:
            return ""

        lines = [f"你和这个用户的关系经历了 {len(memories)} 个重要时刻。"]

        important = [m for m in memories if m.get("impact", 0) >= 3]
        if important:
            lines.append("印象最深的：")
            for m in important[-3:]:
                lines.append(f"  - {m['event']}")

        return "\n".join(lines)

    def _check_level_info(self, profile: UserProfile) -> dict:
        return RELATIONSHIP_LEVELS.get(
            profile.relationship_level,
            RELATIONSHIP_LEVELS[5],
        )
