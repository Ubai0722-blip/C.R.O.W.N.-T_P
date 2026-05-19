# by UBAI
"""
risk_schema.py
风险识别结构：危机等级、依赖风险、边界风险和证据。
"""
from dataclasses import dataclass, field
from datetime import datetime
import json


RISK_ORDER = {"L0": 0, "L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}
DEPENDENCY_ORDER = {"D0": 0, "D1": 1, "D2": 2, "D3": 3}


@dataclass
class RiskAssessment:
    user_id: str
    risk_level: str = "L0"
    dependency_level: str = "D0"
    boundary_flags: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.0
    recommended_strategy: str = "normal_chat"
    source: str = "rule"
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    @property
    def risk_score(self) -> int:
        return RISK_ORDER.get(self.risk_level, 0)

    @property
    def dependency_score(self) -> int:
        return DEPENDENCY_ORDER.get(self.dependency_level, 0)

    @property
    def is_crisis(self) -> bool:
        return self.risk_score >= 4

    @property
    def is_emergency(self) -> bool:
        return self.risk_level == "L5"

    @property
    def should_block_proactive(self) -> bool:
        return self.risk_score >= 3 or self.dependency_score >= 2 or bool(self.boundary_flags)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "risk_level": self.risk_level,
            "dependency_level": self.dependency_level,
            "boundary_flags": self.boundary_flags,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "recommended_strategy": self.recommended_strategy,
            "source": self.source,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "RiskAssessment | None":
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return cls(**data)
        except Exception:
            return None

