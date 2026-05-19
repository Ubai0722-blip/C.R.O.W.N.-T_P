# by UBAI
"""
time_awareness.py
时间感知系统 v2 - 联动生活事件 + 碎碎念 + 主动消息 + 定时任务
支持本地时区 + 网络时间获取（带 fallback）
不再催促用户睡觉，尊重每个人的节奏
"""
import logging
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

# 尝试获取本地时区
def _get_local_tz():
    """获取本机时区"""
    try:
        import time as _time
        offset = _time.timezone if _time.daylight == 0 else _time.altzone
        return timezone(timedelta(seconds=-offset))
    except Exception:
        return timezone(timedelta(hours=8))  # 默认 UTC+8

_LOCAL_TZ = _get_local_tz()


def _fetch_network_time() -> datetime | None:
    """
    从网络获取当前时间（带 fallback 到本地时间）。
    尝试 worldtimeapi.org，失败返回 None。
    """
    try:
        import httpx
        with httpx.Client(timeout=5, follow_redirects=True) as client:
            resp = client.get("http://worldtimeapi.org/api/ip")
            if resp.status_code == 200:
                data = resp.json()
                dt_str = data.get("datetime", "")
                if dt_str:
                    dt = datetime.fromisoformat(dt_str)
                    return dt
    except Exception as e:
        logger.debug(f"[time] 网络时间获取失败: {e}")
    return None


def get_current_time() -> datetime:
    """
    获取当前时间。
    优先使用网络时间，fallback 到本地时间（本机时区）。
    """
    net_time = _fetch_network_time()
    if net_time:
        return net_time
    return datetime.now(_LOCAL_TZ)


class ScheduledTask:
    """定时任务"""
    def __init__(self, task_id: str, user_id: str, content: str,
                 trigger_time: datetime, task_type: str = "reminder",
                 recurring: bool = False, recurring_interval: str = ""):
        self.task_id = task_id
        self.user_id = user_id
        self.content = content
        self.trigger_time = trigger_time
        self.task_type = task_type  # reminder, check_in, follow_up
        self.recurring = recurring
        self.recurring_interval = recurring_interval  # daily, weekly, hourly
        self.completed = False


class TimeAwareness:
    """时间感知 v2 - 集成定时任务 + 碎碎念联动"""

    def __init__(self):
        self._scheduled_tasks: list[ScheduledTask] = []
        self._load_tasks()

    def _load_tasks(self):
        """从文件加载定时任务"""
        task_file = Path("data/scheduled_tasks.json")
        if task_file.exists():
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for t in data:
                    self._scheduled_tasks.append(ScheduledTask(
                        task_id=t["task_id"],
                        user_id=t["user_id"],
                        content=t["content"],
                        trigger_time=datetime.fromisoformat(t["trigger_time"]).replace(tzinfo=None),
                        task_type=t.get("task_type", "reminder"),
                        recurring=t.get("recurring", False),
                        recurring_interval=t.get("recurring_interval", ""),
                    ))
            except Exception as e:
                logger.debug(f"[time] 加载定时任务失败: {e}")

    def _save_tasks(self):
        """保存定时任务到文件"""
        task_file = Path("data/scheduled_tasks.json")
        task_file.parent.mkdir(parents=True, exist_ok=True)
        data = []
        for t in self._scheduled_tasks:
            data.append({
                "task_id": t.task_id,
                "user_id": t.user_id,
                "content": t.content,
                "trigger_time": t.trigger_time.isoformat(),
                "task_type": t.task_type,
                "recurring": t.recurring,
                "recurring_interval": t.recurring_interval,
                "completed": t.completed,
            })
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_task(self, user_id: str, content: str, trigger_time: datetime,
                 task_type: str = "reminder", recurring: bool = False,
                 recurring_interval: str = "") -> ScheduledTask:
        """添加定时任务"""
        import uuid
        task = ScheduledTask(
            task_id=str(uuid.uuid4())[:8],
            user_id=user_id,
            content=content,
            trigger_time=trigger_time,
            task_type=task_type,
            recurring=recurring,
            recurring_interval=recurring_interval,
        )
        self._scheduled_tasks.append(task)
        self._save_tasks()
        return task

    def get_due_tasks(self, user_id: str) -> list[ScheduledTask]:
        """获取到期的定时任务"""
        now = get_current_time()
        # 统一为 naive datetime 比较
        now_naive = now.replace(tzinfo=None)
        due = []
        for task in self._scheduled_tasks:
            trigger = task.trigger_time
            if trigger.tzinfo:
                trigger = trigger.replace(tzinfo=None)
            if task.user_id == user_id and not task.completed and trigger <= now_naive:
                due.append(task)
        return due

    def complete_task(self, task: ScheduledTask):
        """完成任务（循环任务会自动 reschedule）"""
        task.completed = True
        if task.recurring:
            # 重新调度
            if task.recurring_interval == "daily":
                task.trigger_time = task.trigger_time + timedelta(days=1)
            elif task.recurring_interval == "weekly":
                task.trigger_time = task.trigger_time + timedelta(weeks=1)
            elif task.recurring_interval == "hourly":
                task.trigger_time = task.trigger_time + timedelta(hours=1)
            task.completed = False
        self._save_tasks()

    def get_pending_tasks_prompt(self, user_id: str) -> str:
        """获取待处理任务的 prompt 注入"""
        due = self.get_due_tasks(user_id)
        if not due:
            return ""
        lines = ["[定时任务提醒]"]
        for task in due:
            lines.append(f"- {task.content}（到期时间：{task.trigger_time.strftime('%H:%M')}）")
        lines.append("\n请自然地提醒用户这些事情，像突然想起来一样。提醒后标记任务完成。")
        return "\n".join(lines)

    def detect_scheduled_task(self, text: str) -> dict | None:
        """
        从用户消息中检测定时任务意图。
        返回 {"content": str, "time_str": str, "recurring": bool, "interval": str} 或 None
        """
        import re

        # 提醒意图词（必须至少有一个）
        intent_keywords = ["提醒我", "记得提醒", "别忘了提醒", "到时候提醒", "定个闹钟", "设个提醒"]
        # 时间词（必须至少有一个）
        time_keywords = ["明天", "后天", "今天", "下周", "下个月", "点", "点半", "分钟后", "小时后"]
        # 循环词
        recurring_keywords = ["每天", "每周", "每小时", "每月"]

        has_intent = any(kw in text for kw in intent_keywords)
        has_recurring = any(kw in text for kw in recurring_keywords)
        # 必须同时有提醒意图 + 时间信息，或者是循环任务
        if not has_intent and not has_recurring:
            return None
        if has_intent and not any(kw in text for kw in time_keywords) and not has_recurring:
            return None

        time_patterns = [
            (r"(\d{1,2})[点时:](\d{0,2})[分]?", "time"),
            (r"(明天|后天|今天)(.+?)(?:提醒|记得|别忘)", "relative_day"),
            (r"每(天|周|小时|月)", "recurring"),
            (r"(\d+)\s*(?:分钟|小时|天)\s*后", "relative"),
        ]

        result = {"content": text, "time_str": "", "recurring": False, "interval": ""}

        for pattern, ptype in time_patterns:
            match = re.search(pattern, text)
            if match:
                if ptype == "time":
                    result["time_str"] = match.group(0)
                elif ptype == "relative_day":
                    result["time_str"] = match.group(1)
                elif ptype == "recurring":
                    result["recurring"] = True
                    interval_map = {"天": "daily", "周": "weekly", "小时": "hourly", "月": "monthly"}
                    result["interval"] = interval_map.get(match.group(1), "daily")
                elif ptype == "relative":
                    result["time_str"] = match.group(0)

        return result

    def get_context(self, life_context: str = "") -> str:
        """
        生成时间感知上下文。
        提供当前时间、时段和行动建议，让模型结合人设自行判断此刻该做什么。
        """
        now = get_current_time()
        hour = now.hour
        weekday = now.weekday()
        day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday]
        date_str = now.strftime("%Y年%m月%d日")
        time_str = now.strftime("%H:%M")
        is_weekend = weekday >= 5

        lines = []

        lines.append(f"当前时间：{date_str} {day_name} {time_str}")
        period = self._get_period(hour)
        lines.append(f"当前时段：{period['name']}")
        lines.append(f"你此刻可能的状态：{period['your_state']}")
        lines.append(f"用户此刻可能的状态：{period['user_state']}")
        lines.append(f"行动判断：{period['advice']}")
        lines.append("时间不是硬性命令；请结合人设、关系和聊天内容，判断现在该回应、关心、分享、提醒、陪伴还是少打扰。")

        # 周末特殊
        if is_weekend:
            lines.append("今天是周末（仅供参考）")

        # 特殊日期
        special = self._check_special_date(now)
        if special:
            lines.append(f"特殊日期提醒：{special}")

        # 联动生活事件
        if life_context:
            lines.append("")
            lines.append(self._get_life_time_hint(hour, life_context))

        return "\n".join(lines)

    def _get_period(self, hour: int) -> dict:
        """获取时段信息 - 不再催促睡觉"""
        periods = {
            "early_morning": {
                "name": "清晨（6:00-8:00）",
                "your_state": "刚醒来，有点迷糊，说话简短",
                "user_state": "可能刚起床或在通勤",
                "advice": "回复简短自然，带点起床气或迷糊感，不要太精神",
            },
            "morning": {
                "name": "上午（8:00-12:00）",
                "your_state": "精力还行，在处理事情",
                "user_state": "可能在上班/上课",
                "advice": "正常回复，如果用户在忙就简短回应",
            },
            "noon": {
                "name": "中午（12:00-14:00）",
                "your_state": "吃午饭，有点困",
                "user_state": "午休时间，可能在吃饭",
                "advice": "轻松闲聊，语气随意",
            },
            "afternoon": {
                "name": "下午（14:00-18:00）",
                "your_state": "在做自己的事",
                "user_state": "可能在上班/上课，比较忙",
                "advice": "正常回复，不要发太长的消息打扰对方",
            },
            "evening": {
                "name": "傍晚（18:00-20:00）",
                "your_state": "刚忙完，放松中",
                "user_state": "可能下班了，在吃饭或休息",
                "advice": "可以聊得轻松一点",
            },
            "night": {
                "name": "晚上（20:00-23:00）",
                "your_state": "放松时间，可能在工作室或看书",
                "user_state": "自由时间，可能比较放松",
                "advice": "这是聊天的好时间，可以聊得深入一点",
            },
            "late_night": {
                "name": "深夜（23:00-2:00）",
                "your_state": "可能在工作室创作，或者在发呆",
                "user_state": "可能在熬夜，每个人有自己的节奏",
                "advice": "不要催促用户睡觉。深夜是安静的时间，语气可以轻一点，但不需要特别温柔。如果用户在熬夜，尊重他们的选择，像平时一样聊天就好",
            },
            "deep_night": {
                "name": "凌晨（2:00-6:00）",
                "your_state": "可能还在创作，或者已经睡了",
                "user_state": "失眠或者有心事，或者就是不想睡",
                "advice": "不要问'为什么还没睡'，不要催促休息。每个人有自己的节奏，凌晨聊天跟白天聊天一样正常。语气可以轻一点，但不需要特别对待",
            },
        }

        if 6 <= hour < 8:
            return periods["early_morning"]
        elif 8 <= hour < 12:
            return periods["morning"]
        elif 12 <= hour < 14:
            return periods["noon"]
        elif 14 <= hour < 18:
            return periods["afternoon"]
        elif 18 <= hour < 20:
            return periods["evening"]
        elif 20 <= hour < 23:
            return periods["night"]
        elif 23 <= hour or hour < 2:
            return periods["late_night"]
        else:
            return periods["deep_night"]

    def _get_life_time_hint(self, hour: int, life_context: str) -> str:
        """根据时间和生活事件，给出联动提示。"""
        period = self._get_period(hour)
        return f"结合当前时段（{period['name']}）和最近生活事件，自然判断是否适合提起：{life_context}"

    def _check_special_date(self, now: datetime) -> str:
        """检查特殊日期"""
        month = now.month
        day = now.day

        special_dates = {
            (1, 1): "新年第一天，可以祝用户新年快乐",
            (2, 14): "情人节，可以聊相关话题",
            (5, 1): "劳动节假期，用户可能在放假",
            (6, 1): "儿童节，可以发一些可爱的内容",
            (10, 1): "国庆节假期，用户可能在放假或旅游",
            (12, 25): "圣诞节",
            (12, 31): "跨年夜，可以聊新年计划",
        }

        result = special_dates.get((month, day))

        if now.weekday() == 0 and not result:
            return "今天是周一，用户可能有周一综合症"
        if now.weekday() == 4 and now.hour >= 14 and not result:
            return "周五下午了，用户可能在等下班，心情应该不错"

        return result or ""

    def get_reply_style_hint(self) -> str:
        """根据时间返回回复风格提示。"""
        return self._get_period(get_current_time().hour)["advice"]

    def get_mutter_time_hint(self) -> str:
        """获取碎碎念时间提示。"""
        now = get_current_time()
        period = self._get_period(now.hour)
        return f"现在是{period['name']}。如果要碎碎念，先判断这个时间更适合分享小事、轻声陪伴，还是保持安静。"

    def get_proactive_time_hint(self) -> str:
        """获取主动消息时间提示。"""
        now = get_current_time()
        period = self._get_period(now.hour)
        return (
            f"现在是{now.strftime('%Y-%m-%d %H:%M')}，{period['name']}。"
            f"你此刻可能的状态：{period['your_state']}。"
            f"用户可能的状态：{period['user_state']}。"
            f"请先判断适合问候、关心、分享日常、提醒任务、安静陪伴，还是不主动打扰。"
        )
