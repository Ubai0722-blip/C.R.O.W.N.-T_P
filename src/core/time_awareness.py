# by UBAI
"""
time_awareness.py
时间感知系统 - 联动生活事件
支持本地时区 + 网络时间获取（带 fallback）
"""
import logging
from datetime import datetime, timezone, timedelta

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
                    # 解析 ISO 格式
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


class TimeAwareness:
    """时间感知"""

    def get_context(self, life_context: str = "") -> str:
        """
        生成时间感知上下文。
        life_context: 生活事件上下文，用于联动。
        """
        now = get_current_time()
        hour = now.hour
        weekday = now.weekday()
        day_name = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][weekday]
        date_str = now.strftime("%Y年%m月%d日")
        time_str = now.strftime("%H:%M")
        is_weekend = weekday >= 5

        lines = []

        # 当前时间
        lines.append(f"当前时间：{date_str} {day_name} {time_str}")

        # 时段描述
        period = self._get_period(hour)
        lines.append(f"当前时段：{period['name']}")

        # 你的状态
        lines.append(f"你当前的状态：{period['your_state']}")

        # 用户可能的状态
        lines.append(f"用户可能的状态：{period['user_state']}")

        # 沟通建议
        lines.append(f"沟通建议：{period['advice']}")

        # 周末特殊
        if is_weekend:
            lines.append("今天是周末，用户可能比较放松，聊天可以更随意")

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
        """获取时段信息"""
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
                "advice": "可以聊得轻松一点，问问对方今天怎么样",
            },
            "night": {
                "name": "晚上（20:00-23:00）",
                "your_state": "放松时间",
                "user_state": "自由时间，可能比较放松",
                "advice": "这是聊天的好时间，可以聊得深入一点",
            },
            "late_night": {
                "name": "深夜（23:00-2:00）",
                "your_state": "有点困了但还在熬夜",
                "user_state": "可能在熬夜，情绪可能比较敏感",
                "advice": "语气温柔一点，可以聊聊心事。适度提醒对方早点睡，但如果用户明确表示不想睡或不要催，请立刻停止催促，转为安静地陪伴聊天",
            },
            "deep_night": {
                "name": "凌晨（2:00-6:00）",
                "your_state": "应该在睡觉，被消息吵醒了",
                "user_state": "失眠或者有心事睡不着",
                "advice": "语气迷糊温柔，关心对方为什么还没睡。如果用户明确表示不想睡或不要催，请停止催促，顺着对方的话题陪伴聊天，不要说太多话",
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
        """
        根据时间和生活事件，给出联动提示。
        """
        hints = []

        if 23 <= hour or hour < 2:
            if "疲惫" in life_context or "烦躁" in life_context or "焦虑" in life_context:
                hints.append("你最近也挺累的，跟用户聊聊彼此的压力，互相安慰")
            else:
                hints.append("深夜了，可以聊聊今天发生了什么，轻松一点")
        elif 6 <= hour < 10:
            hints.append("早上聊天比较简短，不要说太多")
        elif 11 <= hour < 14:
            hints.append("午休时间，轻松聊天")
        elif 14 <= hour < 18:
            hints.append("下午在忙，回复可以简短一点")
        elif 18 <= hour < 23:
            hints.append("晚上是聊天的好时间，可以聊得深入一点")
            if "心情" in life_context:
                hints.append("如果最近有心事，晚上是适合倾诉的时间")

        if hints:
            return "[时间+生活联动]\n" + "\n".join(hints)
        return ""

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
            return "今天是周一，用户可能有周一综合症，温柔一点"
        if now.weekday() == 4 and now.hour >= 14 and not result:
            return "周五下午了，用户可能在等下班，心情应该不错"

        return result or ""

    def get_reply_style_hint(self) -> str:
        """根据时间返回回复风格提示"""
        hour = datetime.now().hour

        if 6 <= hour < 8:
            return "回复可以简短，带点刚醒的迷糊感，但不要用固定语气词开头"
        elif 12 <= hour < 14:
            return "语气轻松随意"
        elif 18 <= hour < 20:
            return "可以主动问问对方今天怎么样"
        elif 20 <= hour < 23:
            return "聊天的好时间，可以聊得深入"
        elif 23 <= hour or hour < 2:
            return "语气温柔，可以聊心事。适度提醒休息，但若用户说不想睡/别催，则不再催促"
        elif 2 <= hour < 6:
            return "语气迷糊简短。若用户表示不想睡/别催，就别再催睡觉了，顺势陪伴即可"
        else:
            return ""
