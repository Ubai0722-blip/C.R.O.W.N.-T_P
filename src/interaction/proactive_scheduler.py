# by UBAI
"""
proactive_scheduler.py
主动陪伴调度器：统一选择主动消息触发原因，并记录可审计事件。
不引入“过度依赖”监控；仅处理时机、来源、冷却、安全前置和目标/提醒跟进。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import random
import uuid

from ..memory.database import Database


@dataclass
class ProactiveDecision:
    should_send: bool
    user_id: str
    trigger_type: str
    reason: str
    extra_context: str = ""
    event_id: str = ""
    status: str = "skipped"


class ProactiveScheduler:
    def __init__(self, proactive_system, growth_system=None, time_awareness=None, safety_monitor=None):
        self.proactive = proactive_system
        self.growth = growth_system
        self.time_awareness = time_awareness
        self.safety = safety_monitor
        self.db = Database()
        self._ensure_tables()

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def _norm_text(text: str) -> str:
        if not text:
            return ""
        t = str(text).lower().replace("|||", " ")
        for ch in " \t\r\n，。！？；：,.!?;:（）()[]{}\"'":
            t = t.replace(ch, "")
        return t

    def _ensure_tables(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS proactive_events (
                    event_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    trigger_type TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    extra_context TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    sent_at TEXT DEFAULT '',
                    meta_json TEXT DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proactive_events_user ON proactive_events(user_id, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_proactive_events_status ON proactive_events(status)")

    def _set_user(self, user_id: str):
        try:
            self.db.set_user(user_id)
        except Exception:
            pass

    def _record(self, user_id: str, trigger_type: str, reason: str, status: str, extra_context: str = "", meta: dict | None = None) -> str:
        self._set_user(user_id)
        self._ensure_tables()
        event_id = str(uuid.uuid4())
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO proactive_events "
                "(event_id, user_id, trigger_type, reason, status, extra_context, created_at, meta_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    user_id,
                    trigger_type,
                    reason,
                    status,
                    extra_context,
                    self._now(),
                    json.dumps(meta or {}, ensure_ascii=False),
                ),
            )
        return event_id

    def _filter_recent_cares(self, user_id: str, cares: list[str], cooldown_hours: int = 8) -> list[str]:
        """去掉最近已发送过的同话题关心项，避免反复提同一件事。"""
        if not cares:
            return []
        threshold = (datetime.now() - timedelta(hours=cooldown_hours)).strftime("%Y-%m-%d %H:%M:%S")
        self._set_user(user_id)
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT meta_json FROM proactive_events "
                "WHERE user_id = ? AND trigger_type = 'care_event' AND status = 'sent' "
                "AND COALESCE(NULLIF(sent_at, ''), created_at) >= ? "
                "ORDER BY created_at DESC LIMIT 30",
                (user_id, threshold),
            ).fetchall()

        recent = set()
        for row in rows:
            raw = row[0] if row else ""
            if not raw:
                continue
            try:
                meta = json.loads(raw)
            except Exception:
                continue
            for item in meta.get("cares", []) or []:
                norm = self._norm_text(item)
                if norm:
                    recent.add(norm)

        filtered = []
        for care in cares:
            norm = self._norm_text(care)
            if not norm:
                continue
            if norm in recent:
                continue
            filtered.append(care)
        return filtered

    def mark_sent(self, decision: ProactiveDecision):
        if not decision.event_id:
            return
        self._set_user(decision.user_id)
        now = self._now()
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE proactive_events SET status = 'sent', sent_at = ? WHERE event_id = ?",
                (now, decision.event_id),
            )
        if decision.trigger_type == "scheduled_task" and self.time_awareness:
            try:
                for task in self.time_awareness.get_due_tasks(decision.user_id):
                    self.time_awareness.complete_task(task)
            except Exception:
                pass
        if decision.trigger_type == "goal_followup" and self.growth:
            try:
                for goal in self.growth.get_due_goal_followups(decision.user_id):
                    self.growth.update_goal(goal.goal_id, next_follow_up="")
                    self.growth.log_goal_event(goal.goal_id, decision.user_id, "proactive_followup_sent", decision.reason)
            except Exception:
                pass

    def mark_failed(self, decision: ProactiveDecision, reason: str = "send_failed"):
        if not decision.event_id:
            return
        self._set_user(decision.user_id)
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE proactive_events SET status = ?, meta_json = ? WHERE event_id = ?",
                ("failed", json.dumps({"reason": reason}, ensure_ascii=False), decision.event_id),
            )

    def decide(self, user_id: str, relationship_level: int, config: dict | None = None) -> ProactiveDecision:
        config = config or {}
        self._set_user(user_id)
        self._ensure_tables()

        hour = datetime.now().hour
        quiet_start = int(config.get("quiet_hours_start", 0) or 0)
        quiet_end = int(config.get("quiet_hours_end", 7) or 7)
        if quiet_start <= hour < quiet_end:
            return self._skip(user_id, "quiet_hours", f"当前 {hour} 点处于静默时段")

        if self.safety:
            allowed, safety_reason = self.safety.proactive_precheck(user_id)
            if not allowed:
                return self._skip(user_id, "safety_block", safety_reason)

        task_prompt = ""
        if self.time_awareness:
            task_prompt = self.time_awareness.get_pending_tasks_prompt(user_id)
        if task_prompt:
            return self._send(user_id, "scheduled_task", "定时任务到期", task_prompt)

        goal_prompt = ""
        if self.growth:
            goal_prompt = self.growth.get_due_goal_prompt(user_id)
        if goal_prompt:
            return self._send(user_id, "goal_followup", "成长目标到达跟进时间", goal_prompt)

        care_chance = float(config.get("care_trigger_chance", 0.8) or 0.8)
        care_cooldown_hours = int(config.get("care_topic_cooldown_hours", 8) or 8)
        cares = self.proactive.check_care_events(user_id)
        cares = self._filter_recent_cares(user_id, cares, cooldown_hours=care_cooldown_hours)
        if cares:
            if random.random() < care_chance:
                return self._send(
                    user_id,
                    "care_event",
                    "存在可关心事件",
                    self.proactive.get_care_prompt(cares),
                    {"cares": cares},
                )
            return self._skip(user_id, "care_probability", "有可关心事件，但本轮概率未触发", {"cares": cares})

        if config.get("mutter_enabled", True) and self.proactive.should_send_mutter(user_id):
            hint = self.proactive.get_mutter_time_hint()
            extra = "[碎碎念触发]\n现在适合发一条轻量、自然的日常消息。"
            if hint:
                extra += f"\n时间风格：{hint}"
            return self._send(user_id, "mutter", "碎碎念冷却和配额通过", extra)

        if self.proactive.should_send_proactive(user_id, relationship_level):
            return self._send(user_id, "ordinary_proactive", "普通主动消息冷却和概率通过", "")

        return self._skip(user_id, "cooldown_or_probability", "冷却、用户活跃度或概率判断未通过")

    def _send(self, user_id: str, trigger_type: str, reason: str, extra_context: str = "", meta: dict | None = None) -> ProactiveDecision:
        event_id = self._record(user_id, trigger_type, reason, "planned", extra_context, meta)
        return ProactiveDecision(True, user_id, trigger_type, reason, extra_context, event_id, "planned")

    def _skip(self, user_id: str, trigger_type: str, reason: str, meta: dict | None = None) -> ProactiveDecision:
        event_id = self._record(user_id, trigger_type, reason, "skipped", "", meta)
        return ProactiveDecision(False, user_id, trigger_type, reason, "", event_id, "skipped")
