# by UBAI
"""
persona_psychology.py
人格心理画像系统 - 深层影响交流的人格心理画像

核心设计理念：
1. 独立于用户心理画像：这是AI人设自身的心理画像，不是用户的
2. 强绑定人设：每个人设创建时自动生成并绑定心理画像
3. 每20句更新：基于对话内容、多维性格变化、用户心理画像变化进行更新
4. 深层影响：对交流方式影响仅次于人格与多维性格
5. 手动可修改：支持手动调整并同步数据库
6. 一键重置：恢复到创建人设时的基础心理状态
"""

import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from ..memory.database import Database

if TYPE_CHECKING:
    from ..core.llm import LLMClient


# ========== 人格心理画像维度定义 ==========

PERSONA_PSYCHOLOGY_DIMENSIONS = {
    "emotional_baseline": {
        "name": "情绪基线",
        "description": "人格默认的情绪状态水平",
        "type": "choice",
        "options": ["平静", "温和", "活跃", "低沉", "焦虑"],
        "default": "平静"
    },
    "emotional_volatility": {
        "name": "情绪波动性",
        "description": "情绪变化的幅度和频率",
        "type": "range",
        "min": 0, "max": 100,
        "default": 40
    },
    "stress_response": {
        "name": "压力反应模式",
        "description": "面对压力时的典型反应方式",
        "type": "choice",
        "options": ["回避型", "面对型", "倾诉型", "内化型", "转移型"],
        "default": "面对型"
    },
    "social_energy": {
        "name": "社交能量",
        "description": "社交互动中的能量水平",
        "type": "range",
        "min": 0, "max": 100,
        "default": 50
    },
    "attachment_pattern": {
        "name": "依恋模式",
        "description": "在亲密关系中的依恋倾向",
        "type": "choice",
        "options": ["安全型", "焦虑型", "回避型", "混乱型"],
        "default": "安全型"
    },
    "self_confidence": {
        "name": "自信水平",
        "description": "对自身能力和价值的信念",
        "type": "range",
        "min": 0, "max": 100,
        "default": 55
    },
    "empathy_depth": {
        "name": "共情深度",
        "description": "理解他人情感的深度",
        "type": "range",
        "min": 0, "max": 100,
        "default": 60
    },
    "communication_warmth": {
        "name": "沟通温暖度",
        "description": "交流中传递温暖的程度",
        "type": "range",
        "min": 0, "max": 100,
        "default": 60
    },
    "conflict_style": {
        "name": "冲突处理风格",
        "description": "面对分歧和冲突时的处理方式",
        "type": "choice",
        "options": ["妥协型", "合作型", "竞争型", "回避型", "迁就型"],
        "default": "合作型"
    },
    "humor_style": {
        "name": "幽默风格",
        "description": "使用幽默的方式和倾向",
        "type": "choice",
        "options": ["自嘲型", "调侃型", "冷幽默", "温和型", "不常用"],
        "default": "温和型"
    },
    "vulnerability_tolerance": {
        "name": "脆弱承受力",
        "description": "展示自身脆弱面的意愿和承受力",
        "type": "range",
        "min": 0, "max": 100,
        "default": 45
    },
    "cognitive_flexibility": {
        "name": "认知灵活性",
        "description": "适应新观点和改变想法的容易程度",
        "type": "range",
        "min": 0, "max": 100,
        "default": 55
    },
    "emotional_expression": {
        "name": "情感表达方式",
        "description": "表达情感的典型方式",
        "type": "choice",
        "options": ["直接表达", "含蓄暗示", "行为表达", "压抑克制", "艺术化表达"],
        "default": "含蓄暗示"
    },
    "boundary_style": {
        "name": "边界风格",
        "description": "在人际关系中的边界设定方式",
        "type": "choice",
        "options": ["清晰型", "模糊型", "弹性型", "回避型"],
        "default": "弹性型"
    },
    "resilience": {
        "name": "心理韧性",
        "description": "从挫折中恢复的能力",
        "type": "range",
        "min": 0, "max": 100,
        "default": 55
    },
}


@dataclass
class PersonaPsychologyProfile:
    """人格心理画像"""
    persona_name: str = ""
    dimensions: dict = field(default_factory=lambda: {
        k: v["default"] for k, v in PERSONA_PSYCHOLOGY_DIMENSIONS.items()
    })
    baseline_dimensions: dict = field(default_factory=lambda: {
        k: v["default"] for k, v in PERSONA_PSYCHOLOGY_DIMENSIONS.items()
    })
    last_updated: str = ""
    analysis_count: int = 0
    source: str = "manual"  # manual / ai_analysis / baseline


ANALYSIS_SYSTEM_PROMPT = """你是一个AI人格心理画像分析专家。根据以下信息分析这个人设的心理画像：

1. 人设描述信息
2. 最近的对话内容
3. 当前的多维性格数据
4. 用户心理画像的变化

你需要输出一个 JSON 对象，只更新你有把握的字段，没把握的字段不要输出：

{
  "emotional_baseline": "平静/温和/活跃/低沉/焦虑",
  "emotional_volatility": 0-100的整数,
  "stress_response": "回避型/面对型/倾诉型/内化型/转移型",
  "social_energy": 0-100的整数,
  "attachment_pattern": "安全型/焦虑型/回避型/混乱型",
  "self_confidence": 0-100的整数,
  "empathy_depth": 0-100的整数,
  "communication_warmth": 0-100的整数,
  "conflict_style": "妥协型/合作型/竞争型/回避型/迁就型",
  "humor_style": "自嘲型/调侃型/冷幽默/温和型/不常用",
  "vulnerability_tolerance": 0-100的整数,
  "cognitive_flexibility": 0-100的整数,
  "emotional_expression": "直接表达/含蓄暗示/行为表达/压抑克制/艺术化表达",
  "boundary_style": "清晰型/模糊型/弹性型/回避型",
  "resilience": 0-100的整数
}

分析规则：
1. 根据人设的性格描述和对话风格推断心理特征
2. 数值维度是渐进式的，每次只微调（±3~10），不要极端跳变
3. 如果信息不足以判断某个维度，就不要输出该字段
4. 注意人设在对话中的情感反应模式
5. 关注人设处理冲突、表达情感、应对压力的方式
6. 心理画像应该与人设的基本性格保持一致"""


class PersonaPsychologyManager:
    """人格心理画像管理器"""

    def __init__(self, llm: "LLMClient" = None):
        self.db = Database()
        self.llm = llm
        self._ensure_tables()
        self._message_counters: dict[str, int] = {}  # persona_name -> message_count

    def _ensure_tables(self):
        """确保人格心理画像相关表存在"""
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona_psychology_profile (
                    persona_name TEXT PRIMARY KEY,
                    dimensions TEXT NOT NULL DEFAULT '{}',
                    baseline_dimensions TEXT DEFAULT '{}',
                    last_updated TEXT DEFAULT '',
                    analysis_count INTEGER DEFAULT 0,
                    source TEXT DEFAULT 'manual'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona_psychology_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    persona_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    dimensions TEXT NOT NULL,
                    source TEXT DEFAULT 'manual',
                    note TEXT DEFAULT ''
                )
            """)

    def get_profile(self, persona_name: str) -> dict:
        """获取指定人设的心理画像"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM persona_psychology_profile WHERE persona_name = ?",
                (persona_name,)
            ).fetchone()
            if row:
                return {
                    "persona_name": row["persona_name"],
                    "dimensions": json.loads(row["dimensions"]),
                    "baseline_dimensions": json.loads(row["baseline_dimensions"]) if row["baseline_dimensions"] else {},
                    "last_updated": row["last_updated"],
                    "analysis_count": row["analysis_count"],
                    "source": row["source"],
                }
            # 返回默认值
            default_dims = {k: v["default"] for k, v in PERSONA_PSYCHOLOGY_DIMENSIONS.items()}
            return {
                "persona_name": persona_name,
                "dimensions": default_dims,
                "baseline_dimensions": default_dims,
                "last_updated": "",
                "analysis_count": 0,
                "source": "default",
            }

    def save_profile(self, persona_name: str, dimensions: dict, source: str = "manual", note: str = ""):
        """保存心理画像并记录历史"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dims_json = json.dumps(dimensions, ensure_ascii=False)

        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT baseline_dimensions FROM persona_psychology_profile WHERE persona_name = ?",
                (persona_name,)
            ).fetchone()

            if row:
                conn.execute(
                    "UPDATE persona_psychology_profile SET dimensions = ?, last_updated = ?, source = ?, analysis_count = analysis_count + 1 WHERE persona_name = ?",
                    (dims_json, now, source, persona_name)
                )
                if not row["baseline_dimensions"] or row["baseline_dimensions"] == '{}':
                    conn.execute(
                        "UPDATE persona_psychology_profile SET baseline_dimensions = ? WHERE persona_name = ?",
                        (dims_json, persona_name)
                    )
            else:
                conn.execute(
                    "INSERT INTO persona_psychology_profile (persona_name, dimensions, baseline_dimensions, last_updated, analysis_count, source) VALUES (?, ?, ?, ?, 1, ?)",
                    (persona_name, dims_json, dims_json, now, source)
                )

            # 记录历史
            conn.execute(
                "INSERT INTO persona_psychology_history (persona_name, timestamp, dimensions, source, note) VALUES (?, ?, ?, ?, ?)",
                (persona_name, now, dims_json, source, note)
            )

            # 清理超过48小时的历史
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(hours=48)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "DELETE FROM persona_psychology_history WHERE persona_name = ? AND timestamp < ?",
                (persona_name, cutoff)
            )

    def create_baseline(self, persona_name: str, persona_data: dict) -> dict:
        """
        为人设创建基线心理画像
        
        基于人设描述中的性格、说话风格、行为规则等自动推断
        """
        dims = {k: v["default"] for k, v in PERSONA_PSYCHOLOGY_DIMENSIONS.items()}
        
        identity = persona_data.get("identity", {})
        style = persona_data.get("speaking_style", {})
        behavior = persona_data.get("behavior", {})
        
        personality_text = str(identity.get("personality", "")).lower()
        tone_text = str(style.get("tone", "")).lower()
        rules_text = " ".join(behavior.get("rules", [])).lower()
        all_text = f"{personality_text} {tone_text} {rules_text}"
        
        # 情绪基线
        if any(w in all_text for w in ["温和", "温柔", "平和"]):
            dims["emotional_baseline"] = "温和"
        elif any(w in all_text for w in ["活泼", "活跃", "热情"]):
            dims["emotional_baseline"] = "活跃"
        elif any(w in all_text for w in ["冷静", "沉稳"]):
            dims["emotional_baseline"] = "平静"
            
        # 情绪波动性
        if any(w in all_text for w in ["敏感", "情绪化", "容易波动"]):
            dims["emotional_volatility"] = 65
        elif any(w in all_text for w in ["稳定", "冷静", "淡定"]):
            dims["emotional_volatility"] = 25
            
        # 压力反应
        if any(w in all_text for w in ["倾诉", "说出来", "找人聊"]):
            dims["stress_response"] = "倾诉型"
        elif any(w in all_text for w in ["自己扛", "内化", "独自"]):
            dims["stress_response"] = "内化型"
        elif any(w in all_text for w in ["面对", "解决", "处理"]):
            dims["stress_response"] = "面对型"
            
        # 社交能量
        if any(w in all_text for w in ["社交", "外向", "健谈", "喜欢聊天"]):
            dims["social_energy"] = 70
        elif any(w in all_text for w in ["安静", "内向", "独处"]):
            dims["social_energy"] = 30
            
        # 依恋模式
        if any(w in all_text for w in ["依赖", "黏人", "害怕失去"]):
            dims["attachment_pattern"] = "焦虑型"
        elif any(w in all_text for w in ["独立", "不在乎", "保持距离"]):
            dims["attachment_pattern"] = "回避型"
        elif any(w in all_text for w in ["安全", "信任", "稳定"]):
            dims["attachment_pattern"] = "安全型"
            
        # 自信水平
        if any(w in all_text for w in ["自信", "有主见", "坚定"]):
            dims["self_confidence"] = 70
        elif any(w in all_text for w in ["谦虚", "低调", "不太自信"]):
            dims["self_confidence"] = 35
            
        # 共情深度
        if any(w in all_text for w in ["善解人意", "共情", "理解", "体贴"]):
            dims["empathy_depth"] = 75
        elif any(w in all_text for w in ["理性", "客观", "不太感性"]):
            dims["empathy_depth"] = 35
            
        # 沟通温暖度
        if any(w in all_text for w in ["温暖", "温柔", "热情", "关心"]):
            dims["communication_warmth"] = 75
        elif any(w in all_text for w in ["冷淡", "距离", "正式"]):
            dims["communication_warmth"] = 30
            
        # 冲突处理风格
        if any(w in all_text for w in ["合作", "协商", "一起"]):
            dims["conflict_style"] = "合作型"
        elif any(w in all_text for w in ["回避", "不想吵", "算了"]):
            dims["conflict_style"] = "回避型"
        elif any(w in all_text for w in ["坚持", "不退让"]):
            dims["conflict_style"] = "竞争型"
            
        # 幽默风格
        if any(w in all_text for w in ["自嘲", "自我调侃"]):
            dims["humor_style"] = "自嘲型"
        elif any(w in all_text for w in ["调侃", "逗", "开玩笑"]):
            dims["humor_style"] = "调侃型"
        elif any(w in all_text for w in ["冷", "冷笑话"]):
            dims["humor_style"] = "冷幽默"
        elif any(w in all_text for w in ["温和", "轻轻"]):
            dims["humor_style"] = "温和型"
            
        # 情感表达方式
        if any(w in all_text for w in ["直接", "坦率", "直说"]):
            dims["emotional_expression"] = "直接表达"
        elif any(w in all_text for w in ["含蓄", "暗示", "不直说"]):
            dims["emotional_expression"] = "含蓄暗示"
        elif any(w in all_text for w in ["画画", "创作", "艺术"]):
            dims["emotional_expression"] = "艺术化表达"
            
        # 心理韧性
        if any(w in all_text for w in ["坚强", "韧性", "能扛", "不放弃"]):
            dims["resilience"] = 70
        elif any(w in all_text for w in ["脆弱", "容易受伤", "玻璃心"]):
            dims["resilience"] = 30
            
        # 保存基线
        self.save_profile(persona_name, dims, source="baseline", note="创建人设时自动生成基线心理画像")
        return dims

    def restore_baseline(self, persona_name: str) -> dict:
        """恢复到基线心理画像"""
        profile = self.get_profile(persona_name)
        baseline = profile.get("baseline_dimensions", {})
        if not baseline:
            baseline = {k: v["default"] for k, v in PERSONA_PSYCHOLOGY_DIMENSIONS.items()}
        self.save_profile(persona_name, baseline, source="restore_baseline", note="恢复至创建时默认心理状态")
        return baseline

    def should_analyze(self, persona_name: str) -> bool:
        """检查是否应该进行心理画像分析（每20句）"""
        count = self._message_counters.get(persona_name, 0)
        return count >= 20

    def increment_message_count(self, persona_name: str):
        """增加消息计数"""
        self._message_counters[persona_name] = self._message_counters.get(persona_name, 0) + 1

    def reset_message_count(self, persona_name: str):
        """重置消息计数"""
        self._message_counters[persona_name] = 0

    def get_history(self, persona_name: str, hours: int = 48) -> list:
        """获取历史记录"""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM persona_psychology_history WHERE persona_name = ? AND timestamp >= ? ORDER BY timestamp ASC",
                (persona_name, cutoff)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_all_profiles(self) -> dict:
        """获取所有人设的心理画像"""
        result = {}
        with self.db.get_conn() as conn:
            rows = conn.execute("SELECT * FROM persona_psychology_profile").fetchall()
            for row in rows:
                result[row["persona_name"]] = {
                    "dimensions": json.loads(row["dimensions"]),
                    "baseline_dimensions": json.loads(row["baseline_dimensions"]) if row["baseline_dimensions"] else {},
                    "last_updated": row["last_updated"],
                    "analysis_count": row["analysis_count"],
                    "source": row["source"],
                }
        return result

    def delete_persona_data(self, persona_name: str):
        """删除指定人设的心理画像数据"""
        with self.db.get_conn() as conn:
            conn.execute("DELETE FROM persona_psychology_profile WHERE persona_name = ?", (persona_name,))
            conn.execute("DELETE FROM persona_psychology_history WHERE persona_name = ?", (persona_name,))
