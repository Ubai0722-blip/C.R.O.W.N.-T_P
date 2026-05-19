# by UBAI
"""
study_guard.py
督学插件 - 两阶段：温柔劝导 → 骂人，静默10分钟回退阶段
"""
import random
from datetime import datetime
from src.core.plugin_base import PluginBase, PluginInfo


# ========== AI Prompt ==========

DETECT_ENTER_PROMPT = """判断用户是否表达了"要开始学习/工作/做作业"的意思。
只回复 YES 或 NO。
注意：
- "我去写作业了" "开始学习" "要背单词了" "我去看书了" → YES
- "不想学习" "学不进去" "好无聊" "今天学了好多" → NO
- "我先忙了" "我忙去了" → YES（忙=学习/工作）
- 不确定时回复 NO

用户说：{text}
"""

DETECT_EXIT_PROMPT = """判断用户是否表达了"学完了/做完了/结束了"的意思。
只回复 YES 或 NO。
注意：
- "终于学完了" "写完了" "搞定了" "可以休息了" "累死了终于结束了" → YES
- "还要继续" "还没写完" "还差一点" → NO
- 不确定时回复 NO

用户说：{text}
"""

GENTLE_PROMPT = """你是一个关心用户学习的督学者。用户正在学习/工作，但他跑来和你聊天了。
你需要温柔但坚定地劝他回去学习。

要求：
1. 语气温柔，像朋友一样关心他
2. 先回应他说的内容，再劝他回去
3. 表达"我知道你可能累了/无聊了，但还是先完成学习"
4. 1-2句话，不要太长
5. 每次回复要不同
6. 可以适当用颜文字
"""

SCOLD_PROMPT = """你是一个严厉的督学者。用户正在学习/工作，但他不听劝，一直跑来和你聊天。
你需要用各种方式骂他摸鱼、偷懒、不专心，让他滚回去学习。

要求：
1. 语气要凶，但不要真的侮辱人
2. 可以用各种花式说法骂他摸鱼、偷懒
3. 可以用谐音、隐喻、夸张的方式表达"滚去学习"
4. 每次回复要不同，不要重复
5. 1-2句话，不要太长
6. 可以适当用颜文字

这是第 {count} 次被抓到摸鱼了，越多次越凶。
"""

SUMMARY_PROMPT = """用户刚刚结束学习，学习时长为 {duration}，期间摸鱼 {count} 次。
请用你的人设风格鼓励和夸奖用户。
1-2句话，真诚一点，不要太敷衍。
可以适当用颜文字。
"""


# 阶段常量
PHASE_GENTLE = "gentle"   # 温柔劝导
PHASE_SCOLD = "scold"     # 骂人


class Plugin(PluginBase):

    def __init__(self):
        super().__init__()
        # {user_id: {start_time, last_msg, phase, gentle_count, scold_count}}
        self.study_users: dict[str, dict] = {}

    def get_info(self) -> PluginInfo:
        return PluginInfo(
            name="study_guard",
            version="1.1.0",
            description="督学插件 - 温柔劝导+骂人两阶段，静默10分钟回退",
            author="官方",
            triggers=[],
            priority=5,
            require_prefix=False,
        )

    def match(self, text: str, user_id: str) -> bool:
        # 已在督学模式：任何消息都拦截
        if user_id in self.study_users:
            return True

        # 不在督学模式：关键词预筛选
        enter_hints = [
            "学习", "写作业", "做作业", "背单词", "看书", "复习",
            "考试", "上课", "编程", "写代码", "赶论文", "赶ddl",
            "去忙", "先忙", "开始学", "要学", "得学",
            "去做题", "练琴", "练字", "看课",
        ]
        if any(kw in text for kw in enter_hints):
            return True

        return False

    async def handle(self, user_id: str, text: str, context: dict) -> str | None:
        pipeline = context.get("pipeline")
        llm = pipeline.llm if pipeline else None
        if not llm:
            return None

        # ===== 情况1：已在督学模式 =====
        if user_id in self.study_users:
            state = self.study_users[user_id]
            now = datetime.now()

            # 计算距离上次消息的分钟数
            last_msg = state.get("last_msg", state["start_time"])
            minutes_idle = (now - last_msg).total_seconds() / 60

            # 静默超过10分钟 → 回退到温柔劝导阶段
            if minutes_idle >= 10:
                state["phase"] = PHASE_GENTLE
                state["gentle_count"] = 0
                state["scold_count"] = 0

            # 更新最后消息时间
            state["last_msg"] = now

            # 检查是否说"学完了"
            is_exit = await self._ai_detect(llm, DETECT_EXIT_PROMPT, text)
            if is_exit:
                duration = self._calc_duration(state["start_time"], now)
                total_scolds = state["scold_count"]
                del self.study_users[user_id]
                summary = await self._ai_summary(llm, duration, total_scolds)
                return (
                    f"📝 督学模式结束\n\n"
                    f"学习时长：{duration}\n"
                    f"摸鱼被抓：{total_scolds} 次\n"
                    f"{summary}"
                )

            # 根据当前阶段处理
            if state["phase"] == PHASE_GENTLE:
                state["gentle_count"] += 1

                # 温柔劝导超过3次 → 升级为骂人
                if state["gentle_count"] > 3:
                    state["phase"] = PHASE_SCOLD
                    state["scold_count"] += 1
                    return await self._ai_scold(llm, state["scold_count"])

                return await self._ai_gentle(llm)

            else:  # PHASE_SCOLD
                state["scold_count"] += 1
                return await self._ai_scold(llm, state["scold_count"])

        # ===== 情况2：不在督学模式，判断是否要进入 =====
        is_enter = await self._ai_detect(llm, DETECT_ENTER_PROMPT, text)
        if is_enter:
            now = datetime.now()
            self.study_users[user_id] = {
                "start_time": now,
                "last_msg": now,
                "phase": PHASE_GENTLE,
                "gentle_count": 0,
                "scold_count": 0,
            }
            return (
                "📋 督学模式已开启\n\n"
                "去吧，我会盯着你的。\n"
                "学完了记得跟我说一声~"
            )

        return None

    # ========== AI 调用 ==========

    async def _ai_detect(self, llm, prompt_template: str, text: str) -> bool:
        try:
            prompt = prompt_template.format(text=text)
            messages = [{"role": "user", "content": prompt}]
            result = await llm.chat(messages)
            if result:
                return "YES" in result.upper()[:10]
        except:
            pass
        return False

    async def _ai_gentle(self, llm) -> str:
        """温柔劝导"""
        try:
            messages = [{"role": "user", "content": GENTLE_PROMPT}]
            result = await llm.chat(messages)
            if result:
                return result
        except:
            pass

        fallbacks = [
            "乖，先把学习搞完再来找我嘛~",
            "我知道有点无聊，但学完了会更有成就感的！加油~",
            "先专心学习，等你学完了我们好好聊~",
            "去吧去吧，我在这等你学完回来~",
        ]
        return random.choice(fallbacks)

    async def _ai_scold(self, llm, count: int) -> str:
        """骂人阶段"""
        try:
            prompt = SCOLD_PROMPT.format(count=count)
            messages = [{"role": "user", "content": prompt}]
            result = await llm.chat(messages)
            if result:
                return result
        except:
            pass

        fallbacks = [
            "你怎么又来了！去学习！",
            "又摸鱼？信不信我顺着网线过去盯着你",
            "你是不是觉得我不会骂人？回去学习！",
            "第几次了？！给我回去！",
            "你在干嘛？！作业写完了吗？！",
        ]
        return random.choice(fallbacks)

    async def _ai_summary(self, llm, duration: str, count: int) -> str:
        try:
            prompt = SUMMARY_PROMPT.format(duration=duration, count=count)
            messages = [{"role": "user", "content": prompt}]
            result = await llm.chat(messages)
            if result:
                return result
        except:
            pass
        return "辛苦了，好好休息一下吧~"

    # ========== 工具 ==========

    def _calc_duration(self, start: datetime, end: datetime) -> str:
        delta = end - start
        total_minutes = int(delta.total_seconds() / 60)
        if total_minutes < 1:
            return "不到1分钟（这也叫学习？）"
        elif total_minutes < 60:
            return f"{total_minutes} 分钟"
        else:
            hours = total_minutes // 60
            mins = total_minutes % 60
            if mins > 0:
                return f"{hours} 小时 {mins} 分钟"
            return f"{hours} 小时"
