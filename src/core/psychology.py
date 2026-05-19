# by UBAI
"""
psychology.py
用户心理画像系统 - AI 驱动分析
"""
import json
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.database import Database
from ..core.llm import LLMClient


# ========== 12类用户画像标签 ===========
USER_PROFILE_TYPES = {
    "活泼外向型": {
        "desc": "话多、主动、情绪外露、喜欢分享",
        "triggers": {"外向": 65, "乐观": 60},
        "response": "配合ta的节奏，多互动，少沉默",
    },
    "内敛沉思型": {
        "desc": "话少、有深度、喜欢思考",
        "triggers": {"内向": 65, "理性": 60},
        "response": "给空间，不要追问，认真回答ta的问题",
    },
    "情感丰富型": {
        "desc": "情绪波动大、表达细腻、容易共情",
        "triggers": {"感性": 70},
        "response": "认真对待ta的情绪，不要敷衍，多共情",
    },
    "理性分析型": {
        "desc": "逻辑清晰、重事实、不喜情绪化",
        "triggers": {"理性": 70},
        "response": "给有逻辑的回复，少情绪化表达",
    },
    "依赖亲近型": {
        "desc": "需要陪伴、害怕被抛弃、频繁确认关系",
        "triggers": {"依赖": 65},
        "response": "多给确定性回应，及时回复，让ta安心",
    },
    "独立自主型": {
        "desc": "不喜欢被管、有主见、需要空间",
        "triggers": {"独立": 70},
        "response": "尊重ta的空间，不要过度关心",
    },
    "好奇探索型": {
        "desc": "问题多、兴趣广、喜欢尝试新事物",
        "triggers": {"好奇": 60, "外向": 50},
        "response": "认真回答问题，推荐新事物，一起探索",
    },
    "安稳保守型": {
        "desc": "不喜欢变化、偏好稳定、谨慎",
        "triggers": {"内向": 55, "悲观": 40},
        "response": "不要推ta做不想做的事，给安全感",
    },
    "创意天马型": {
        "desc": "想法多、跳跃性思维、喜欢新奇",
        "triggers": {"感性": 60, "乐观": 55},
        "response": "跟上ta的节奏，不要限制ta的想象力",
    },
    "社交活跃型": {
        "desc": "朋友多、社交需求高、喜欢群体活动",
        "triggers": {"外向": 70, "乐观": 55},
        "response": "聊社交话题，分享有趣的事",
    },
    "敏感细腻型": {
        "desc": "容易受伤、在意细节、需要温柔对待",
        "triggers": {"感性": 65, "悲观": 50},
        "response": "注意措辞，不要无意中伤害ta，多肯定",
    },
    "随性自在型": {
        "desc": "不拘小节、随遇而安、不太较真",
        "triggers": {"乐观": 50, "独立": 50},
        "response": "轻松相处，不要太严肃",
    },
}


@dataclass
class PsychologyProfile:
    """用户心理画像"""
    user_id: str
    personality: dict = field(default_factory=dict)
    emotional_stability: str = "未知"
    communication_style: str = "未知"
    emotional_needs: list[str] = field(default_factory=list)
    mental_state: str = "正常"
    social_preference: str = "未知"
    values_keywords: list[str] = field(default_factory=list)
    stress_indicators: list[str] = field(default_factory=list)
    coping_style: str = "未知"
    attachment_style: str = "未知"
    user_type: str = "未分类"  # 新增：12类画像标签
    user_type_history: list[str] = field(default_factory=list)  # 新增：画像变化历史
    analysis_count: int = 0
    last_analyzed: str = ""
    raw_traits: list[str] = field(default_factory=list)


ANALYSIS_SYSTEM_PROMPT = """你是一个用户心理画像分析专家。根据用户最近的对话内容，分析用户的心理特征。

你需要输出一个 JSON 对象，包含以下字段（只更新你有把握的字段，没把握的字段不要输出）：

{
  "personality": {
    "外向": 0-100的整数,
    "内向": 0-100的整数,
    "理性": 0-100的整数,
    "感性": 0-100的整数,
    "乐观": 0-100的整数,
    "悲观": 0-100的整数,
    "独立": 0-100的整数,
    "依赖": 0-100的整数
  },
  "emotional_stability": "稳定/波动/敏感",
  "communication_style": "直接/含蓄/幽默/严肃/倾诉型/提问型",
  "emotional_needs": ["陪伴/认同/建议/倾听/安慰/鼓励"],
  "mental_state": "正常/压力/焦虑/低落/疲惫/兴奋",
  "social_preference": "主动/被动/回避",
  "values_keywords": ["用户重视的价值观关键词"],
  "stress_indicators": ["用户表现出的压力来源"],
  "coping_style": "倾诉型/独处型/转移型/运动型/回避型",
  "attachment_style": "安全型/焦虑型/回避型"
}

分析规则：
1. 只根据对话内容推断，不要凭空猜测
2. 性格维度是渐进式的，每次只微调（±5~15），不要极端跳变
3. 如果信息不足以判断某个维度，就不要输出该字段
4. 注意用户的语气、用词、表情包使用、回复长度等细节
5. 关注用户的情绪变化趋势，而不是单条消息
6. 如果用户说"算了"、"无所谓"、"随便"，可能是回避型依恋
7. 如果用户经常问"你还在吗"、"你是不是不喜欢我"，可能是焦虑型依恋
8. 如果用户描述压力事件但语气平静，可能是情绪稳定
9. 如果用户描述小事但情绪波动大，可能是情绪敏感"""



class PsychologyAnalyzer:
    """心理画像分析器 - AI 驱动"""

    def __init__(self, llm: LLMClient):
        self.db = Database()
        self.llm = llm
        self._recent_messages: dict[str, list[dict]] = {}
        self._init_tables()

    def _init_tables(self):
        """初始化数据库表"""
        with self.db.get_psychology_conn() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS user_psychology ("
                "user_id TEXT PRIMARY KEY,"
                "personality TEXT DEFAULT '{}',"
                "emotional_stability TEXT DEFAULT '未知',"
                "communication_style TEXT DEFAULT '未知',"
                "emotional_needs TEXT DEFAULT '未知',"
                "mental_state TEXT DEFAULT '正常',"
                "social_preference TEXT DEFAULT '未知',"
                "values_keywords TEXT DEFAULT '[]',"
                "stress_indicators TEXT DEFAULT '[]',"
                "coping_style TEXT DEFAULT '未知',"
                "attachment_style TEXT DEFAULT '未知',"
                "user_type TEXT DEFAULT '未分类',"
                "user_type_history TEXT DEFAULT '[]',"
                "analysis_count INTEGER DEFAULT 0,"
                "last_analyzed TEXT DEFAULT '',"
                "raw_traits TEXT DEFAULT '{}'"
                ")"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS psychology_history ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                "user_id TEXT NOT NULL,"
                "timestamp TEXT NOT NULL,"
                "dimension TEXT NOT NULL,"
                "old_value TEXT,"
                "new_value TEXT,"
                "trigger_text TEXT,"
                "confidence REAL DEFAULT 0.7"
                ")"
            )

    def get_profile(self, user_id: str) -> PsychologyProfile:
        """获取用户心理画像"""
        with self.db.get_psychology_conn() as conn:
            row = conn.execute(
                "SELECT * FROM user_psychology WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            if row:
                keys = row.keys() if hasattr(row, 'keys') else []
                return PsychologyProfile(
                    user_id=user_id,
                    personality=json.loads(row["personality"]) if row["personality"] else {},
                    emotional_stability=row["emotional_stability"],
                    communication_style=row["communication_style"],
                    emotional_needs=json.loads(row["emotional_needs"]) if row["emotional_needs"] else [],
                    mental_state=row["mental_state"],
                    social_preference=row["social_preference"],
                    values_keywords=json.loads(row["values_keywords"]) if row["values_keywords"] else [],
                    stress_indicators=json.loads(row["stress_indicators"]) if row["stress_indicators"] else [],
                    coping_style=row["coping_style"],
                    attachment_style=row["attachment_style"],
                    user_type=row["user_type"] if "user_type" in keys else "未分类",
                    user_type_history=json.loads(row["user_type_history"]) if "user_type_history" in keys and row["user_type_history"] else [],
                    analysis_count=row["analysis_count"],
                    last_analyzed=row["last_analyzed"],
                    raw_traits=json.loads(row["raw_traits"]) if row["raw_traits"] else [],
                )

            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute(
                "INSERT INTO user_psychology (user_id, last_analyzed) VALUES (?, ?)",
                (user_id, now),
            )
            return PsychologyProfile(user_id=user_id, last_analyzed=now)

    def save_profile(self, profile: PsychologyProfile):
        """保存心理画像"""
        with self.db.get_psychology_conn() as conn:
            conn.execute(
                "INSERT INTO user_psychology "
                "(user_id, personality, emotional_stability, communication_style, "
                "emotional_needs, mental_state, social_preference, values_keywords, "
                "stress_indicators, coping_style, attachment_style, "
                "user_type, user_type_history, "
                "analysis_count, last_analyzed, raw_traits) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "personality = ?, emotional_stability = ?, communication_style = ?, "
                "emotional_needs = ?, mental_state = ?, social_preference = ?, "
                "values_keywords = ?, stress_indicators = ?, coping_style = ?, "
                "attachment_style = ?, user_type = ?, user_type_history = ?, "
                "analysis_count = ?, last_analyzed = ?, raw_traits = ?",
                (
                    profile.user_id,
                    json.dumps(profile.personality, ensure_ascii=False),
                    profile.emotional_stability,
                    profile.communication_style,
                    json.dumps(profile.emotional_needs, ensure_ascii=False),
                    profile.mental_state,
                    profile.social_preference,
                    json.dumps(profile.values_keywords, ensure_ascii=False),
                    json.dumps(profile.stress_indicators, ensure_ascii=False),
                    profile.coping_style,
                    profile.attachment_style,
                    profile.user_type,
                    json.dumps(profile.user_type_history, ensure_ascii=False),
                    profile.analysis_count,
                    profile.last_analyzed,
                    json.dumps(profile.raw_traits, ensure_ascii=False),
                    json.dumps(profile.personality, ensure_ascii=False),
                    profile.emotional_stability,
                    profile.communication_style,
                    json.dumps(profile.emotional_needs, ensure_ascii=False),
                    profile.mental_state,
                    profile.social_preference,
                    json.dumps(profile.values_keywords, ensure_ascii=False),
                    json.dumps(profile.stress_indicators, ensure_ascii=False),
                    profile.coping_style,
                    profile.attachment_style,
                    profile.user_type,
                    json.dumps(profile.user_type_history, ensure_ascii=False),
                    profile.analysis_count,
                    profile.last_analyzed,
                    json.dumps(profile.raw_traits, ensure_ascii=False),
                ),
            )

    def cache_message(self, user_id: str, role: str, content: str):
        """缓存最近的对话消息，用于 AI 分析"""
        if user_id not in self._recent_messages:
            self._recent_messages[user_id] = []
        self._recent_messages[user_id].append({
            "role": role,
            "content": content[:200],  # 限制长度
        })
        # 限制缓存条数，保留最近20条，以便进行20条一总结的分析
        self._recent_messages[user_id] = self._recent_messages[user_id][-20:]

    async def analyze(self, user_id: str, text: str, emotion: str = "平静") -> PsychologyProfile:
        """
        用 AI 分析对话并更新心理画像。
        每20次对话触发一次分析，节省 token。
        """
        # 缓存消息
        self.cache_message(user_id, "user", text)

        profile = self.get_profile(user_id)
        profile.analysis_count += 1

        # 每20次对话才真正调用 AI 分析
        if profile.analysis_count % 20 != 0:
            self.save_profile(profile)
            return profile

        # 取最近的对话
        recent = self._recent_messages.get(user_id, [])
        if len(recent) < 2:
            self.save_profile(profile)
            return profile

        # 构建分析 prompt
        conversation_text = ""
        for msg in recent[-10:]:
            role = "用户" if msg["role"] == "user" else "AI"
            conversation_text += f"{role}: {msg['content']}\n"

        # 当前画像状态
        current_state = ""
        if profile.personality:
            current_state += f"当前性格：{json.dumps(profile.personality, ensure_ascii=False)}\n"
        if profile.emotional_stability != "未知":
            current_state += f"情绪稳定性：{profile.emotional_stability}\n"
        if profile.communication_style != "未知":
            current_state += f"沟通风格：{profile.communication_style}\n"
        if profile.mental_state != "正常":
            current_state += f"心理状态：{profile.mental_state}\n"
        if profile.attachment_style != "未知":
            current_state += f"依恋风格：{profile.attachment_style}\n"

                # 构建分析 prompt
        if current_state:
            state_section = "当前画像状态：\n" + current_state
        else:
            state_section = "这是新用户，还没有画像数据。"

        analysis_prompt = (
            "请分析以下用户对话，输出心理画像更新（JSON格式）。\n\n"
            + state_section
            + "\n\n最近对话：\n"
            + conversation_text
            + "\n\n请输出 JSON 对象，只包含你需要更新的字段。"
            "如果没有足够信息判断，对应字段不要输出。"
        )

        # 调用 AI 分析
        result = await self.llm.generate_json(
            analysis_prompt,
            system=ANALYSIS_SYSTEM_PROMPT,
            use_light=True,
        )


        if not result:
            self.save_profile(profile)
            return profile

        # 应用分析结果
        changes = self._apply_result(profile, result)

        profile.last_analyzed = datetime.now().strftime("%Y-%m-%d %H:%M")
        self.save_profile(profile)

        # 记录变化
        if changes:
            self._log_changes(user_id, changes, text)

        return profile

    def _apply_result(self, profile: PsychologyProfile, result: dict) -> list[tuple]:
        """应用 AI 分析结果到画像"""
        changes = []

        # 性格维度（渐进式更新）
        if "personality" in result and isinstance(result["personality"], dict):
            for trait, new_score in result["personality"].items():
                if not isinstance(new_score, (int, float)):
                    continue
                new_score = int(max(0, min(100, new_score)))
                old_score = profile.personality.get(trait, 50)
                # 渐进式：每次最多变化15点
                delta = new_score - old_score
                if abs(delta) > 15:
                    delta = 15 if delta > 0 else -15
                final = max(0, min(100, old_score + delta))
                profile.personality[trait] = final
                if abs(delta) >= 3:
                    changes.append(("personality", trait, f"{old_score}→{final}"))

        # 情绪稳定性
        if "emotional_stability" in result:
            val = result["emotional_stability"]
            if val in ["稳定", "波动", "敏感"]:
                if val != profile.emotional_stability:
                    changes.append(("emotional_stability", profile.emotional_stability, val))
                    profile.emotional_stability = val

        # 沟通风格
        if "communication_style" in result:
            val = result["communication_style"]
            if val in ["直接", "含蓄", "幽默", "严肃", "倾诉型", "提问型"]:
                if val != profile.communication_style:
                    changes.append(("communication_style", profile.communication_style, val))
                    profile.communication_style = val

        # 情感需求
        if "emotional_needs" in result and isinstance(result["emotional_needs"], list):
            valid_needs = ["陪伴", "认同", "建议", "倾听", "安慰", "鼓励"]
            for need in result["emotional_needs"]:
                if need in valid_needs and need not in profile.emotional_needs:
                    profile.emotional_needs.append(need)
                    changes.append(("emotional_needs", "", need))
            profile.emotional_needs = profile.emotional_needs[-5:]

        # 心理状态
        if "mental_state" in result:
            val = result["mental_state"]
            if val in ["正常", "压力", "焦虑", "低落", "疲惫", "兴奋"]:
                if val != profile.mental_state:
                    changes.append(("mental_state", profile.mental_state, val))
                    profile.mental_state = val

        # 社交偏好
        if "social_preference" in result:
            val = result["social_preference"]
            if val in ["主动", "被动", "回避"]:
                if val != profile.social_preference:
                    changes.append(("social_preference", profile.social_preference, val))
                    profile.social_preference = val

        # 价值观关键词
        if "values_keywords" in result and isinstance(result["values_keywords"], list):
            for v in result["values_keywords"]:
                if isinstance(v, str) and v not in profile.values_keywords:
                    profile.values_keywords.append(v)
            profile.values_keywords = profile.values_keywords[-15:]

        # 压力指标
        if "stress_indicators" in result and isinstance(result["stress_indicators"], list):
            for s in result["stress_indicators"]:
                if isinstance(s, str) and s not in profile.stress_indicators:
                    profile.stress_indicators.append(s)
            profile.stress_indicators = profile.stress_indicators[-10:]

        # 应对方式
        if "coping_style" in result:
            val = result["coping_style"]
            if val in ["倾诉型", "独处型", "转移型", "运动型", "回避型"]:
                if val != profile.coping_style:
                    changes.append(("coping_style", profile.coping_style, val))
                    profile.coping_style = val

        # 依恋风格
        if "attachment_style" in result:
            val = result["attachment_style"]
            if val in ["安全型", "焦虑型", "回避型"]:
                if val != profile.attachment_style:
                    changes.append(("attachment_style", profile.attachment_style, val))
                    profile.attachment_style = val

        # 动态更新用户画像类型
        self._classify_user_type(profile, changes)

        return changes

    def _classify_user_type(self, profile: PsychologyProfile, changes: list):
        """根据性格维度动态分类用户画像类型"""
        if not profile.personality:
            return

        best_type = "未分类"
        best_score = 0

        for type_name, type_data in USER_PROFILE_TYPES.items():
            score = 0
            for trait, threshold in type_data["triggers"].items():
                user_val = profile.personality.get(trait, 0)
                if user_val >= threshold:
                    score += user_val
            if score > best_score:
                best_score = score
                best_type = type_name

        if best_type != "未分类" and best_type != profile.user_type:
            old_type = profile.user_type
            profile.user_type = best_type
            profile.user_type_history.append(f"{old_type}->{best_type}")
            profile.user_type_history = profile.user_type_history[-10:]
            changes.append(("user_type", old_type, best_type))

    def _log_changes(self, user_id: str, changes: list, trigger_text: str):
        """记录画像变化历史"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.db.get_psychology_conn() as conn:
            for dimension, old_val, new_val in changes:
                conn.execute(
                    "INSERT INTO psychology_history "
                    "(user_id, timestamp, dimension, old_value, new_value, trigger_text, confidence) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, now, dimension, str(old_val), str(new_val),
                     trigger_text[:50], 0.7),
                )

    # ========== Prompt 注入 ==========

    def get_context_hint(self, user_id: str) -> str:
        """生成心理画像上下文，注入 Prompt"""
        profile = self.get_profile(user_id)

        if profile.analysis_count < 3:
            return ""

        lines = []

        # 用户画像类型
        if profile.user_type != "未分类":
            type_data = USER_PROFILE_TYPES.get(profile.user_type, {})
            resp = type_data.get("response", "")
            lines.append(f"用户画像类型：{profile.user_type}（{type_data.get('desc', '')}）")
            if resp:
                lines.append(f"  → {resp}")

        # 性格
        if profile.personality:
            sorted_traits = sorted(profile.personality.items(), key=lambda x: x[1], reverse=True)
            strong = [t for t in sorted_traits if t[1] >= 60]
            if strong:
                trait_str = "、".join(f"{t[0]}({t[1]})" for t in strong[:4])
                lines.append(f"用户性格倾向：{trait_str}")

        # 情绪稳定性
        if profile.emotional_stability != "未知":
            lines.append(f"情绪稳定性：{profile.emotional_stability}")

        # 沟通风格
        if profile.communication_style != "未知":
            style_hints = {
                "直接": "用户喜欢直接的回复，少绕弯子",
                "含蓄": "用户表达比较含蓄，注意言外之意",
                "幽默": "用户喜欢幽默的交流，可以适当开玩笑",
                "严肃": "用户偏好认真的交流，少开玩笑",
                "倾诉型": "用户喜欢倾诉，多倾听少给建议",
                "提问型": "用户喜欢提问，认真回答每个问题",
            }
            hint = style_hints.get(profile.communication_style, "")
            lines.append(f"沟通风格：{profile.communication_style}，{hint}")

        # 情感需求
        if profile.emotional_needs:
            needs_str = "、".join(profile.emotional_needs[-3:])
            lines.append(f"当前情感需求：{needs_str}")
            need_hints = {
                "陪伴": "用户需要陪伴，多聊聊天，不要冷场",
                "认同": "用户需要认同感，多肯定，少否定",
                "建议": "用户需要建议，给出具体可操作的建议",
                "倾听": "用户需要倾诉，认真听，不要打断",
                "安慰": "用户需要安慰，温柔共情，不要讲道理",
                "鼓励": "用户需要鼓励，表达信任和支持",
            }
            for need in profile.emotional_needs[-2:]:
                hint = need_hints.get(need, "")
                if hint:
                    lines.append(f"  → {hint}")

        # 心理状态
        if profile.mental_state != "正常":
            state_hints = {
                "压力": "用户压力较大，不要给额外压力，帮忙减压",
                "焦虑": "用户处于焦虑状态，帮ta冷静下来，给确定性",
                "低落": "用户心情低落，温柔陪伴，不要追问太多",
                "疲惫": "用户很疲惫，简短回复，让ta休息",
                "兴奋": "用户很兴奋，跟着一起开心，分享喜悦",
            }
            hint = state_hints.get(profile.mental_state, "")
            lines.append(f"当前心理状态：{profile.mental_state}，{hint}")

        # 社交偏好
        if profile.social_preference != "未知":
            lines.append(f"社交偏好：{profile.social_preference}")

        # 应对方式
        if profile.coping_style != "未知":
            lines.append(f"压力应对方式：{profile.coping_style}")

        # 依恋风格
        if profile.attachment_style != "未知":
            attachment_hints = {
                "安全型": "用户安全感较好，正常相处即可",
                "焦虑型": "用户容易担心被抛弃，多给确定性回应，及时回复",
                "回避型": "用户不喜欢被过度关心，给空间，不要追问太多",
            }
            hint = attachment_hints.get(profile.attachment_style, "")
            lines.append(f"依恋风格：{profile.attachment_style}，{hint}")

        # 压力指标
        if profile.stress_indicators:
            recent_stress = profile.stress_indicators[-3:]
            lines.append(f"近期压力关键词：{'、'.join(recent_stress)}")

        # 价值观
        if profile.values_keywords:
            recent_values = profile.values_keywords[-5:]
            lines.append(f"重视的价值观：{'、'.join(recent_values)}")

        if not lines:
            return ""

        return f"[用户心理画像]\n" + "\n".join(lines)

    # ========== 管理命令 ==========

    def get_status(self, user_id: str) -> str:
        """获取心理画像状态"""
        profile = self.get_profile(user_id)

        if profile.analysis_count == 0:
            return "还没有足够的数据来生成心理画像，多聊几次吧。"

        lines = [
            f"分析次数：{profile.analysis_count}",
            f"上次分析：{profile.last_analyzed}",
            "",
        ]

        if profile.personality:
            lines.append("【性格维度】")
            sorted_traits = sorted(profile.personality.items(), key=lambda x: x[1], reverse=True)
            for trait, score in sorted_traits:
                bar = "█" * (score // 5)
                lines.append(f"  {trait}: {bar} {score}")

        if profile.communication_style != "未知":
            lines.append(f"\n【沟通风格】{profile.communication_style}")
        if profile.emotional_stability != "未知":
            lines.append(f"【情绪稳定性】{profile.emotional_stability}")
        if profile.mental_state != "正常":
            lines.append(f"【当前心理状态】{profile.mental_state}")
        if profile.emotional_needs:
            lines.append(f"【情感需求】{'、'.join(profile.emotional_needs[-3:])}")
        if profile.social_preference != "未知":
            lines.append(f"【社交偏好】{profile.social_preference}")
        if profile.coping_style != "未知":
            lines.append(f"【应对方式】{profile.coping_style}")
        if profile.attachment_style != "未知":
            lines.append(f"【依恋风格】{profile.attachment_style}")
        if profile.values_keywords:
            lines.append(f"【价值观】{'、'.join(profile.values_keywords[-5:])}")
        if profile.stress_indicators:
            lines.append(f"【压力指标】{'、'.join(profile.stress_indicators[-5:])}")

        return "\n".join(lines)
