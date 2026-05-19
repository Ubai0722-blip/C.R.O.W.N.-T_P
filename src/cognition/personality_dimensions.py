# by UBAI
"""
personality_dimensions.py
多维性格量化系统 - 独立于人设基础性格的深层性格维度

核心设计理念：
1. 多维度性格量化：将人格拆解为可量化的性格维度（0-100）
2. 雷达图可视化：前端用 Chart.js 雷达图展示
3. 深层影响：对交流内容的影响优先度远高于人设控制页面的性格部分
4. 时间维度：保留历史调试数据，支持回退
5. 强绑定人设：每个人设有独立的多维性格数据
"""

import json
import math
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from ..memory.database import Database


# ========== 性格维度定义 ==========

PERSONALITY_DIMENSIONS = {
    # Big Five + 扩展维度
    "openness": {
        "name": "开放性",
        "description": "对新事物、新体验的接受程度。高分：好奇、富有想象力、喜欢尝试；低分：保守、偏好传统、喜欢稳定",
        "default": 50,
        "icon": "🌐"
    },
    "conscientiousness": {
        "name": "尽责性",
        "description": "自律、有组织、负责任的程度。高分：严谨、有计划、可靠；低分：随性、灵活、不拘小节",
        "default": 50,
        "icon": "📋"
    },
    "extraversion": {
        "name": "外向性",
        "description": "社交活跃度和精力来源。高分：热情、健谈、喜欢社交；低分：安静、内敛、偏好独处",
        "default": 50,
        "icon": "🗣️"
    },
    "agreeableness": {
        "name": "宜人性",
        "description": "友善、合作、信任他人的程度。高分：温和、体贴、乐于助人；低分：直率、独立、有竞争意识",
        "default": 50,
        "icon": "🤝"
    },
    "neuroticism": {
        "name": "神经质",
        "description": "情绪波动和焦虑倾向。高分：敏感、易焦虑、情绪化；低分：冷静、稳定、不容易受情绪影响",
        "default": 50,
        "icon": "🌊"
    },
    # 扩展维度
    "emotionality": {
        "name": "情感表达",
        "description": "表达情感的倾向和强度。高分：善于表达感受、情感丰富；低分：含蓄内敛、不轻易表露情感",
        "default": 50,
        "icon": "💖"
    },
    "creativity": {
        "name": "创造力",
        "description": "创造性思维和艺术感知力。高分：富有创意、善于联想、审美独特；低分：务实、注重实际、按部就班",
        "default": 50,
        "icon": "🎨"
    },
    "dominance": {
        "name": "主导性",
        "description": "在社交互动中的主导倾向。高分：自信、有主见、喜欢引导话题；低分：顺从、配合、喜欢跟随",
        "default": 50,
        "icon": "👑"
    },
    "empathy": {
        "name": "共情力",
        "description": "理解和感受他人情绪的能力。高分：善解人意、能感受他人情绪；低分：理性客观、不太受他人情绪影响",
        "default": 50,
        "icon": "🫂"
    },
    "impulsiveness": {
        "name": "冲动性",
        "description": "行为决策的速度和冲动程度。高分：反应快、凭直觉行动；低分：深思熟虑、谨慎决策",
        "default": 50,
        "icon": "⚡"
    },
    "independence": {
        "name": "独立性",
        "description": "自主决策和不依赖他人的程度。高分：自主、有主见、不依赖他人；低分：依赖、寻求认同、重视他人意见",
        "default": 50,
        "icon": "🦅"
    },
    "humor": {
        "name": "幽默感",
        "description": "使用幽默和轻松方式交流的倾向。高分：风趣、喜欢开玩笑、善于活跃气氛；低分：严肃、正经、不常开玩笑",
        "default": 50,
        "icon": "😄"
    },
    "warmth": {
        "name": "温暖度",
        "description": "对待他人的温暖和关怀程度。高分：热情、关心他人、让人感到温暖；低分：冷淡、保持距离、公事公办",
        "default": 50,
        "icon": "☀️"
    },
    "sensitivity": {
        "name": "敏感度",
        "description": "对外界刺激和他人言行的敏感程度。高分：细腻、容易察觉细节变化；低分：钝感、不太在意细节",
        "default": 50,
        "icon": "🔔"
    },
    "rationality": {
        "name": "理性度",
        "description": "决策和思考中理性与感性的比重。高分：逻辑驱动、注重分析；低分：直觉驱动、注重感受",
        "default": 50,
        "icon": "🧠"
    },
}

# 所有维度名称列表
DIMENSION_KEYS = list(PERSONALITY_DIMENSIONS.keys())


@dataclass
class PersonalitySnapshot:
    """性格快照 - 某一时刻的完整多维性格数据"""
    persona_name: str = ""
    timestamp: str = ""
    dimensions: dict = field(default_factory=lambda: {k: v["default"] for k, v in PERSONALITY_DIMENSIONS.items()})
    source: str = "manual"  # manual / ai_analysis / rollback
    note: str = ""

    def to_dict(self):
        return {
            "persona_name": self.persona_name,
            "timestamp": self.timestamp,
            "dimensions": self.dimensions,
            "source": self.source,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            persona_name=d.get("persona_name", ""),
            timestamp=d.get("timestamp", ""),
            dimensions=d.get("dimensions", {}),
            source=d.get("source", "manual"),
            note=d.get("note", ""),
        )


class PersonalityDimensionManager:
    """
    多维性格管理器
    
    职责：
    1. 管理每个多维性格数据
    2. 从人设描述自动分析生成初始多维性格
    3. 保存/读取数据库
    4. 历史记录管理（0-8小时窗口，2小时自动清理）
    5. 回退功能
    """

    def __init__(self):
        self.db = Database()
        self._ensure_tables()

    def _ensure_tables(self):
        """确保多维性格相关表存在"""
        with self.db.get_conn() as conn:
            # 当前多维性格数据
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona_dimensions (
                    persona_name TEXT PRIMARY KEY,
                    dimensions TEXT NOT NULL DEFAULT '{}',
                    last_updated TEXT NOT NULL,
                    source TEXT DEFAULT 'manual',
                    baseline_dimensions TEXT DEFAULT '{}',
                    baseline_created TEXT DEFAULT ''
                )
            """)
            # 多维性格历史记录
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona_dimensions_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    persona_name TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    dimensions TEXT NOT NULL,
                    source TEXT DEFAULT 'manual',
                    note TEXT DEFAULT ''
                )
            """)

    def get_dimensions(self, persona_name: str) -> dict:
        """获取指定人设的当前多维性格数据"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT dimensions FROM persona_dimensions WHERE persona_name = ?",
                (persona_name,)
            ).fetchone()
            if row:
                return json.loads(row["dimensions"])
            return {k: v["default"] for k, v in PERSONALITY_DIMENSIONS.items()}

    def get_baseline(self, persona_name: str) -> dict:
        """获取指定人设的基线多维性格数据（创建人设时的默认值）"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT baseline_dimensions FROM persona_dimensions WHERE persona_name = ?",
                (persona_name,)
            ).fetchone()
            if row and row["baseline_dimensions"]:
                return json.loads(row["baseline_dimensions"])
            return {k: v["default"] for k, v in PERSONALITY_DIMENSIONS.items()}

    def save_dimensions(self, persona_name: str, dimensions: dict, source: str = "manual", note: str = ""):
        """保存多维性格数据并记录历史"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dimensions_json = json.dumps(dimensions, ensure_ascii=False)

        with self.db.get_conn() as conn:
            # 检查是否存在基线
            row = conn.execute(
                "SELECT baseline_dimensions FROM persona_dimensions WHERE persona_name = ?",
                (persona_name,)
            ).fetchone()

            if row:
                # 更新现有记录
                conn.execute(
                    "UPDATE persona_dimensions SET dimensions = ?, last_updated = ?, source = ? WHERE persona_name = ?",
                    (dimensions_json, now, source, persona_name)
                )
                # 如果没有基线，设置当前为基线
                if not row["baseline_dimensions"] or row["baseline_dimensions"] == '{}':
                    conn.execute(
                        "UPDATE persona_dimensions SET baseline_dimensions = ?, baseline_created = ? WHERE persona_name = ?",
                        (dimensions_json, now, persona_name)
                    )
            else:
                # 新建记录，当前值同时作为基线
                conn.execute(
                    "INSERT INTO persona_dimensions (persona_name, dimensions, last_updated, source, baseline_dimensions, baseline_created) VALUES (?, ?, ?, ?, ?, ?)",
                    (persona_name, dimensions_json, now, source, dimensions_json, now)
                )

            # 记录历史
            conn.execute(
                "INSERT INTO persona_dimensions_history (persona_name, timestamp, dimensions, source, note) VALUES (?, ?, ?, ?, ?)",
                (persona_name, now, dimensions_json, source, note)
            )

            # 清理超过8小时的历史记录
            cutoff = (datetime.now() - timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "DELETE FROM persona_dimensions_history WHERE persona_name = ? AND timestamp < ?",
                (persona_name, cutoff)
            )

    def set_baseline(self, persona_name: str, dimensions: dict):
        """设置基线性格（创建人设时调用）"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        dimensions_json = json.dumps(dimensions, ensure_ascii=False)
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM persona_dimensions WHERE persona_name = ?",
                (persona_name,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE persona_dimensions SET baseline_dimensions = ?, baseline_created = ? WHERE persona_name = ?",
                    (dimensions_json, now, persona_name)
                )
            else:
                conn.execute(
                    "INSERT INTO persona_dimensions (persona_name, dimensions, last_updated, source, baseline_dimensions, baseline_created) VALUES (?, ?, ?, ?, ?, ?)",
                    (persona_name, dimensions_json, now, "baseline", dimensions_json, now)
                )

    def restore_baseline(self, persona_name: str) -> dict:
        """恢复到基线性格"""
        baseline = self.get_baseline(persona_name)
        self.save_dimensions(persona_name, baseline, source="restore_baseline", note="恢复至创建时默认性格")
        return baseline

    def get_history(self, persona_name: str, hours: int = 8) -> list:
        """获取指定时间范围内的历史记录"""
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM persona_dimensions_history WHERE persona_name = ? AND timestamp >= ? ORDER BY timestamp ASC",
                (persona_name, cutoff)
            ).fetchall()
            return [dict(r) for r in rows]

    def rollback_to_time(self, persona_name: str, history_id: int) -> dict:
        """回退到指定历史记录的时间点"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM persona_dimensions_history WHERE id = ? AND persona_name = ?",
                (history_id, persona_name)
            ).fetchone()
            if not row:
                return {"ok": False, "msg": "历史记录不存在"}

            dimensions = json.loads(row["dimensions"])
            self.save_dimensions(
                persona_name, dimensions,
                source="rollback",
                note=f"回退至 {row['timestamp']} 的状态"
            )
            return {"ok": True, "dimensions": dimensions, "timestamp": row["timestamp"]}

    def cleanup_old_history(self):
        """清理超过2小时的早期历史（保留最新和最早各一条）"""
        with self.db.get_conn() as conn:
            cutoff = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            # 获取所有人设
            personas = conn.execute(
                "SELECT DISTINCT persona_name FROM persona_dimensions_history"
            ).fetchall()
            for (persona_name,) in personas:
                rows = conn.execute(
                    "SELECT id, timestamp FROM persona_dimensions_history WHERE persona_name = ? ORDER BY timestamp ASC",
                    (persona_name,)
                ).fetchall()
                if len(rows) <= 2:
                    continue
                # 删除超过2小时的，但保留最新一条
                old_rows = [r for r in rows if r["timestamp"] < cutoff]
                if len(old_rows) > 1:
                    # 保留最早的那条
                    ids_to_delete = [r["id"] for r in old_rows[:-1]]
                    for rid in ids_to_delete:
                        conn.execute("DELETE FROM persona_dimensions_history WHERE id = ?", (rid,))

    def analyze_from_persona(self, persona_name: str, persona_data: dict) -> dict:
        """
        从人设描述自动分析生成多维性格数据
        
        基于人设的 identity.personality, speaking_style, behavior 等字段
        使用规则推断各维度的初始值
        """
        dims = {k: v["default"] for k, v in PERSONALITY_DIMENSIONS.items()}
        
        # 提取人设信息
        identity = persona_data.get("identity", {})
        style = persona_data.get("speaking_style", {})
        behavior = persona_data.get("behavior", {})
        
        personality_text = str(identity.get("personality", ""))
        background_text = str(identity.get("background", ""))
        description_text = str(identity.get("description", ""))
        tone_text = str(style.get("tone", ""))
        verbal_tics = style.get("verbal_tics", [])
        sentence_length = str(style.get("sentence_length", ""))
        vocab_level = str(style.get("vocabulary_level", ""))
        emoji_usage = str(style.get("emoji_usage", ""))
        greeting = str(behavior.get("greeting", ""))
        rules = behavior.get("rules", [])
        
        all_text = f"{personality_text} {background_text} {description_text} {tone_text} {' '.join(verbal_tics)} {greeting} {' '.join(rules)}".lower()
        
        # 开放性分析
        if any(w in all_text for w in ["好奇", "创造", "想象", "新", "探索", "艺术", "画画", "插画"]):
            dims["openness"] = 72
        if any(w in all_text for w in ["传统", "保守", "稳定", "规矩"]):
            dims["openness"] = 35
            
        # 尽责性分析
        if any(w in all_text for w in ["严谨", "认真", "负责", "计划", "规律", "自律"]):
            dims["conscientiousness"] = 70
        if any(w in all_text for w in ["随性", "自由", "散漫", "灵活", "不拘"]):
            dims["conscientiousness"] = 35
            
        # 外向性分析
        if any(w in all_text for w in ["活泼", "热情", "健谈", "社交", "外向", "开朗"]):
            dims["extraversion"] = 72
        if any(w in all_text for w in ["安静", "内向", "内敛", "独处", "害羞", "腼腆"]):
            dims["extraversion"] = 30
        if sentence_length in ["极短", "短句为主"]:
            dims["extraversion"] = max(25, dims["extraversion"] - 15)
            
        # 宜人性分析
        if any(w in all_text for w in ["温柔", "温和", "善良", "体贴", "关心", "照顾", "耐心"]):
            dims["agreeableness"] = 75
        if any(w in all_text for w in ["直率", "固执", "有主见", "不附和", "竞争"]):
            dims["agreeableness"] = 40
            
        # 神经质分析
        if any(w in all_text for w in ["敏感", "焦虑", "情绪化", "易怒", "不安"]):
            dims["neuroticism"] = 65
        if any(w in all_text for w in ["冷静", "稳定", "淡定", "从容", "平和"]):
            dims["neuroticism"] = 30
            
        # 情感表达分析
        if any(w in all_text for w in ["温柔", "感性", "情感", "细腻", "表达"]):
            dims["emotionality"] = 70
        if any(w in all_text for w in ["含蓄", "内敛", "不表达", "沉默"]):
            dims["emotionality"] = 30
            
        # 创造力分析
        if any(w in all_text for w in ["画画", "插画", "艺术", "创作", "设计", "创意", "美术"]):
            dims["creativity"] = 80
        if any(w in all_text for w in ["务实", "实际", "技术", "工程"]):
            dims["creativity"] = 35
            
        # 主导性分析
        if any(w in all_text for w in ["自信", "主见", "领导", "强势", "独立"]):
            dims["dominance"] = 68
        if any(w in all_text for w in ["顺从", "配合", "跟随", "谦虚", "低调"]):
            dims["dominance"] = 30
            
        # 共情力分析
        if any(w in all_text for w in ["善解人意", "共情", "理解", "关心", "体贴", "安慰"]):
            dims["empathy"] = 75
        if any(w in all_text for w in ["理性", "客观", "冷静", "不太关心"]):
            dims["empathy"] = 35
            
        # 冲动性分析
        if any(w in all_text for w in ["冲动", "直觉", "快速", "急性子"]):
            dims["impulsiveness"] = 65
        if any(w in all_text for w in ["谨慎", "深思", "稳重", "慢热"]):
            dims["impulsiveness"] = 30
            
        # 独立性分析
        if any(w in all_text for w in ["独立", "自主", "自由", "自己", "一个人"]):
            dims["independence"] = 70
        if any(w in all_text for w in ["依赖", "陪伴", "需要人", "害怕孤独"]):
            dims["independence"] = 30
            
        # 幽默感分析
        if any(w in all_text for w in ["幽默", "搞笑", "玩笑", "逗", "有趣"]):
            dims["humor"] = 70
        if any(w in all_text for w in ["严肃", "正经", "认真", "不开玩笑"]):
            dims["humor"] = 30
            
        # 温暖度分析
        if any(w in all_text for w in ["温暖", "温柔", "热情", "关心", "体贴", "暖"]):
            dims["warmth"] = 75
        if any(w in all_text for w in ["冷淡", "距离", "公事", "冷漠"]):
            dims["warmth"] = 25
            
        # 敏感度分析
        if any(w in all_text for w in ["敏感", "细腻", "细心", "注意细节", "察觉"]):
            dims["sensitivity"] = 70
        if any(w in all_text for w in ["钝感", "粗心", "不在意", "大大咧咧"]):
            dims["sensitivity"] = 30
            
        # 理性度分析
        if any(w in all_text for w in ["理性", "逻辑", "分析", "客观", "冷静"]):
            dims["rationality"] = 70
        if any(w in all_text for w in ["感性", "直觉", "感受", "情绪", "跟着感觉"]):
            dims["rationality"] = 30
            
        # emoji 使用影响
        if emoji_usage in ["频繁", "经常"]:
            dims["emotionality"] = min(100, dims["emotionality"] + 10)
            dims["warmth"] = min(100, dims["warmth"] + 5)
        if emoji_usage in ["不用", "极少"]:
            dims["emotionality"] = max(0, dims["emotionality"] - 10)
            
        # 语气词影响
        if verbal_tics and len(verbal_tics) > 3:
            dims["warmth"] = min(100, dims["warmth"] + 8)
            dims["emotionality"] = min(100, dims["emotionality"] + 5)
            
        return dims

    def get_all_persona_dimensions(self) -> dict:
        """获取所有已保存的多维性格数据"""
        result = {}
        with self.db.get_conn() as conn:
            rows = conn.execute("SELECT persona_name, dimensions, baseline_dimensions, last_updated FROM persona_dimensions").fetchall()
            for row in rows:
                result[row["persona_name"]] = {
                    "current": json.loads(row["dimensions"]),
                    "baseline": json.loads(row["baseline_dimensions"]) if row["baseline_dimensions"] else {},
                    "last_updated": row["last_updated"],
                }
        return result

    def delete_persona_data(self, persona_name: str):
        """删除指定人设的所有多维性格数据"""
        with self.db.get_conn() as conn:
            conn.execute("DELETE FROM persona_dimensions WHERE persona_name = ?", (persona_name,))
            conn.execute("DELETE FROM persona_dimensions_history WHERE persona_name = ?", (persona_name,))
