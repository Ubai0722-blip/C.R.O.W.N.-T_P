# by UBAI
"""
emotion.py v2
情绪识别模块 - 增强版
新增：中文网络用语词库、意图识别层、三阶段响应流程
"""
import re
import random
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.database import Database


@dataclass
class EmotionResult:
    """情绪识别结果"""
    primary: str
    intensity: str
    tags: list[str] = field(default_factory=list)
    context_hint: str = ""
    source: str = "text"
    sentiment: str = "中性"  # 新增：正向/中性/负向
    intent: str = ""  # 新增：用户意图


# ========== 情绪关键词库（含中文网络用语）==========
EMOTION_KEYWORDS = {
    "开心": {
        "keywords": [
            "哈哈", "嘿嘿", "嘻嘻", "太好了", "开心", "高兴", "爽", "棒", "nice",
            "耶", "好耶", "哈哈哈哈哈", "笑死", "绝了", "太棒了", "好开心",
            "幸福", "满足", "快乐", "哈哈哈",
            # 网络用语
            "yyds", "绝绝子", "太可了", "好家伙", "冲冲冲", "爱了爱了",
            "上头", "DNA动了", "有被笑到", "笑不活了", "哈哈哈哈哈哈",
            "好家伙", "绝绝子", "属于是", "狠狠爱住", "真的会谢",
            "泰裤辣", "6", "666", "牛", "牛逼", "nb",
        ],
        "emoji": ["😊", "😄", "😁", "🎉", "🥳", "❤️", "💕"],
    },
    "难过": {
        "keywords": [
            "难过", "伤心", "哭", "呜呜", "好惨", "心痛", "难受", "不开心",
            "郁闷", "委屈", "想哭", "崩溃", "绝望", "心塞", "唉",
            "好烦", "烦死了", "烦", "累", "心累",
            # 网络用语
            "破防了", "破大防", "emo", "e了", "玉玉了", "玉玉症",
            "抑郁了", "裂开", "心态崩了", "绷不住了", "泪目", "暴风哭泣",
            "好家伙我直接哭", "真的会哭", "蚌埠住了", "我不李姐",
        ],
        "emoji": ["😢", "😭", "💔", "😞", "😔", "🥺"],
    },
    "生气": {
        "keywords": [
            "生气", "气死", "愤怒", "烦死", "讨厌", "无语", "离谱",
            "过分", "受不了", "忍不了", "什么鬼", "有病", "垃圾",
            "操", "草", "靠", "我去", "我靠",
            # 网络用语
            "拳头硬了", "血压上来了", "有被冒犯到", "阿这", "啊这",
            "无大语", "离大谱", "真下头", "下头", "yue", "吐了",
            "给我整无语了", "我真的会谢", "拳头硬了",
        ],
        "emoji": ["😡", "🤬", "😤", "💢"],
    },
    "焦虑": {
        "keywords": [
            "焦虑", "担心", "紧张", "害怕", "慌", "不安", "压力大",
            "怎么办", "来不及了", "完蛋", "糟糕", "急", "赶",
            "焦虑死了", "好慌",
            # 网络用语
            "救命", "救", "我giao", "慌得一批", "人麻了", "头大",
            "要命", "寄", "g了", "gg", "芭比Q了", "芭比q",
        ],
        "emoji": ["😰", "😨", "😟", "😥"],
    },
    "疲惫": {
        "keywords": [
            "累", "好累", "累了", "困", "想睡", "撑不住", "没力气",
            "不想动", "精疲力尽", "身心俱疲", "好困", "困死了",
            "不想干了", "摆烂", "躺平",
            # 网络用语
            "卷不动了", "摆了", "开摆", "开躺", "废了", "不行了",
            "顶不住了", "肝不动了", "摸鱼", "划水",
        ],
        "emoji": ["😩", "😫", "🥱", "😪"],
    },
    "敷衍": {
        "keywords": ["嗯", "哦", "好", "行", "知道了", "随便", "都行", "ok",
                      "嗯嗯", "噢", "好吧", "啊对对对", "你说的对"],
        "emoji": [],
    },
    "撒娇": {
        "keywords": [
            "嘛", "呜呜呜", "人家", "求你了", "拜托", "好不好",
            "你帮帮我", "我不管", "就要", "哼", "讨厌啦",
            "你欺负我", "不理你了",
            # 网络用语
            "嘤嘤嘤", "qwq", "QAQ", "TAT", "ovo", "pwp",
            "贴贴", "抱抱", "蹭蹭", "要抱抱",
        ],
        "emoji": ["🥺", "👉👈", "🙇", "💕"],
    },
    "好奇": {
        "keywords": [
            "为什么", "怎么回事", "什么意思", "真的吗", "是吗",
            "然后呢", "后来呢", "怎么了", "发生什么", "啥情况",
            "好奇", "想知道",
            # 网络用语
            "细说", "展开说说", "细嗦", "展开讲讲",
        ],
        "emoji": ["🤔", "❓", "👀"],
    },
    "无聊": {
        "keywords": ["无聊", "好无聊", "没事干", "闲", "没意思",
                      "打发时间", "闲得慌", "百无聊赖", "无所事事"],
        "emoji": ["😑", "😐", "🥱"],
    },
    "感动": {
        "keywords": [
            "感动", "暖心", "谢谢你", "太好了", "好温柔",
            "你真好", "被治愈了", "眼眶湿了", "破防了",
            # 网络用语
            "磕到了", "嗑到了", "好甜", "awsl", "啊我死了",
            "太暖了", "被暖到",
        ],
        "emoji": ["🥹", "😭", "❤️", "💕", "🥰"],
    },
    "嘲讽": {
        "keywords": [
            "呵呵", "厉害", "真棒", "了不起", "好厉害哦",
            # 网络用语
            "典", "典中典", "孝", "孝死了", "急了急了",
            "乐", "乐了", "蚌", "好家伙", "啊对对对",
            "确实", "是这样的", "懂的都懂",
        ],
        "emoji": ["😏", "🙄", "💅"],
    },
    "惊讶": {
        "keywords": [
            "啊", "卧槽", "我靠", "天啊", "不会吧", "真的假的",
            "震惊", "惊了",
            # 网络用语
            "好家伙", "啊这", "阿这", "我直接好家伙",
            "万万没想到", "居然", "竟然",
        ],
        "emoji": ["😱", "🤯", "😳", "❗"],
    },
}

INTENSITY_BOOSTERS = ["太", "超级", "非常", "特别", "真的", "真的好", "好", "巨", "贼",
                       "极其", "超", "暴", "狂", "疯狂"]
INTENSITY_LOWERS = ["有点", "稍微", "一点点", "略微", "还好", "似乎", "好像"]


# ========== 意图识别 ==========
INTENT_PATTERNS = {
    "求助": {
        "keywords": ["怎么办", "帮帮我", "救救我", "怎么解决", "有什么办法",
                      "你帮我想想", "给个建议", "指点一下"],
        "priority": 3,
    },
    "倾诉": {
        "keywords": ["我跟你说", "你知道吗", "有件事", "我想说", "憋不住了",
                      "想找人聊聊", "你能听我说"],
        "priority": 2,
    },
    "分享": {
        "keywords": ["你看", "我跟你说", "今天", "刚才", "你知道吗",
                      "分享一下", "告诉你一件事"],
        "priority": 1,
    },
    "提问": {
        "keywords": ["什么是", "为什么", "怎么", "哪个", "什么时候",
                      "你觉得", "你怎么看", "是不是"],
        "priority": 1,
    },
    "抱怨": {
        "keywords": ["烦死了", "受不了", "太坑了", "什么玩意", "垃圾",
                      "无语", "离谱", "过分"],
        "priority": 3,
    },
    "安慰需求": {
        "keywords": ["心情不好", "好难过", "我好累", "不想活了", "活着好累",
                      "没人理解我", "好孤独", "好寂寞"],
        "priority": 4,
    },
    "闲聊": {
        "keywords": ["在吗", "在干嘛", "干嘛呢", "无聊", "随便聊聊"],
        "priority": 0,
    },
    "表白": {
        "keywords": ["喜欢你", "爱你", "想你", "你好好", "你好可爱",
                      "你好好看", "心动了"],
        "priority": 2,
    },
}


# ========== 情绪状态机 ==========
EMOTION_VALUES = {
    "开心": 0.8, "感动": 0.5, "撒娇": 0.3, "好奇": 0.1,
    "无聊": -0.1, "敷衍": -0.2, "疲惫": -0.4, "焦虑": -0.5,
    "难过": -0.7, "生气": -0.8, "嘲讽": -0.2, "惊讶": 0.1, "平静": 0.0,
}

USER_IMPACT = {
    "开心": 0.2, "感动": 0.15, "撒娇": 0.1, "好奇": 0.05,
    "无聊": -0.05, "敷衍": -0.1, "疲惫": -0.15, "焦虑": -0.2,
    "难过": -0.3, "生气": -0.25, "嘲讽": -0.1, "惊讶": 0.05, "平静": 0.0,
}

INTENSITY_MULTIPLIER = {"轻度": 0.5, "中度": 1.0, "强烈": 1.5}

SENTIMENT_MAP = {
    "开心": "正向", "感动": "正向", "撒娇": "正向", "好奇": "中性",
    "无聊": "中性", "敷衍": "中性", "惊讶": "中性", "嘲讽": "负向",
    "疲惫": "负向", "焦虑": "负向", "难过": "负向", "生气": "负向", "平静": "中性",
}


class EmotionState:
    """情绪持久化状态"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = Database()
        self._init_table()
        self._ensure_state()

    def _init_table(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS emotion_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL UNIQUE,
                    mood_value REAL DEFAULT 0.0,
                    dominant_emotion TEXT DEFAULT '平静',
                    streak_count INTEGER DEFAULT 0,
                    last_emotion TEXT DEFAULT '平静',
                    updated_at TEXT NOT NULL
                )
            """)

    def _ensure_state(self):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            existing = conn.execute(
                "SELECT user_id FROM emotion_state WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()
            if not existing:
                conn.execute(
                    "INSERT INTO emotion_state (user_id, mood_value, dominant_emotion, updated_at) "
                    "VALUES (?, 0.0, '平静', ?)",
                    (self.user_id, now),
                )

    def get_state(self):
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT mood_value, dominant_emotion, streak_count, last_emotion, updated_at "
                "FROM emotion_state WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()
        return dict(row) if row else {
            "mood_value": 0.0, "dominant_emotion": "平静",
            "streak_count": 0, "last_emotion": "平静",
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    def update_state(self, emotion: str, intensity: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        state = self.get_state()
        current_mood = state["mood_value"]
        last_emotion = state["last_emotion"]
        streak = state["streak_count"]

        impact = USER_IMPACT.get(emotion, 0.0)
        multiplier = INTENSITY_MULTIPLIER.get(intensity, 1.0)
        delta = impact * multiplier

        if emotion == last_emotion:
            streak = min(streak + 1, 5)
            delta *= (1 + streak * 0.15)
        else:
            streak = 0

        new_mood = max(-1.0, min(1.0, current_mood + delta))

        try:
            last_time = datetime.strptime(state["updated_at"], "%Y-%m-%d %H:%M:%S")
            hours_passed = (datetime.now() - last_time).total_seconds() / 3600
            if hours_passed > 1:
                decay = min(hours_passed * 0.03, abs(new_mood))
                new_mood = new_mood - decay if new_mood > 0 else new_mood + decay
        except:
            pass

        new_mood = round(new_mood, 3)

        if abs(new_mood) < 0.1:
            dominant = "平静"
        elif new_mood > 0.5:
            dominant = "开心"
        elif new_mood > 0.2:
            dominant = "还不错"
        elif new_mood < -0.5:
            dominant = "低落"
        elif new_mood < -0.2:
            dominant = "不太开心"
        else:
            dominant = "平静"

        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE emotion_state SET mood_value = ?, dominant_emotion = ?, "
                "streak_count = ?, last_emotion = ?, updated_at = ? WHERE user_id = ?",
                (new_mood, dominant, streak, emotion, now, self.user_id),
            )

    def get_mood_hint(self) -> str:
        state = self.get_state()
        mood = state["mood_value"]
        dominant = state["dominant_emotion"]
        try:
            last_time = datetime.strptime(state["updated_at"], "%Y-%m-%d %H:%M:%S")
            hours_passed = (datetime.now() - last_time).total_seconds() / 3600
            if hours_passed > 12:
                return ""
        except:
            return ""
        if abs(mood) < 0.1:
            return ""
        if mood > 0.5:
            return f"用户最近心情很好（{dominant}），语气可以活泼、轻快一些"
        elif mood > 0.2:
            return f"用户心情还不错（{dominant}），保持轻松的氛围"
        elif mood < -0.5:
            return f"用户最近情绪比较低落（{dominant}），说话温柔一些，多关心用户"
        elif mood < -0.2:
            return f"用户情绪有点低（{dominant}），语气稍微柔和一点"
        return ""


class EmotionAnalyzer:
    """情绪分析器 v2 - 含意图识别和三阶段响应"""

    EMOTION_PRIORITY = {
        "生气": 5, "难过": 5, "焦虑": 4, "疲惫": 3, "感动": 3,
        "嘲讽": 2, "撒娇": 2, "开心": 2, "惊讶": 2,
        "好奇": 1, "无聊": 1, "敷衍": 1, "平静": 0,
    }

    INTENSITY_VALUE = {"轻度": 1, "中度": 2, "强烈": 3}

    def __init__(self):
        self._states: dict[str, EmotionState] = {}

    def get_state(self, user_id: str) -> EmotionState:
        if user_id not in self._states:
            self._states[user_id] = EmotionState(user_id)
        return self._states[user_id]

    # ========== 第一阶段：意图识别 ==========
    def detect_intent(self, text: str) -> str:
        """识别用户意图"""
        if not text:
            return "闲聊"

        scores = {}
        for intent, data in INTENT_PATTERNS.items():
            score = sum(1 for kw in data["keywords"] if kw in text)
            if score > 0:
                scores[intent] = score + data["priority"]

        if scores:
            return max(scores, key=scores.get)
        return "闲聊"

    # ========== 第二阶段：情绪分析 ==========
    def analyze(self, text: str) -> EmotionResult:
        if not text:
            return EmotionResult(primary="平静", intensity="轻度", source="text",
                                 sentiment="中性", intent="闲聊")

        scores: dict[str, int] = {}
        matched_tags: list[str] = []

        for emotion, data in EMOTION_KEYWORDS.items():
            score = 0
            for kw in data["keywords"]:
                if kw in text:
                    score += 1
            for emoji in data["emoji"]:
                if emoji in text:
                    score += 1
            if score > 0:
                scores[emotion] = score
                matched_tags.append(emotion)

        intensity = "中度"
        for word in INTENSITY_BOOSTERS:
            if word in text:
                intensity = "强烈"
                break
        for word in INTENSITY_LOWERS:
            if word in text:
                intensity = "轻度"
                break

        exclaim_count = text.count("!") + text.count("！")
        if exclaim_count >= 3:
            intensity = "强烈"
        if text == text.upper() and len(text) > 2:
            intensity = "强烈"
        if re.search(r'(.)\1{2,}', text):
            intensity = "强烈"

        if len(text) <= 2 and not scores:
            intent = self.detect_intent(text)
            return EmotionResult(
                primary="敷衍", intensity="轻度", tags=["敷衍"],
                context_hint="用户回复很简短，可能不太想聊，不要追问，简短回应就好",
                source="text", sentiment="中性", intent=intent,
            )

        if scores:
            primary = max(scores, key=scores.get)
        else:
            primary = "平静"

        sentiment = SENTIMENT_MAP.get(primary, "中性")
        intent = self.detect_intent(text)
        hint = self._generate_hint(primary, intensity, intent)

        return EmotionResult(
            primary=primary, intensity=intensity,
            tags=matched_tags, context_hint=hint, source="text",
            sentiment=sentiment, intent=intent,
        )

    async def analyze_with_llm(self, text: str, llm_client=None) -> EmotionResult:
        if not text or not llm_client:
            return self.analyze(text)

        prompt = (
            "分析以下用户消息的情绪和意图。输出JSON格式：\n"
            '{"emotion": "情绪标签", "intensity": "强度", "intent": "意图", "reason": "简短理由"}\n'
            "\n"
            "可选情绪标签：开心、难过、生气、焦虑、疲惫、敷衍、撒娇、好奇、无聊、感动、嘲讽、惊讶、平静\n"
            "可选强度：轻度、中度、强烈\n"
            "可选意图：求助、倾诉、分享、提问、抱怨、安慰需求、闲聊、表白\n"
            "\n"
            "注意：\n"
            "- 如果用户在反讽/正话反说，根据真实情绪判断\n"
            "- 如果只有一两个字（如'嗯'、'哦'），判断为敷衍\n"
            "- 如果包含多个情绪，选最强烈的那个\n"
            "- 网络用语如'破防了'='难过'，'yyds'='开心'，'下头'='生气'\n"
            "\n"
            f"用户消息：{text}\n"
            "\n"
            "只输出JSON，不要其他内容。"
        )

        try:
            result = await llm_client.generate_json(prompt, use_light=True)
            if result and "emotion" in result:
                emotion = result["emotion"]
                intensity = result.get("intensity", "中度")
                intent = result.get("intent", "闲聊")
                reason = result.get("reason", "")

                valid_emotions = set(EMOTION_KEYWORDS.keys()) | {"平静"}
                if emotion not in valid_emotions:
                    emotion = "平静"
                if intensity not in ("轻度", "中度", "强烈"):
                    intensity = "中度"

                sentiment = SENTIMENT_MAP.get(emotion, "中性")
                hint = self._generate_hint(emotion, intensity, intent)
                if reason:
                    hint = f"（{reason}）{hint}" if hint else f"（{reason}）"

                return EmotionResult(
                    primary=emotion, intensity=intensity,
                    tags=[emotion], context_hint=hint, source="llm",
                    sentiment=sentiment, intent=intent,
                )
        except Exception:
            pass

        return self.analyze(text)

    # ========== 第三阶段：响应策略 ==========
    def get_response_strategy(self, emotion: EmotionResult) -> dict:
        """根据情绪和意图生成响应策略"""
        strategy = {
            "priority": "normal",
            "tone": "default",
            "approach": "standard",
            "soothing": False,
        }

        # 负向情绪优先触发安抚
        if emotion.sentiment == "负向":
            strategy["priority"] = "high"
            strategy["soothing"] = True

            if emotion.primary in ("难过", "生气"):
                strategy["tone"] = "gentle"
                strategy["approach"] = "comfort_first"
            elif emotion.primary == "焦虑":
                strategy["tone"] = "calm"
                strategy["approach"] = "rational_help"
            elif emotion.primary == "疲惫":
                strategy["tone"] = "soft"
                strategy["approach"] = "minimal"
            elif emotion.primary == "嘲讽":
                strategy["tone"] = "neutral"
                strategy["approach"] = "defuse"

        # 安慰需求最高优先级
        if emotion.intent == "安慰需求":
            strategy["priority"] = "critical"
            strategy["soothing"] = True
            strategy["approach"] = "deep_comfort"

        # 求助优先给方案
        if emotion.intent == "求助":
            strategy["priority"] = "high"
            strategy["approach"] = "solution_first"

        return strategy

    def analyze_and_update(self, user_id: str, text: str) -> EmotionResult:
        result = self.analyze(text)
        state = self.get_state(user_id)
        state.update_state(result.primary, result.intensity)
        return result

    async def analyze_and_update_with_llm(self, user_id: str, text: str, llm_client=None) -> EmotionResult:
        result = await self.analyze_with_llm(text, llm_client)
        state = self.get_state(user_id)
        state.update_state(result.primary, result.intensity)
        return result

    def get_mood_hint(self, user_id: str) -> str:
        state = self.get_state(user_id)
        return state.get_mood_hint()

    def merge_emotions(self, text_emotion: EmotionResult, sticker_emotion: str, sticker_intensity: str) -> EmotionResult:
        if text_emotion.primary == sticker_emotion:
            merged_intensity = self._max_intensity(text_emotion.intensity, sticker_intensity)
            return EmotionResult(
                primary=sticker_emotion, intensity=merged_intensity,
                tags=list(set(text_emotion.tags + [sticker_emotion])),
                context_hint=self._generate_hint(sticker_emotion, merged_intensity),
                source="merged", sentiment=text_emotion.sentiment, intent=text_emotion.intent,
            )

        text_priority = self.EMOTION_PRIORITY.get(text_emotion.primary, 0)
        sticker_priority = self.EMOTION_PRIORITY.get(sticker_emotion, 0)

        if sticker_priority >= text_priority:
            chosen = sticker_emotion
            chosen_intensity = sticker_intensity
        else:
            chosen = text_emotion.primary
            chosen_intensity = text_emotion.intensity

        sentiment = SENTIMENT_MAP.get(chosen, "中性")
        hint = self._generate_hint(chosen, chosen_intensity)
        if text_priority >= 3 and sticker_priority >= 3 and text_emotion.primary != sticker_emotion:
            hint += (
                f"\n注意：用户的文字情绪偏向{text_emotion.primary}，"
                f"但发表的表情包偏向{sticker_emotion}，"
                f"可能在用表情包表达文字没有说出来的感受。"
            )

        return EmotionResult(
            primary=chosen, intensity=chosen_intensity,
            tags=list(set(text_emotion.tags + [sticker_emotion])),
            context_hint=hint, source="merged",
            sentiment=sentiment, intent=text_emotion.intent,
        )

    def _max_intensity(self, a: str, b: str) -> str:
        a_val = self.INTENSITY_VALUE.get(a, 2)
        b_val = self.INTENSITY_VALUE.get(b, 2)
        max_val = max(a_val, b_val)
        for name, val in self.INTENSITY_VALUE.items():
            if val == max_val:
                return name
        return "中度"

    def _generate_hint(self, primary: str, intensity: str, intent: str = "") -> str:
        # 基础情绪提示
        hints = {
            "开心": {
                "轻度": "用户心情不错，可以轻松地聊",
                "中度": "用户挺开心的，配合他的情绪，一起开心",
                "强烈": "用户非常开心，跟着一起兴奋",
            },
            "难过": {
                "轻度": "用户有点低落，温柔一点，不要追问太多",
                "中度": "用户心情不好，认真安慰，不要敷衍",
                "强烈": "用户很难过，放下一切，认真陪伴和安慰",
            },
            "生气": {
                "轻度": "用户有点不爽，不要火上浇油，先认同他的感受",
                "中度": "用户在生气，先让他发泄，不要反驳",
                "强烈": "用户非常生气，先安抚情绪，等他冷静了再聊",
            },
            "焦虑": {
                "轻度": "用户有点焦虑，给一些轻松的回应",
                "中度": "用户比较焦虑，帮他理清思路，给实际建议",
                "强烈": "用户非常焦虑，先让他冷静下来，再帮他分析",
            },
            "疲惫": {
                "轻度": "用户有点累，让他休息，不要给他压力",
                "中度": "用户很累，简短回复，不要长篇大论",
                "强烈": "用户精疲力尽，少说话，让他去休息",
            },
            "敷衍": {
                "轻度": "用户回复简短，不要追问，简短回应",
                "中度": "用户可能不太想聊，给一个轻松的回应就好",
                "强烈": "用户明显不想聊，不要主动找话题",
            },
            "撒娇": {
                "轻度": "用户在撒娇，温柔一点回应",
                "中度": "用户在撒娇，配合一下，但不要太夸张",
                "强烈": "用户在使劲撒娇，可以适当调侃回去",
            },
            "好奇": {
                "轻度": "用户有点好奇，简单回答",
                "中度": "用户很好奇，详细一点回答",
                "强烈": "用户非常好奇，认真详细地解答",
            },
            "无聊": {
                "轻度": "用户有点无聊，可以主动找话题",
                "中度": "用户很无聊，推荐一些事情给他做",
                "强烈": "用户非常无聊，想办法逗他开心",
            },
            "感动": {
                "轻度": "用户有点感动，温柔回应",
                "中度": "用户被感动了，真诚地回应",
                "强烈": "用户非常感动，认真对待，不要敷衍",
            },
            "嘲讽": {
                "轻度": "用户在讽刺，不要当真，轻松化解",
                "中度": "用户在嘲讽，不要被激怒，保持冷静",
                "强烈": "用户在激烈嘲讽，不要对抗，先认同再引导",
            },
            "惊讶": {
                "轻度": "用户有点惊讶，简单解释",
                "中度": "用户很惊讶，详细解释",
                "强烈": "用户非常震惊，先安抚再解释",
            },
            "平静": {"轻度": "", "中度": "", "强烈": ""},
        }
        base_hint = hints.get(primary, {}).get(intensity, "")

        # 意图叠加提示
        intent_hints = {
            "求助": "用户需要帮助，优先给实际建议",
            "倾诉": "用户想倾诉，认真听，不要急着给建议",
            "分享": "用户在分享，积极回应，表达兴趣",
            "抱怨": "用户在抱怨，先认同感受，再引导",
            "安慰需求": "用户需要安慰，优先安抚情绪，再考虑解决方案",
            "表白": "用户在表达好感，真诚回应",
        }
        intent_hint = intent_hints.get(intent, "")

        if base_hint and intent_hint:
            return f"{base_hint}。{intent_hint}"
        return base_hint or intent_hint
