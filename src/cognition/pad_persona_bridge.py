# by UBAI
"""
pad_persona_bridge.py
PAD情感模型 ↔ 人格系统 桥接模块

设计理念：
PAD模型（pad_emotion.py）提供三维情感坐标，但目前没有和人格系统联动。
本模块将 PAD 状态翻译为人格的动态调整参数，让人格随情感状态"活"起来。

核心机制：
1. PAD坐标 → 说话风格调整（语气词、句式、口头禅频率）
2. PAD坐标 → 行为倾向调整（主动关心频率、话题选择偏好）
3. PAD持久化：跨会话保存，模拟情感惯性
4. 衰减恢复：长时间不聊天，PAD自动回归基线
"""

import json
import time
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.database import Database
from ..cognition.pad_emotion import PADEmotionModel


@dataclass
class PersonaAdjustment:
    """人格动态调整参数"""
    # 语气调整
    tone_modifier: str = "自然"           # 语气修饰词
    energy_level: float = 0.5             # 能量水平 [0.0, 1.0] 低=慵懒 高=活泼
    verbal_tic_freq: float = 0.5          # 口头禅频率 [0.0, 1.0]
    sentence_length_bias: float = 0.0     # 句子长度偏移 [-1.0, 1.0] 负=更短 正=更长

    # 行为倾向
    care_tendency: float = 0.5            # 主动关心倾向 [0.0, 1.0]
    topic_openness: float = 0.5           # 话题开放度 [0.0, 1.0]
    humor_tendency: float = 0.5           # 幽默倾向 [0.0, 1.0]

    # Prompt 注入文本
    prompt_hint: str = ""                 # 直接注入 system prompt 的提示

    def is_neutral(self) -> bool:
        """是否处于中性状态（不需要特殊调整）"""
        return (
            abs(self.energy_level - 0.5) < 0.15
            and abs(self.care_tendency - 0.5) < 0.15
            and not self.prompt_hint
        )


# PAD坐标到离散情绪的映射
PAD_EMOTION_MAP = {
    # (P高, A高): 开心/兴奋
    (True, True): {
        "label": "开心/兴奋",
        "tone": "活泼轻快",
        "energy": 0.85,
        "verbal_tic": 0.7,
        "length": 0.2,
        "care": 0.6,
        "humor": 0.7,
        "hint": "你现在心情很好，说话会不自觉地带上笑意，偶尔会用感叹号，"
                "语气轻快活泼，可能会主动分享开心的事情。",
    },
    # (P高, A低): 舒适/放松
    (True, False): {
        "label": "舒适/放松",
        "tone": "温柔平和",
        "energy": 0.4,
        "verbal_tic": 0.3,
        "length": -0.1,
        "care": 0.7,
        "humor": 0.4,
        "hint": "你现在处于很放松的状态，说话慢悠悠的，语气很温柔，"
                "但不要形成固定口癖，直接说内容会更自然。",
    },
    # (P低, A高): 烦躁/愤怒
    (False, True): {
        "label": "烦躁/不安",
        "tone": "有点冲",
        "energy": 0.75,
        "verbal_tic": 0.2,
        "length": 0.1,
        "care": 0.3,
        "humor": 0.2,
        "hint": "你现在心里有点烦躁，说话可能会比较直接，甚至有点冲，"
                "语气不像平时那么温和，偶尔会叹气。",
    },
    # (P低, A低): 低落/疲惫
    (False, False): {
        "label": "低落/疲惫",
        "tone": "有气无力",
        "energy": 0.2,
        "verbal_tic": 0.15,
        "length": -0.3,
        "care": 0.4,
        "humor": 0.1,
        "hint": "你现在情绪比较低落，说话没什么力气，回复会很简短，"
                "但不要反复用'嗯'、'哦'应付，可以用简短但具体的话回应。",
    },
}


class PADPersonaBridge:
    """PAD情感模型与人格系统的桥接器"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = Database()
        self._pad: PADEmotionModel | None = None
        self._init_table()

    def _init_table(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS pad_state (
                    user_id TEXT PRIMARY KEY,
                    p_value REAL DEFAULT 0.0,
                    a_value REAL DEFAULT 0.0,
                    d_value REAL DEFAULT 0.0,
                    base_p REAL DEFAULT 0.0,
                    base_a REAL DEFAULT 0.0,
                    base_d REAL DEFAULT 0.0,
                    last_update TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    # ========== PAD 状态管理 ==========

    def get_pad(self) -> PADEmotionModel:
        """获取 PAD 模型实例（带持久化恢复）"""
        if self._pad is not None:
            return self._pad

        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM pad_state WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()

        if row:
            self._pad = PADEmotionModel(
                base_p=row["base_p"],
                base_a=row["base_a"],
                base_d=row["base_d"],
            )
            self._pad.p = row["p_value"]
            self._pad.a = row["a_value"]
            self._pad.d = row["d_value"]
            # 恢复时间戳用于衰减计算
            try:
                self._pad.last_update = datetime.strptime(
                    row["last_update"], "%Y-%m-%d %H:%M:%S"
                ).timestamp()
            except:
                self._pad.last_update = time.time()
        else:
            self._pad = PADEmotionModel()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO pad_state "
                    "(user_id, p_value, a_value, d_value, base_p, base_a, base_d, "
                    "last_update, created_at) "
                    "VALUES (?, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, ?, ?)",
                    (self.user_id, now, now),
                )

        return self._pad

    def save_pad(self):
        """持久化 PAD 状态"""
        pad = self.get_pad()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE pad_state SET "
                "p_value = ?, a_value = ?, d_value = ?, "
                "last_update = ? WHERE user_id = ?",
                (pad.p, pad.a, pad.d, now, self.user_id),
            )

    def receive_stimulus(
        self,
        target_p: float,
        target_a: float,
        target_d: float,
        intensity: float = 0.3,
    ):
        """
        接收外界刺激并更新 PAD 状态
        
        参数：
        - target_p/a/d: 刺激目标的 PAD 坐标
        - intensity: 刺激强度 (0.0-1.0)，越强情绪变化越大
        """
        pad = self.get_pad()
        pad.receive_stimulus(target_p, target_a, target_d, intensity)
        self.save_pad()

    def receive_emotion_stimulus(self, emotion: str, intensity: str = "中度"):
        """
        从离散情绪标签接收刺激（方便与 emotion.py 联动）
        """
        from ..cognition.pad_emotion import PADEmotionModel

        # 情绪→PAD坐标映射
        emotion_pad = {
            "开心":   (0.7, 0.6, 0.3),
            "感动":   (0.5, 0.5, 0.2),
            "撒娇":   (0.3, 0.4, -0.2),
            "好奇":   (0.2, 0.5, 0.1),
            "无聊":   (-0.1, 0.1, -0.1),
            "敷衍":   (-0.2, 0.1, -0.2),
            "疲惫":   (-0.3, -0.3, -0.3),
            "焦虑":   (-0.4, 0.7, -0.4),
            "难过":   (-0.6, 0.4, -0.3),
            "生气":   (-0.7, 0.8, 0.3),
            "平静":   (0.0, 0.0, 0.0),
            "兴奋":   (0.8, 0.9, 0.4),
            "惊喜":   (0.8, 0.8, 0.3),
            "崩溃":   (-0.9, 0.9, -0.5),
            "治愈":   (0.6, 0.3, 0.2),
        }

        target = emotion_pad.get(emotion, (0.0, 0.0, 0.0))

        # 强度映射
        intensity_map = {"轻度": 0.2, "中度": 0.4, "强烈": 0.7}
        actual_intensity = intensity_map.get(intensity, 0.4)

        self.receive_stimulus(
            target[0], target[1], target[2], actual_intensity
        )

    # ========== 人格调整计算 ==========

    def get_adjustment(self) -> PersonaAdjustment:
        """
        根据当前 PAD 状态计算人格调整参数
        """
        pad = self.get_pad()

        # 触发时间衰减
        pad._apply_time_decay()

        # 确定当前 PAD 象限
        high_p = pad.p > 0.15
        high_a = pad.a > 0.15

        # 查找对应的调整方案
        config = PAD_EMOTION_MAP.get((high_p, high_a), {
            "label": "平静",
            "tone": "自然",
            "energy": 0.5,
            "verbal_tic": 0.5,
            "length": 0.0,
            "care": 0.5,
            "humor": 0.5,
            "hint": "",
        })

        # 根据 PAD 值的强度做微调
        # P值越高（越开心），能量越高
        energy = config["energy"]
        if pad.p > 0:
            energy = min(1.0, energy + pad.p * 0.15)
        elif pad.p < -0.3:
            energy = max(0.0, energy + pad.p * 0.1)

        # A值越高（越激动），句子越长（话多）
        length_bias = config["length"]
        if pad.a > 0.5:
            length_bias += 0.15
        elif pad.a < -0.3:
            length_bias -= 0.15

        # D值越高（越有支配感），关心倾向越低（更自我）
        care = config["care"]
        if pad.d > 0.3:
            care = max(0.2, care - 0.1)
        elif pad.d < -0.3:
            care = min(0.9, care + 0.1)

        # 构建 prompt hint
        hint = config.get("hint", "")
        if hint:
            hint = f"[情感状态动态调整]\n{hint}\n"

        # 如果 PAD 值非常极端，追加强化提示
        if pad.a > 0.7:
            hint += "（你现在情绪很激动，说话可能会有点冲动，带很多感叹号）\n"
        elif pad.a < -0.5:
            hint += "（你现在非常慵懒，连打字都不太想，回复尽可能简短）\n"
        if pad.p < -0.6:
            hint += "（你心里一直有股闷气没消，态度比较冷淡）\n"

        return PersonaAdjustment(
            tone_modifier=config["tone"],
            energy_level=energy,
            verbal_tic_freq=config["verbal_tic"],
            sentence_length_bias=length_bias,
            care_tendency=care,
            topic_openness=0.5,
            humor_tendency=config["humor"],
            prompt_hint=hint.strip(),
        )

    def get_prompt_context(self) -> str:
        """
        获取当前 PAD 状态的 Prompt 注入文本
        用于注入到 pipeline 的 context 构建中
        """
        pad = self.get_pad()
        adjustment = self.get_adjustment()

        if adjustment.is_neutral():
            return ""

        lines = [
            f"[情感惯性] 你当前的情感坐标是 "
            f"(愉悦度:{pad.p:.2f}, 唤醒度:{pad.a:.2f}, 支配度:{pad.d:.2f})",
        ]

        if adjustment.prompt_hint:
            lines.append(adjustment.prompt_hint)

        # 能量水平提示
        if adjustment.energy_level < 0.3:
            lines.append("你现在的能量很低，说话有气无力的")
        elif adjustment.energy_level > 0.75:
            lines.append("你现在精力充沛，说话很有活力")

        return "\n".join(lines)

    # ========== 调试 ==========

    def get_status(self) -> str:
        """获取 PAD 状态（供调试命令使用）"""
        pad = self.get_pad()
        adjustment = self.get_adjustment()

        label_map = {
            (True, True): "开心/兴奋",
            (True, False): "舒适/放松",
            (False, True): "烦躁/不安",
            (False, False): "低落/疲惫",
        }
        high_p = pad.p > 0.15
        high_a = pad.a > 0.15
        label = label_map.get((high_p, high_a), "平静")

        lines = [
            f"PAD 状态：{label}",
            f"  愉悦度(P): {pad.p:.3f} {'↑' if pad.p > 0 else '↓'}",
            f"  唤醒度(A): {pad.a:.3f} {'↑' if pad.a > 0 else '↓'}",
            f"  支配度(D): {pad.d:.3f} {'↑' if pad.d > 0 else '↓'}",
            f"人格调整：",
            f"  语气: {adjustment.tone_modifier}",
            f"  能量: {adjustment.energy_level:.2f}",
            f"  关心倾向: {adjustment.care_tendency:.2f}",
            f"  幽默倾向: {adjustment.humor_tendency:.2f}",
        ]
        if adjustment.prompt_hint:
            lines.append(f"  提示: {adjustment.prompt_hint[:50]}...")

        return "\n".join(lines)
