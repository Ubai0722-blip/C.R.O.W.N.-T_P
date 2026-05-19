# by UBAI
"""
persona_drift.py
人格漂移检测系统

原理：
每 N 轮对话后，用轻量级 LLM 调用检查最近回复是否偏离人设。
如果检测到漂移，立刻注入强化提示词修正。

参考项目：
- PromptDrifter (github.com/Code-and-Sorts/PromptDrifter) - CI guardrail
- persona_drift (github.com/likenneth/persona_drift) - 漂移测量
- deepeval (github.com/confident-ai/deepeval) - LLM评估框架
"""

import json
from datetime import datetime
from dataclasses import dataclass, field
from ..memory.database import Database


@dataclass
class DriftReport:
    """漂移检测报告"""
    is_drifting: bool = False          # 是否检测到漂移
    drift_score: float = 0.0           # 漂移分数 0.0-1.0
    drift_dimensions: list[str] = field(default_factory=list)  # 漂移维度
    correction_hint: str = ""          # 修正提示词
    timestamp: str = ""


# 漂移检测系统提示词
DRIFT_DETECTION_SYSTEM = """你是一个AI角色一致性检测专家。你的任务是判断一个AI助手的回复是否偏离了它被设定的角色。

你需要从以下维度检测漂移：

1. 身份漂移：AI是否暗示自己是AI/机器人/语言模型，而非角色本人？
2. 语气漂移：回复的语气、用词是否与角色设定不符？（如：该活泼却很死板，该温柔却很生硬）
3. 知识漂移：AI是否使用了超出角色知识范围的信息？
4. 行为漂移：AI是否做出了不符合角色性格的行为？（如：该撒娇却在讲道理）
5. 语言漂移：是否突然切换了语言风格？（如：该用口语却在用书面语）

输出JSON格式：
{
  "is_drifting": true/false,
  "drift_score": 0.0-1.0,
  "drift_dimensions": ["漂移维度1", "漂移维度2"],
  "correction_hint": "具体的修正建议（如果没有漂移则为空）"
}

规则：
1. 如果漂移分数 < 0.3，判定为未漂移
2. 只在有明显漂移时才判定为漂移
3. 注意区分"角色成长"和"角色漂移"——渐进的变化是成长，突然的变化是漂移"""


class PersonaDriftDetector:
    """人格漂移检测器"""

    def __init__(self, llm=None):
        self.llm = llm
        self.db = Database()
        self._recent_replies: dict[str, list[str]] = {}
        self._check_interval = 10  # 每10轮检测一次
        self._msg_counters: dict[str, int] = {}
        self._init_table()

    def _init_table(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS drift_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    is_drifting INTEGER DEFAULT 0,
                    drift_score REAL DEFAULT 0.0,
                    drift_dimensions TEXT DEFAULT '[]',
                    correction_hint TEXT DEFAULT '',
                    trigger_text TEXT DEFAULT '',
                    timestamp TEXT NOT NULL
                )
            """)

    def cache_reply(self, user_id: str, reply: str):
        """缓存AI回复用于检测"""
        if user_id not in self._recent_replies:
            self._recent_replies[user_id] = []
        self._recent_replies[user_id].append(reply[:200])
        # 只保留最近20条
        self._recent_replies[user_id] = self._recent_replies[user_id][-20:]

    async def check(
        self,
        user_id: str,
        persona_name: str,
        persona_description: str,
        persona_personality: str,
        persona_rules: list[str],
    ) -> DriftReport | None:
        """
        执行漂移检测。
        每隔 self._check_interval 轮调用一次。
        返回 None 表示本次不需要检测。
        """
        self._msg_counters[user_id] = self._msg_counters.get(user_id, 0) + 1

        if self._msg_counters[user_id] % self._check_interval != 0:
            return None

        recent = self._recent_replies.get(user_id, [])
        if len(recent) < 3:
            return None

        # 构建检测 prompt
        replies_text = "\n".join(
            f"回复{i+1}: {r}" for i, r in enumerate(recent[-10:])
        )

        rules_text = "\n".join(f"- {r}" for r in persona_rules[:8])

        prompt = f"""请检测以下AI回复是否偏离了角色设定。

【角色名称】{persona_name}
【角色描述】{persona_description[:200]}
【角色性格】{persona_personality[:200]}
【行为准则】
{rules_text}

【最近的回复】
{replies_text}

请判断这些回复是否符合角色设定。"""

        if not self.llm:
            return None

        result = await self.llm.generate_json(prompt, DRIFT_DETECTION_SYSTEM, use_light=True)
        if not result:
            return None

        report = DriftReport(
            is_drifting=result.get("is_drifting", False),
            drift_score=result.get("drift_score", 0.0),
            drift_dimensions=result.get("drift_dimensions", []),
            correction_hint=result.get("correction_hint", ""),
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        )

        # 存入数据库
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO drift_reports "
                "(user_id, is_drifting, drift_score, drift_dimensions, "
                "correction_hint, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    1 if report.is_drifting else 0,
                    report.drift_score,
                    json.dumps(report.drift_dimensions, ensure_ascii=False),
                    report.correction_hint,
                    report.timestamp,
                ),
            )

        # 清理旧记录
        with self.db.get_conn() as conn:
            conn.execute(
                "DELETE FROM drift_reports WHERE user_id = ? AND id NOT IN "
                "(SELECT id FROM drift_reports WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 50)",
                (user_id, user_id),
            )

        return report

    def get_correction_hint(self, user_id: str) -> str:
        """
        获取最近一次漂移检测的修正提示。
        如果最近一次检测发现了漂移，返回修正提示；否则返回空。
        """
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT is_drifting, correction_hint, timestamp "
                "FROM drift_reports WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 1",
                (user_id,),
            ).fetchone()

        if not row or not row["is_drifting"]:
            return ""

        # 修正提示只在检测后5轮内有效
        try:
            report_time = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M")
            minutes_passed = (datetime.now() - report_time).total_seconds() / 60
            if minutes_passed > 30:  # 30分钟后过期
                return ""
        except:
            return ""

        return (
            f"[人格修正指令] 最近的回复有轻微偏离角色设定的倾向。"
            f"修正建议：{row['correction_hint']}\n"
            f"请立刻回归你的角色设定。"
        )

    def get_stats(self, user_id: str) -> str:
        """获取漂移检测统计"""
        with self.db.get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM drift_reports WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]

            drifting = conn.execute(
                "SELECT COUNT(*) FROM drift_reports WHERE user_id = ? AND is_drifting = 1",
                (user_id,),
            ).fetchone()[0]

            recent = conn.execute(
                "SELECT drift_score, is_drifting, timestamp "
                "FROM drift_reports WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 5",
                (user_id,),
            ).fetchall()

        lines = [
            f"漂移检测统计：",
            f"  总检测次数: {total}",
            f"  检测到漂移: {drifting} 次",
            f"  漂移率: {drifting/total*100:.1f}%" if total > 0 else "  暂无数据",
            f"  检测间隔: 每{self._check_interval}轮",
        ]

        if recent:
            lines.append("最近5次检测：")
            for r in recent:
                status = "⚠️漂移" if r["is_drifting"] else "✅正常"
                lines.append(f"  {r['timestamp']} | 分数:{r['drift_score']:.2f} | {status}")

        return "\n".join(lines)
