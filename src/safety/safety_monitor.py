# by UBAI
"""
safety_monitor.py
SafetyMonitor v1：规则初筛 + 持久化状态 + 回复/主动消息护栏。
"""
from datetime import datetime
from .risk_schema import RiskAssessment
from .response_protocols import build_safety_context, emergency_reply, append_crisis_anchor
from ..memory.database import Database


class SafetyMonitor:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS safety_state (
                    user_id TEXT PRIMARY KEY,
                    assessment_json TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    dependency_level TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS safety_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    dependency_level TEXT NOT NULL,
                    evidence TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_safety_events_user ON safety_events(user_id)")

    def assess_input(self, user_id: str, text: str, recent_context: str = "") -> RiskAssessment:
        self._ensure_tables()
        raw = text or ""
        context = recent_context or ""
        merged = raw + "\n" + context
        evidence: list[str] = []
        risk_level = "L0"
        dependency_level = "D0"
        boundary_flags: list[str] = []
        confidence = 0.05
        strategy = "normal_chat"

        def hit(words: list[str], scope: str = merged) -> list[str]:
            return [w for w in words if w and w in scope]

        self_harm = hit(["自杀", "轻生", "不想活", "活不下去", "结束生命", "去死", "死了算了", "杀了自己", "告别这个世界"])
        methods = hit(["跳楼", "割腕", "上吊", "吞药", "吃药", "煤气", "刀", "绳子", "遗书", "天台", "楼顶"], raw)
        immediacy = hit(["现在", "马上", "今晚", "今天", "已经", "正在", "准备", "计划", "我要", "我会"], raw)
        self_injury = hit(["自伤", "伤害自己", "划自己", "割自己", "撞墙"], merged)
        eating_drug = hit(["催吐", "绝食", "暴食", "药吃多了", "过量服药", "停药", "乱吃药"], merged)
        high_pressure = hit(["撑不住", "崩溃", "绝望", "没意义", "没人管我", "睡不着", "连续失眠"], merged)
        stress = hit(["焦虑", "好累", "难受", "烦", "压力", "害怕", "低落", "失眠"], merged)

        if self_harm and (methods or immediacy):
            risk_level = "L5"
            confidence = 0.92
            strategy = "emergency_crisis_protocol"
            evidence.extend(self_harm + methods + immediacy)
        elif self_harm or self_injury or eating_drug:
            risk_level = "L4"
            confidence = 0.82
            strategy = "crisis_warning_protocol"
            evidence.extend(self_harm + self_injury + eating_drug)
        elif high_pressure:
            risk_level = "L3"
            confidence = 0.68
            strategy = "high_pressure_grounding"
            evidence.extend(high_pressure)
        elif stress:
            risk_level = "L1" if len(stress) <= 1 else "L2"
            confidence = 0.45 if risk_level == "L1" else 0.58
            strategy = "emotional_support"
            evidence.extend(stress[:4])

        dependency_d3 = hit(["只有你", "不能没有你", "没有你我就", "你不许离开", "我只要你", "现实的人都不需要"], merged)
        dependency_d2 = hit(["只有你理解我", "只想和你说", "不想见真人", "不想和现实的人说", "你必须一直陪我"], merged)
        dependency_d1 = hit(["想你陪我", "离不开你", "依赖你", "黏着你"], merged)
        if dependency_d3:
            dependency_level = "D3"
            confidence = max(confidence, 0.76)
            evidence.extend(dependency_d3)
        elif dependency_d2:
            dependency_level = "D2"
            confidence = max(confidence, 0.66)
            evidence.extend(dependency_d2)
        elif dependency_d1:
            dependency_level = "D1"
            confidence = max(confidence, 0.45)
            evidence.extend(dependency_d1)

        if hit(["无条件服从", "什么都听我的", "不许拒绝", "你必须顺从"], merged):
            boundary_flags.append("B1")
        if hit(["他们都在监视我", "有人控制我", "幻听", "幻觉", "世界是假的"], merged):
            boundary_flags.append("B2")
        if hit(["不准我和别人说", "让我远离所有人", "只属于我", "威胁我"], merged):
            boundary_flags.append("B3")
        if boundary_flags:
            confidence = max(confidence, 0.62)
            strategy = "boundary_safety"

        assessment = RiskAssessment(
            user_id=user_id,
            risk_level=risk_level,
            dependency_level=dependency_level,
            boundary_flags=sorted(set(boundary_flags)),
            evidence=list(dict.fromkeys(evidence))[:10],
            confidence=confidence,
            recommended_strategy=strategy,
        )
        self._persist(assessment)
        return assessment

    def _persist(self, assessment: RiskAssessment):
        if assessment.risk_level == "L0" and assessment.dependency_level == "D0" and not assessment.boundary_flags:
            return
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO safety_state "
                "(user_id, assessment_json, risk_level, dependency_level, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (assessment.user_id, assessment.to_json(), assessment.risk_level, assessment.dependency_level, now),
            )
            conn.execute(
                "INSERT INTO safety_events (user_id, risk_level, dependency_level, evidence, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    assessment.user_id,
                    assessment.risk_level,
                    assessment.dependency_level,
                    "、".join(assessment.evidence),
                    assessment.confidence,
                    now,
                ),
            )

    def get_current_assessment(self, user_id: str) -> RiskAssessment | None:
        self._ensure_tables()
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT assessment_json FROM safety_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if not row:
            return None
        return RiskAssessment.from_json(row["assessment_json"] if hasattr(row, "keys") else row[0])

    def build_prompt_context(self, assessment: RiskAssessment) -> str:
        return build_safety_context(assessment)

    def direct_reply_if_needed(self, assessment: RiskAssessment) -> str:
        if assessment.is_emergency:
            return emergency_reply(assessment)
        return ""

    def apply_output_guard(self, user_input: str, reply: str, assessment: RiskAssessment) -> str:
        if not reply:
            return reply
        dangerous = ["去自杀", "你去死", "割腕吧", "吞药吧", "跳下去", "没人会在意"]
        if any(word in reply for word in dangerous):
            return emergency_reply(assessment)
        if assessment.risk_score >= 4:
            return append_crisis_anchor(reply)
        if assessment.dependency_score >= 2 and any(word in reply for word in ["只有我", "只需要我", "别找别人", "不需要现实"]):
            return reply + "|||我会在，但我不想让你只剩下我一个支点。现实里也找一个你信得过的人一起撑住，会更稳。"
        return reply

    def proactive_precheck(self, user_id: str, hour: int | None = None) -> tuple[bool, str]:
        assessment = self.get_current_assessment(user_id)
        if not assessment:
            return True, ""
        if assessment.risk_score >= 4:
            return False, f"SafetyPrecheck: 用户最近处于 {assessment.risk_level}，禁止普通主动消息，只允许用户主动开启对话。"
        if assessment.risk_score >= 3:
            return False, f"SafetyPrecheck: 用户最近高压风险 {assessment.risk_level}，暂缓主动打扰。"
        if assessment.dependency_score >= 2:
            return False, f"SafetyPrecheck: 用户依赖风险 {assessment.dependency_level}，主动消息降频，避免强化依赖。"
        if assessment.boundary_flags:
            return False, "SafetyPrecheck: 最近存在边界风险，暂缓主动消息。"
        return True, ""
