# by UBAI
"""
proactive.py
主动发消息系统 v3 - 全面重构
支持：主动聊天、碎碎念、主动关心、随机问候、定时任务
碎碎念与时间感知深度联动
所有状态持久化到数据库，重启不丢失
"""
import random
import json
from datetime import datetime, timedelta
from ..memory.database import Database


class ProactiveSystem:
    """主动发消息系统 v3"""

    def __init__(self, time_awareness=None):
        self.db = Database()
        self._ensure_tables()
        self.boot_time = datetime.now()
        self.boot_cooldown_minutes = 5
        self.time_awareness = time_awareness

    def _ensure_tables(self):
        """确保主动消息相关表存在"""
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proactive_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    state_key TEXT NOT NULL,
                    state_value TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, state_key)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_proactive_user
                ON proactive_state(user_id)
            """)

    # ========== 状态持久化 ==========

    def _bind_user(self, user_id: str):
        try:
            self.db.set_user(user_id)
        except Exception:
            pass

    def _get_state(self, user_id: str, key: str, default: str = "") -> str:
        """从数据库获取状态"""
        self._bind_user(user_id)
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT state_value FROM proactive_state WHERE user_id = ? AND state_key = ?",
                (user_id, key)
            ).fetchone()
            return row[0] if row else default

    def _set_state(self, user_id: str, key: str, value: str):
        """写入状态到数据库"""
        self._bind_user(user_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO proactive_state (user_id, state_key, state_value, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (user_id, key, value, now)
            )

    def _get_state_time(self, user_id: str, key: str) -> datetime | None:
        """获取状态对应的时间"""
        val = self._get_state(user_id, key)
        if not val:
            return None
        try:
            return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
        except:
            return None

    # ========== 开机保护 ==========

    def is_boot_safe(self) -> bool:
        elapsed = (datetime.now() - self.boot_time).total_seconds() / 60
        return elapsed >= self.boot_cooldown_minutes

    # ========== 记录用户活跃 ==========

    def record_proactive(self, user_id: str):
        """记录用户活跃（收到用户消息时调用）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._set_state(user_id, "last_user_msg", now)
        self._set_state(user_id, "last_user_message", now)

    def record_sent(self, user_id: str, msg_type: str = "proactive"):
        """记录已发送主动消息"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._set_state(user_id, f"last_{msg_type}", now)

    # ========== 主动聊天判断 ==========

    def should_send_proactive(self, user_id: str, relationship_level: int) -> bool:
        """判断是否应该发送主动消息"""
        if not self.is_boot_safe():
            return False

        now = datetime.now()
        hour = now.hour

        # 凌晨静默（但不禁止深夜）
        if 0 <= hour < 6:
            return False

        # 检查冷却时间（默认2小时）
        last_sent = self._get_state_time(user_id, "last_proactive")
        if last_sent:
            hours_since = (now - last_sent).total_seconds() / 3600
            if hours_since < 2.0:
                return False
        else:
            boot_elapsed = (now - self.boot_time).total_seconds() / 3600
            if boot_elapsed < 1:
                return False

        # 检查用户最近是否活跃（如果用户30分钟内发过消息，不发主动消息）
        last_user_msg = self._get_state_time(user_id, "last_user_msg")
        if last_user_msg:
            minutes_since = (now - last_user_msg).total_seconds() / 60
            if minutes_since < 30:
                return False

        # 基于关系等级的概率调整
        base_chance = 0.3
        level_bonus = min(relationship_level - 5, 5) * 0.05
        chance = min(base_chance + level_bonus, 0.6)

        # 深夜概率降低但不为零
        if 23 <= hour or hour < 2:
            chance *= 0.5

        return random.random() < chance

    # ========== 碎碎念系统 ==========

    def should_send_mutter(self, user_id: str) -> bool:
        """判断是否应该发碎碎念 - 与时间感知联动"""
        if not self.is_boot_safe():
            return False

        now = datetime.now()
        hour = now.hour

        # 凌晨静默（但不禁止深夜）
        if 0 <= hour < 6:
            return False

        # 检查时段配额
        slot = self._get_time_slot(hour)
        if not slot:
            return False

        # 读取今日配额使用情况
        today = now.strftime("%Y-%m-%d")
        quota_key = f"mutter_quota_{today}"
        quota_json = self._get_state(user_id, quota_key, "{}")
        try:
            quotas = json.loads(quota_json)
        except:
            quotas = {}

        max_per_slot = 3
        used = quotas.get(slot, 0)
        if used >= max_per_slot:
            return False

        # 冷却检查：碎碎念和主动消息之间至少间隔30分钟
        last_mutter = self._get_state_time(user_id, "last_mutter")
        last_proactive = self._get_state_time(user_id, "last_proactive")

        if last_mutter:
            if (now.timestamp() - last_mutter.timestamp()) / 60 < 30:
                return False
        if last_proactive:
            if (now.timestamp() - last_proactive.timestamp()) / 60 < 30:
                return False

        # 检查用户最近是否发过消息（防止碎碎念插入对话）
        last_user_msg = self._get_state_time(user_id, "last_user_message")
        if last_user_msg:
            minutes_since_user_msg = (now.timestamp() - last_user_msg.timestamp()) / 60
            if minutes_since_user_msg < 30:
                return False

        # 概率触发（深夜概率降低）
        base_chance = 0.25
        if 23 <= hour or hour < 2:
            base_chance = 0.15

        return random.random() < base_chance

    def refresh_mutter_cooldown(self, user_id: str):
        """收到用户消息时刷新碎碎念冷却（防止碎碎念插入对话）"""
        now = datetime.now()
        now_text = now.strftime("%Y-%m-%d %H:%M:%S")
        self._set_state(user_id, "last_user_message", now_text)
        self._set_state(user_id, "last_user_msg", now_text)

    def record_mutter(self, user_id: str):
        """记录碎碎念已发送"""
        now = datetime.now()
        self._set_state(user_id, "last_mutter", now.strftime("%Y-%m-%d %H:%M:%S"))

        today = now.strftime("%Y-%m-%d")
        slot = self._get_time_slot(now.hour)
        if slot:
            quota_key = f"mutter_quota_{today}"
            quota_json = self._get_state(user_id, quota_key, "{}")
            try:
                quotas = json.loads(quota_json)
            except:
                quotas = {}
            quotas[slot] = quotas.get(slot, 0) + 1
            self._set_state(user_id, quota_key, json.dumps(quotas))

    def _get_time_slot(self, hour: int) -> str | None:
        """获取时段 - 包含深夜"""
        if 7 <= hour < 12:
            return "morning"
        elif 12 <= hour < 18:
            return "afternoon"
        elif 18 <= hour < 23:
            return "evening"
        elif 23 <= hour or hour < 2:
            return "late_night"
        return None

    def get_mutter_stats(self, user_id: str) -> str:
        """查看今日碎碎念统计"""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        quota_key = f"mutter_quota_{today}"
        quota_json = self._get_state(user_id, quota_key, "{}")
        try:
            quotas = json.loads(quota_json)
        except:
            quotas = {}

        lines = ["今日碎碎念："]
        for slot, name in [("morning", "上午"), ("afternoon", "下午"), ("evening", "晚上"), ("late_night", "深夜")]:
            used = quotas.get(slot, 0)
            lines.append(f"  {name}: {used}/3")
        return "\n".join(lines)

    def get_mutter_time_hint(self) -> str:
        """获取碎碎念时间提示 - 与时间感知联动"""
        if self.time_awareness:
            return self.time_awareness.get_mutter_time_hint()
        # fallback
        now = datetime.now()
        hour = now.hour
        if 7 <= hour < 12:
            return "上午的碎碎念，可以聊聊今天打算做什么"
        elif 12 <= hour < 14:
            return "午休时间的碎碎念，轻松随意"
        elif 14 <= hour < 18:
            return "下午的碎碎念，可以聊聊工作进度"
        elif 18 <= hour < 23:
            return "晚上的碎碎念，可以聊聊今天发生了什么"
        elif 23 <= hour or hour < 2:
            return "深夜的碎碎念，可以聊聊创作灵感"
        return "凌晨的碎碎念，轻声自言自语"

    # ========== 主动关心系统 ==========

    def check_care_events(self, user_id: str) -> list[str]:
        """检查是否有需要关心的事件"""
        if not self.is_boot_safe():
            return []

        now = datetime.now()
        hour = now.hour
        if hour < 8:
            return []

        cares = []

        with self.db.get_conn() as conn:
            # 检查生活事件
            rows = conn.execute(
                "SELECT content, time FROM life_events "
                "WHERE shared = 1 "
                "ORDER BY time DESC LIMIT 20"
            ).fetchall()
            for r in rows:
                care = self._check_life_event_care(r, now)
                if care:
                    cares.append(care)

            # 检查成长记忆
            rows = conn.execute(
                "SELECT event, time, emotion FROM growth_memories "
                "WHERE user_id = ? AND category IN ('分享秘密', '情感共鸣', '关心回应') "
                "ORDER BY id DESC LIMIT 10",
                (user_id,)
            ).fetchall()
            for r in rows:
                care = self._check_growth_care(r, now)
                if care:
                    cares.append(care)

            # 检查长期记忆中的计划
            rows = conn.execute(
                "SELECT content, created_at FROM long_term_memory "
                "WHERE user_id = ? AND category = '计划' "
                "ORDER BY id DESC LIMIT 10",
                (user_id,)
            ).fetchall()
            for r in rows:
                care = self._check_plan_care(r, now)
                if care:
                    cares.append(care)

        # 去重
        seen = set()
        unique = []
        for c in cares:
            if c not in seen:
                seen.add(c)
                unique.append(c)

        return unique[:2]

    def _check_life_event_care(self, row, now):
        content = row[0] if row else ""
        event_time = row[1] if len(row) > 1 else ""
        if not content or not event_time:
            return None
        try:
            event_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S")
        except:
            try:
                event_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M")
            except:
                return None
        hours_after = (now - event_dt).total_seconds() / 3600
        if 1 <= hours_after <= 6:
            if any(kw in content for kw in ["面试", "考试", "比赛", "手术", "体检"]):
                return f"你之前提到的「{content[:20]}」，结果怎么样？"
            if any(kw in content for kw in ["生日", "聚会", "约会", "旅行"]):
                return f"「{content[:20]}」好玩吗？"
        return None

    def _check_growth_care(self, row, now):
        event = row[0] if row else ""
        event_time = row[1] if len(row) > 1 else ""
        emotion = row[2] if len(row) > 2 else ""
        if not event or not event_time:
            return None
        try:
            event_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M:%S")
        except:
            try:
                event_dt = datetime.strptime(event_time, "%Y-%m-%d %H:%M")
            except:
                return None
        hours_after = (now - event_dt).total_seconds() / 3600
        if emotion in ["难过", "生气", "焦虑"] and 2 <= hours_after <= 8:
            return f"你之前好像心情不太好，现在好点了吗？"
        return None

    def _check_plan_care(self, row, now):
        content = row[0] if row else ""
        if not content:
            return None
        plan_keywords = ["考试", "面试", "截止", "ddl", "生日", "聚会", "旅行"]
        if any(kw in content for kw in plan_keywords):
            return f"你之前提到的「{content[:20]}」，准备得怎么样了？"
        return None

    def get_care_prompt(self, cares: list[str]) -> str:
        """将关心事件列表组装成 prompt 注入上下文"""
        if not cares:
            return ""
        lines = ["[主动关心提醒]", "你有以下事情想要关心一下用户，可以自然地提起："]
        for i, care in enumerate(cares, 1):
            lines.append(f"{i}. {care}")
        lines.append("\n规则：只挑一件提起就好，不要全部都说。用自然的语气，像突然想起来一样。")
        return "\n".join(lines)

    # ========== 定时任务联动 ==========

    def check_scheduled_tasks(self, user_id: str, time_awareness=None) -> str:
        """检查定时任务并生成提醒 prompt"""
        ta = time_awareness or self.time_awareness
        if not ta:
            return ""
        return ta.get_pending_tasks_prompt(user_id)

    def get_proactive_time_hint(self) -> str:
        """获取主动消息时间提示"""
        if self.time_awareness:
            return self.time_awareness.get_proactive_time_hint()
        return ""

    # ========== 随机问候（不再催睡觉）==========

    def get_random_greeting(self, hour: int) -> str | None:
        """基于时间的随机问候语 - 不再催睡觉"""
        greetings = {
            "morning": [
                "起来了没",
                "早",
                "今天有什么安排",
            ],
            "noon": [
                "吃了吗",
                "午休了",
            ],
            "afternoon": [
                "在忙吗",
                "下午了",
            ],
            "evening": [
                "忙完了吗",
                "今天怎么样",
            ],
            "night": [
                "在干嘛",
                "还没睡啊",
            ],
            "late_night": [
                "还在啊",
                "在干嘛呢",
                "没睡呢",
            ],
        }

        if 6 <= hour < 12:
            slot = "morning"
        elif 12 <= hour < 14:
            slot = "noon"
        elif 14 <= hour < 18:
            slot = "afternoon"
        elif 18 <= hour < 22:
            slot = "evening"
        elif 22 <= hour or hour < 2:
            slot = "night"
        elif 2 <= hour < 6:
            slot = "late_night"
        else:
            return None

        options = greetings.get(slot, [])
        return random.choice(options) if options else None

# [0.0.5 REFACTORED] v3 - 碎碎念时间联动 + 定时任务 + 去除催睡觉
