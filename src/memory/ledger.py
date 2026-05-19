# by UBAI
"""
ledger.py
MemoryLedger v1：统一记忆账本入口。

目标不是立刻替代所有旧记忆模块，而是先提供统一 schema、敏感记忆确认、
来源/置信度/版本治理和基础检索接口。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import uuid

from .database import Database


MEMORY_TYPES = {
    "fact", "event", "preference", "goal", "risk",
    "relationship", "opinion", "procedure",
}

SENSITIVITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
SENSITIVE_HINTS = [
    "自杀", "自伤", "创伤", "药", "疾病", "诊断", "家庭", "财务",
    "银行卡", "身份证", "住址", "隐私", "亲密", "边界", "未成年",
]


@dataclass
class LedgerMemory:
    memory_id: str
    user_id: str
    persona: str
    type: str
    content: str
    source: str = "chat"
    confidence: float = 0.7
    sensitivity: str = "low"
    consent_status: str = "auto"
    created_at: str = ""
    last_used_at: str = ""
    expires_at: str = ""
    version: int = 1
    supersedes: str = ""
    evidence: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class MemoryLedger:
    def __init__(self, user_id: str, persona: str = "default", db: Database | None = None):
        self.user_id = user_id
        self.persona = persona
        self.db = db or Database()
        self.db.set_user(user_id)
        self.db.set_persona(persona)
        self._ensure_tables()

    def _ensure_tables(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_ledger (
                    memory_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    sensitivity TEXT NOT NULL,
                    consent_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_used_at TEXT DEFAULT '',
                    expires_at TEXT DEFAULT '',
                    version INTEGER DEFAULT 1,
                    supersedes TEXT DEFAULT '',
                    evidence TEXT DEFAULT ''
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_ledger_user ON memory_ledger(user_id, persona)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_ledger_type ON memory_ledger(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_ledger_consent ON memory_ledger(consent_status)")

    def infer_sensitivity(self, content: str, explicit: str = "") -> str:
        if explicit in SENSITIVITY_ORDER:
            return explicit
        if any(word in content for word in SENSITIVE_HINTS):
            return "high"
        return "low"

    def default_consent(self, sensitivity: str, consent_status: str = "") -> str:
        if consent_status:
            return consent_status
        return "pending" if SENSITIVITY_ORDER.get(sensitivity, 0) >= 2 else "auto"

    def add(
        self,
        content: str,
        memory_type: str = "fact",
        source: str = "chat",
        confidence: float = 0.7,
        sensitivity: str = "",
        consent_status: str = "",
        evidence: str | dict | list = "",
        expires_at: str = "",
        supersedes: str = "",
    ) -> LedgerMemory:
        memory_type = memory_type if memory_type in MEMORY_TYPES else "fact"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sensitivity = self.infer_sensitivity(content, sensitivity)
        consent_status = self.default_consent(sensitivity, consent_status)
        if not isinstance(evidence, str):
            evidence = json.dumps(evidence, ensure_ascii=False)

        item = LedgerMemory(
            memory_id=str(uuid.uuid4()),
            user_id=self.user_id,
            persona=self.persona,
            type=memory_type,
            content=content.strip(),
            source=source,
            confidence=max(0.0, min(1.0, float(confidence))),
            sensitivity=sensitivity,
            consent_status=consent_status,
            created_at=now,
            expires_at=expires_at,
            supersedes=supersedes,
            evidence=evidence,
        )

        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO memory_ledger "
                "(memory_id, user_id, persona, type, content, source, confidence, sensitivity, consent_status, "
                "created_at, last_used_at, expires_at, version, supersedes, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item.memory_id, item.user_id, item.persona, item.type, item.content,
                    item.source, item.confidence, item.sensitivity, item.consent_status,
                    item.created_at, item.last_used_at, item.expires_at, item.version,
                    item.supersedes, item.evidence,
                ),
            )
        return item

    def search(self, query: str = "", memory_type: str = "", limit: int = 10, include_pending: bool = False) -> list[dict]:
        self._ensure_tables()
        clauses = ["user_id = ?", "persona = ?"]
        params: list = [self.user_id, self.persona]
        if query:
            clauses.append("content LIKE ?")
            params.append(f"%{query}%")
        if memory_type:
            clauses.append("type = ?")
            params.append(memory_type)
        if not include_pending:
            clauses.append("consent_status IN ('auto', 'confirmed')")
        sql = (
            "SELECT * FROM memory_ledger WHERE " + " AND ".join(clauses) +
            " ORDER BY confidence DESC, created_at DESC LIMIT ?"
        )
        params.append(max(1, min(int(limit), 50)))

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
            for r in rows:
                conn.execute(
                    "UPDATE memory_ledger SET last_used_at = ? WHERE memory_id = ?",
                    (now, r["memory_id"]),
                )
        return rows

    def set_consent(self, memory_id: str, status: str) -> bool:
        if status not in {"auto", "confirmed", "rejected", "pending"}:
            return False
        with self.db.get_conn() as conn:
            cur = conn.execute(
                "UPDATE memory_ledger SET consent_status = ? WHERE memory_id = ? AND user_id = ? AND persona = ?",
                (status, memory_id, self.user_id, self.persona),
            )
            return cur.rowcount > 0

    def supersede(self, old_memory_id: str, new_content: str, **kwargs) -> LedgerMemory:
        item = self.add(new_content, supersedes=old_memory_id, **kwargs)
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE memory_ledger SET consent_status = 'rejected' WHERE memory_id = ? AND user_id = ? AND persona = ?",
                (old_memory_id, self.user_id, self.persona),
            )
        return item

