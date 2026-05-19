# by UBAI
"""
persona_control.py
人格控制中心 - 残差分析、累计偏差、可采纳性判定、修正参数生成

核心设计理念：
1. 残差标签（Residual Labels）：每个对话轮次产生的人格偏移量
2. 累计偏差（Cumulative Deviation）：多个残差标签的滑动窗口累积
3. 可采纳性（Adoptability）：判定偏差是否在可接受范围内
4. 修正参数生成：偏差超阈值时，生成一组参数化提示词修正人格

数据流：
  对话 → 残差计算 → 累计偏差更新 → 可采纳性判定
                                                    │
                           ┌────────────────────────┤
                           │                        │
                      偏差可接受                 偏差超阈值
                      (语义稀释容忍)             (触发修正)
                           │                        │
                           ▼                        ▼
                    继续当前人格状态          生成修正参数
                                              → 生成修正提示词组
                                              → 注入pipeline修正
"""

import json
import math
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.database import Database


# ========== 残差标签维度定义 ==========

@dataclass
class ResidualLabel:
    """
    残差标签：记录一次对话中的人格偏移
    
    每个维度的值域 [-1.0, 1.0]：
    - 正值 = 向某个方向偏移
    - 负值 = 向相反方向偏移
    - 0.0 = 无偏移
    """
    timestamp: str = ""
    
    # 语气维度残差
    tone_warmth: float = 0.0       # 温暖度残差（正=更温暖，负=更冷淡）
    tone_formality: float = 0.0    # 正式度残差（正=更正式，负=更随意）
    tone_energy: float = 0.0       # 能量残差（正=更活泼，负=更慵懒）
    
    # 行为维度残差
    care_intensity: float = 0.0    # 关心强度残差
    humor_frequency: float = 0.0   # 幽默频率残差
    verbosity: float = 0.0         # 话多程度残差（正=话多，负=话少）
    
    # 身份维度残差（最关键——偏离角色身份）
    identity_drift: float = 0.0    # 身份漂移（正=偏离角色，负=过度入戏）
    knowledge_overflow: float = 0.0 # 知识溢出（使用了角色不该知道的知识）
    
    # 情感维度残差
    emotional_mirroring: float = 0.0  # 情感镜像度（正=过度共情，负=缺乏共情）
    
    def magnitude(self) -> float:
        """计算残差向量的总幅度（L2范数）"""
        values = [
            self.tone_warmth, self.tone_formality, self.tone_energy,
            self.care_intensity, self.humor_frequency, self.verbosity,
            self.identity_drift, self.knowledge_overflow,
            self.emotional_mirroring,
        ]
        return math.sqrt(sum(v ** 2 for v in values))

    def dominant_dimension(self) -> tuple[str, float]:
        """找到偏移最大的维度"""
        dims = {
            "tone_warmth": self.tone_warmth,
            "tone_formality": self.tone_formality,
            "tone_energy": self.tone_energy,
            "care_intensity": self.care_intensity,
            "humor_frequency": self.humor_frequency,
            "verbosity": self.verbosity,
            "identity_drift": self.identity_drift,
            "knowledge_overflow": self.knowledge_overflow,
            "emotional_mirroring": self.emotional_mirroring,
        }
        max_dim = max(dims.items(), key=lambda x: abs(x[1]))
        return max_dim


@dataclass
class CumulativeDeviation:
    """
    累计偏差：滑动窗口内残差标签的累积
    
    使用指数加权移动平均（EWMA），近期偏差权重更大。
    """
    # 各维度的累计偏差值
    dims: dict[str, float] = field(default_factory=lambda: {
        "tone_warmth": 0.0,
        "tone_formality": 0.0,
        "tone_energy": 0.0,
        "care_intensity": 0.0,
        "humor_frequency": 0.0,
        "verbosity": 0.0,
        "identity_drift": 0.0,
        "knowledge_overflow": 0.0,
        "emotional_mirroring": 0.0,
    })
    
    # EWMA 衰减因子（0 < alpha <= 1，越大越重视近期）
    alpha: float = 0.3
    
    # 累计样本数
    sample_count: int = 0
    
    def update(self, residual: ResidualLabel):
        """用新的残差标签更新累计偏差"""
        residual_dict = {
            "tone_warmth": residual.tone_warmth,
            "tone_formality": residual.tone_formality,
            "tone_energy": residual.tone_energy,
            "care_intensity": residual.care_intensity,
            "humor_frequency": residual.humor_frequency,
            "verbosity": residual.verbosity,
            "identity_drift": residual.identity_drift,
            "knowledge_overflow": residual.knowledge_overflow,
            "emotional_mirroring": residual.emotional_mirroring,
        }
        
        for dim, new_val in residual_dict.items():
            old_val = self.dims.get(dim, 0.0)
            # EWMA: new_avg = alpha * new_val + (1-alpha) * old_avg
            self.dims[dim] = self.alpha * new_val + (1 - self.alpha) * old_val
        
        self.sample_count += 1

    def total_magnitude(self) -> float:
        """累计偏差总幅度"""
        return math.sqrt(sum(v ** 2 for v in self.dims.values()))

    def get_significant_dims(self, threshold: float = 0.15) -> dict[str, float]:
        """获取超过阈值的显著偏差维度"""
        return {k: v for k, v in self.dims.items() if abs(v) >= threshold}


@dataclass
class AdoptabilityVerdict:
    """可采纳性判定结果"""
    is_adoptable: bool           # 是否可采纳（偏差在可接受范围内）
    confidence: float            # 判定置信度 0.0-1.0
    severity: str                # 严重程度：minor/moderate/critical
    cumulative_magnitude: float  # 累计偏差幅度
    significant_dims: dict[str, float] = field(default_factory=dict)
    action: str = ""             # 建议动作：accept/dilute/correct


@dataclass
class CorrectionParameters:
    """修正参数：由累计偏差计算生成"""
    # 修正标签（每个维度的修正目标值）
    correction_targets: dict[str, float] = field(default_factory=dict)
    
    # 修正强度 [0.0, 1.0]
    correction_strength: float = 0.5
    
    # 修正提示词组
    correction_prompts: list[str] = field(default_factory=list)
    
    # 修正策略
    strategy: str = "gentle"     # gentle/firm/immediate


# ========== 维度名称映射 ==========

DIM_CN = {
    "tone_warmth": "温暖度",
    "tone_formality": "正式度",
    "tone_energy": "能量感",
    "care_intensity": "关心强度",
    "humor_frequency": "幽默频率",
    "verbosity": "话多程度",
    "identity_drift": "身份漂移",
    "knowledge_overflow": "知识溢出",
    "emotional_mirroring": "情感镜像",
}

# 维度修正提示词模板
CORRECTION_TEMPLATES = {
    "tone_warmth": {
        "positive": "你最近说话有点太冷淡了，请恢复你平时温暖的语气，多用一些亲切的表达。",
        "negative": "你最近说话过于热情了，请适当收敛，回到你平时自然的状态。",
    },
    "tone_formality": {
        "positive": "你最近说话太正式了，像在写报告。请回到你平时随意的口语风格。",
        "negative": "你最近说话太随意了，请稍微注意一下表达的完整性。",
    },
    "tone_energy": {
        "positive": "你最近回复太没精神了，请稍微振作一点，保持你平时的活力。",
        "negative": "你最近太亢奋了，请稍微冷静一下，回到正常状态。",
    },
    "care_intensity": {
        "positive": "你最近对用户关心不够，请多表达一些关心和在意。",
        "negative": "你最近关心过度了，给用户一些空间，不要每句话都问长问短。",
    },
    "humor_frequency": {
        "positive": "你最近太严肃了，适当加一些幽默和玩笑。",
        "negative": "你最近玩笑开太多了，请适当严肃一点。",
    },
    "verbosity": {
        "positive": "你最近话太少了，请多说一点，分享你的想法。",
        "negative": "你最近话太多了，请精简回复，不要长篇大论。",
    },
    "identity_drift": {
        "positive": "【紧急】你正在偏离角色身份。请立刻记住：你就是这个角色本人，不是AI助手。不要用客观、分析的语气说话。",
        "negative": "你有点过于入戏了，保持角色的同时也要注意不要做出超出角色能力范围的事情。",
    },
    "knowledge_overflow": {
        "positive": "你刚才使用了超出你角色知识范围的信息。请只使用你角色应该知道的知识。",
        "negative": "",
    },
    "emotional_mirroring": {
        "positive": "你对用户情绪的回应过于平淡了，请多一些共情和情感表达。",
        "negative": "你对用户情绪的反应过度了，请适当保持冷静，不要被用户情绪完全带着走。",
    },
}


class PersonaController:
    """
    人格控制中心
    
    职责：
    1. 计算每轮对话的残差标签
    2. 维护累计偏差（EWMA）
    3. 判定可采纳性
    4. 生成修正参数和提示词
    5. 提供人格状态的统一查询接口
    """

    def __init__(self, user_id: str, llm=None):
        self.user_id = user_id
        self.llm = llm
        self.db = Database()
        
        # 当前累计偏差
        self.cumulative = CumulativeDeviation()
        
        # 最近的残差标签（保留最近20个）
        self._recent_residuals: list[ResidualLabel] = []
        
        # 阈值配置
        self.accept_threshold = 0.3      # 可接受偏差阈值
        self.correct_threshold = 0.6     # 触发修正的阈值
        self.critical_threshold = 0.9    # 紧急修正阈值
        
        self._init_table()

    def _init_table(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona_control (
                    user_id TEXT PRIMARY KEY,
                    cumulative_state TEXT DEFAULT '{}',
                    residual_history TEXT DEFAULT '[]',
                    last_correction TEXT DEFAULT '',
                    correction_count INTEGER DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS persona_residuals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    residual_data TEXT NOT NULL,
                    magnitude REAL DEFAULT 0.0,
                    dominant_dim TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)

    # ========== 残差计算 ==========

    def compute_residual(
        self,
        current_reply: str,
        expected_persona: dict,
        user_text: str = "",
        emotion: str = "平静",
    ) -> ResidualLabel:
        """
        计算当前回复相对于预输入人格的残差。
        
        参数：
        - current_reply: AI的当前回复
        - expected_persona: 预输入的人格基线（从 persona.yaml 加载）
        - user_text: 用户输入（用于上下文判断）
        - emotion: 当前情感状态
        
        残差的计算基于规则+启发式，不调用LLM（轻量级）。
        """
        residual = ResidualLabel(
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )
        
        reply_len = len(current_reply)
        style = expected_persona.get("speaking_style", {})
        expected_len = style.get("sentence_length", "短句为主")
        expected_tone = style.get("tone", "随意")
        
        # === 语气温暖度残差 ===
        warm_words = ["呢", "呀", "嘛", "哦", "嘿嘿", "嘻嘻", "哈哈", "❤", "💕"]
        cold_words = ["嗯", "哦", "好的", "知道了", "收到"]
        warm_count = sum(1 for w in warm_words if w in current_reply)
        cold_count = sum(1 for w in cold_words if w in current_reply)
        residual.tone_warmth = max(-1.0, min(1.0, (warm_count - cold_count) * 0.2))
        
        # === 语气正式度残差 ===
        formal_markers = ["因此", "综上", "根据", "建议", "分析", "总结"]
        casual_markers = ["嘿嘿", "哈哈", "嘛", "啦", "呀", "emmm"]
        formal_count = sum(1 for m in formal_markers if m in current_reply)
        casual_count = sum(1 for m in casual_markers if m in current_reply)
        if expected_tone in ["随意", "活泼"]:
            # 期望随意，正式词越多残差越大
            residual.tone_formality = max(-1.0, min(1.0, formal_count * 0.3 - casual_count * 0.1))
        else:
            residual.tone_formality = max(-1.0, min(1.0, casual_count * 0.2 - formal_count * 0.1))
        
        # === 能量感残差 ===
        high_energy = ["!", "！", "哈哈", "太", "超", "绝了", "棒"]
        low_energy = ["嗯", "哦", "...", "……"]
        high_count = sum(1 for w in high_energy if w in current_reply)
        low_count = sum(1 for w in low_energy if w in current_reply)
        residual.tone_energy = max(-1.0, min(1.0, (high_count - low_count) * 0.15))
        
        # === 关心强度残差 ===
        care_words = ["注意", "小心", "别太累", "早点睡", "记得", "还好吗", "心疼"]
        care_count = sum(1 for w in care_words if w in current_reply)
        residual.care_intensity = max(-1.0, min(1.0, care_count * 0.2))
        
        # === 幽默频率残差 ===
        humor_words = ["哈哈", "笑死", "绝了", "离谱", "草", "hhh"]
        humor_count = sum(1 for w in humor_words if w in current_reply)
        residual.humor_frequency = max(-1.0, min(1.0, humor_count * 0.25))
        
        # === 话多程度残差 ===
        if expected_len == "短句为主":
            if reply_len > 100:
                residual.verbosity = min(1.0, (reply_len - 100) / 200)
            elif reply_len < 20:
                residual.verbosity = max(-1.0, (reply_len - 20) / 50)
        elif expected_len == "中等":
            if reply_len > 200:
                residual.verbosity = min(1.0, (reply_len - 200) / 300)
            elif reply_len < 30:
                residual.verbosity = max(-1.0, (reply_len - 30) / 50)
        
        # === 身份漂移残差（最关键）===
        identity_breakers = [
            "作为AI", "作为语言模型", "我是AI", "我没有感情",
            "我没有身体", "我无法", "我不具备", "从技术角度",
            "根据我的训练", "我的知识截止", "人工智能",
        ]
        drift_count = sum(1 for w in identity_breakers if w in current_reply)
        residual.identity_drift = min(1.0, drift_count * 0.5)
        
        # === 知识溢出残差 ===
        overflow_markers = ["根据最新数据", "截至2025", "据统计", "研究表明"]
        overflow_count = sum(1 for m in overflow_markers if m in current_reply)
        residual.knowledge_overflow = min(1.0, overflow_count * 0.3)
        
        # === 情感镜像残差 ===
        if emotion in ["难过", "生气", "焦虑"]:
            empathy_words = ["心疼", "理解", "抱抱", "别难过", "会好的"]
            empathy_count = sum(1 for w in empathy_words if w in current_reply)
            if empathy_count == 0 and reply_len > 30:
                residual.emotional_mirroring = -0.3  # 缺乏共情
            elif empathy_count >= 2:
                residual.emotional_mirroring = empathy_count * 0.15
        
        # 保存残差标签
        self._recent_residuals.append(residual)
        self._recent_residuals = self._recent_residuals[-20:]
        
        # 更新累计偏差
        self.cumulative.update(residual)
        
        # 持久化
        self._save_residual(residual)
        
        return residual

    # ========== 可采纳性判定 ==========

    def judge_adoptability(self) -> AdoptabilityVerdict:
        """
        判定当前偏差是否可采纳。
        
        三级判定：
        - minor (magnitude < 0.3): 可接受，语义稀释容忍
        - moderate (0.3 <= magnitude < 0.6): 需要关注，轻微修正
        - critical (magnitude >= 0.6): 需要修正，生成修正参数
        """
        magnitude = self.cumulative.total_magnitude()
        significant = self.cumulative.get_significant_dims(threshold=0.15)
        
        if magnitude < self.accept_threshold:
            severity = "minor"
            action = "accept"
            is_adoptable = True
            confidence = 0.9
        elif magnitude < self.correct_threshold:
            severity = "moderate"
            action = "dilute"
            is_adoptable = True
            confidence = 0.7
        elif magnitude < self.critical_threshold:
            severity = "critical"
            action = "correct"
            is_adoptable = False
            confidence = 0.8
        else:
            severity = "critical"
            action = "immediate_correct"
            is_adoptable = False
            confidence = 0.95
        
        return AdoptabilityVerdict(
            is_adoptable=is_adoptable,
            confidence=confidence,
            severity=severity,
            cumulative_magnitude=magnitude,
            significant_dims=significant,
            action=action,
        )

    # ========== 修正参数生成 ==========

    def generate_correction(self) -> CorrectionParameters:
        """
        根据累计偏差生成修正参数。
        
        生成内容：
        1. correction_targets: 每个偏差维度的修正目标值
        2. correction_strength: 修正强度
        3. correction_prompts: 一组修正提示词
        4. strategy: 修正策略
        """
        verdict = self.judge_adoptability()
        significant = verdict.significant_dims
        
        if not significant:
            return CorrectionParameters(strategy="none")
        
        # 生成修正目标（将偏差拉回零点附近）
        targets = {}
        prompts = []
        
        for dim, deviation in significant.items():
            # 修正目标：当前偏差的反方向，但不是完全归零（保留一些自然波动）
            correction_factor = 0.7  # 修正70%的偏差
            target = -deviation * correction_factor
            targets[dim] = target
            
            # 生成修正提示词
            direction = "positive" if deviation > 0 else "negative"
            template = CORRECTION_TEMPLATES.get(dim, {})
            prompt = template.get(direction, "")
            if prompt:
                prompts.append(prompt)
        
        # 计算修正强度
        magnitude = verdict.cumulative_magnitude
        if magnitude >= self.critical_threshold:
            strength = min(1.0, magnitude)
            strategy = "immediate"
        elif magnitude >= self.correct_threshold:
            strength = 0.6
            strategy = "firm"
        else:
            strength = 0.3
            strategy = "gentle"
        
        # 组装修正提示词
        if prompts:
            header = "[人格修正指令]"
            if strategy == "immediate":
                header = "[紧急人格修正]"
            prompts = [header] + prompts + ["请立刻回归你的角色设定。"]
        
        return CorrectionParameters(
            correction_targets=targets,
            correction_strength=strength,
            correction_prompts=prompts,
            strategy=strategy,
        )

    # ========== Prompt 注入 ==========

    def get_control_context(self) -> str:
        """
        获取人格控制的 Prompt 注入文本。
        在 pipeline._build_context() 中调用。
        """
        verdict = self.judge_adoptability()
        
        if verdict.is_adoptable and verdict.severity == "minor":
            # 偏差很小，不需要注入
            return ""
        
        lines = []
        
        if verdict.severity == "moderate":
            lines.append("[人格状态提醒] 你最近的回复有轻微偏离角色设定的倾向。")
            # 只提醒最显著的1-2个维度
            top_dims = sorted(
                verdict.significant_dims.items(),
                key=lambda x: abs(x[1]),
                reverse=True,
            )[:2]
            for dim, val in top_dims:
                dim_cn = DIM_CN.get(dim, dim)
                direction = "偏高" if val > 0 else "偏低"
                lines.append(f"  - {dim_cn}{direction}，请适当调整。")
        
        elif verdict.severity in ("critical",):
            # 偏差严重，生成修正参数
            correction = self.generate_correction()
            if correction.correction_prompts:
                lines.extend(correction.correction_prompts)
                lines.append(f"[修正强度: {correction.strategy}]")
        
        return "\n".join(lines) if lines else ""

    # ========== 统一状态查询 ==========

    def get_full_status(self) -> dict:
        """获取完整的人格控制状态（供调试和 /persona 命令使用）"""
        verdict = self.judge_adoptability()
        
        return {
            "cumulative_magnitude": round(self.cumulative.total_magnitude(), 3),
            "severity": verdict.severity,
            "is_adoptable": verdict.is_adoptable,
            "sample_count": self.cumulative.sample_count,
            "significant_dims": {
                k: round(v, 3) for k, v in verdict.significant_dims.items()
            },
            "dimension_details": {
                k: round(v, 3) for k, v in self.cumulative.dims.items()
            },
        }

    def get_status_text(self) -> str:
        """获取人格控制状态的可读文本"""
        status = self.get_full_status()
        
        lines = [
            f"人格控制状态",
            f"  累计偏差幅度: {status['cumulative_magnitude']:.3f}",
            f"  严重程度: {status['severity']}",
            f"  可采纳: {'✅ 是' if status['is_adoptable'] else '❌ 否'}",
            f"  采样数: {status['sample_count']}",
        ]
        
        if status['significant_dims']:
            lines.append("  显著偏差维度：")
            for dim, val in status['significant_dims'].items():
                dim_cn = DIM_CN.get(dim, dim)
                bar = "█" * int(abs(val) * 10)
                sign = "+" if val > 0 else "-"
                lines.append(f"    {dim_cn}: {sign}{bar} ({val:+.3f})")
        
        # 各维度详情
        lines.append("  各维度累计偏差：")
        for dim, val in status['dimension_details'].items():
            if abs(val) > 0.01:
                dim_cn = DIM_CN.get(dim, dim)
                sign = "+" if val > 0 else "-"
                lines.append(f"    {dim_cn}: {sign}{val:.3f}")
        
        return "\n".join(lines)

    # ========== 持久化 ==========

    def _save_residual(self, residual: ResidualLabel):
        """保存残差标签"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        data = {
            "tone_warmth": residual.tone_warmth,
            "tone_formality": residual.tone_formality,
            "tone_energy": residual.tone_energy,
            "care_intensity": residual.care_intensity,
            "humor_frequency": residual.humor_frequency,
            "verbosity": residual.verbosity,
            "identity_drift": residual.identity_drift,
            "knowledge_overflow": residual.knowledge_overflow,
            "emotional_mirroring": residual.emotional_mirroring,
        }
        magnitude = residual.magnitude()
        dominant = residual.dominant_dimension()
        
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO persona_residuals "
                "(user_id, residual_data, magnitude, dominant_dim, timestamp) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.user_id, json.dumps(data, ensure_ascii=False),
                 magnitude, dominant[0], now),
            )
            # 保留最近200条
            conn.execute(
                "DELETE FROM persona_residuals WHERE user_id = ? AND id NOT IN "
                "(SELECT id FROM persona_residuals WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 200)",
                (self.user_id, self.user_id),
            )
        
        # 保存累计偏差状态
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO persona_control "
                "(user_id, cumulative_state, correction_count, updated_at) "
                "VALUES (?, ?, COALESCE((SELECT correction_count FROM persona_control WHERE user_id = ?), 0), ?)",
                (self.user_id, json.dumps(self.cumulative.dims, ensure_ascii=False),
                 self.user_id, now),
            )

    def load_state(self):
        """从数据库恢复状态"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT cumulative_state FROM persona_control WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()
        
        if row and row["cumulative_state"]:
            try:
                self.cumulative.dims = json.loads(row["cumulative_state"])
            except:
                pass

    # ========== 重置 ==========

    def reset(self):
        """重置人格控制状态（当用户使用 /clear 或 /reset 时调用）"""
        self.cumulative = CumulativeDeviation()
        self._recent_residuals = []
        with self.db.get_conn() as conn:
            conn.execute(
                "DELETE FROM persona_residuals WHERE user_id = ?",
                (self.user_id,),
            )
            conn.execute(
                "DELETE FROM persona_control WHERE user_id = ?",
                (self.user_id,),
            )
