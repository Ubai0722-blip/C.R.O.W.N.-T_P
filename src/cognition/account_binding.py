# by UBAI
"""
account_binding.py
账号配置绑定系统 - 面向聊天账号的关系配置绑定

核心功能：
1. 为每个聊天账号（如QQ号）绑定独立的关系配置
2. 支持关系类型、亲密度、称呼等配置
3. 与人设解耦，同一人设下不同账号可有不同关系配置
"""

import json
from datetime import datetime
from ..memory.database import Database


# 默认关系配置模板
DEFAULT_ACCOUNT_BINDING = {
    "relationship_type": "朋友",
    "intimacy_level": 50,
    "custom_name": "",
    "custom_honorific": "",
    "trust_level": 50,
    "interaction_style": "默认",
    "boundaries": {},
    "notes": "",
    "created_at": "",
    "updated_at": "",
}


class AccountBindingManager:
    """账号配置绑定管理器"""

    def __init__(self):
        self.db = Database()
        self._ensure_tables()

    def _ensure_tables(self):
        """确保表存在"""
        with self.db.get_psychology_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS account_bindings (
                    account_id TEXT NOT NULL,
                    persona_name TEXT NOT NULL,
                    relationship_type TEXT DEFAULT '朋友',
                    intimacy_level INTEGER DEFAULT 50,
                    custom_name TEXT DEFAULT '',
                    custom_honorific TEXT DEFAULT '',
                    trust_level INTEGER DEFAULT 50,
                    interaction_style TEXT DEFAULT '默认',
                    boundaries TEXT DEFAULT '{}',
                    notes TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (account_id, persona_name)
                )
            """)

    def _candidate_account_ids(self, account_id: str) -> list[str]:
        account_id = str(account_id or "").strip()
        if not account_id:
            return []
        candidates = [account_id]
        if account_id.startswith("qq_"):
            candidates.append(account_id[3:])
        elif account_id.isdigit():
            candidates.append("qq_" + account_id)
        return list(dict.fromkeys(candidates))

    def _canonical_account_id(self, account_id: str) -> str:
        account_id = str(account_id or "").strip()
        if account_id.isdigit():
            return "qq_" + account_id
        return account_id

    def _row_to_binding(self, row) -> dict:
        return {
            "account_id": row["account_id"],
            "persona_name": row["persona_name"],
            "relationship_type": row["relationship_type"],
            "intimacy_level": row["intimacy_level"],
            "custom_name": row["custom_name"],
            "custom_honorific": row["custom_honorific"],
            "trust_level": row["trust_level"],
            "interaction_style": row["interaction_style"],
            "boundaries": json.loads(row["boundaries"]) if row["boundaries"] else {},
            "notes": row["notes"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "_exists": True,
        }

    def get_binding(self, account_id: str, persona_name: str) -> dict:
        """获取指定账号与人设的绑定配置"""
        with self.db.get_psychology_conn() as conn:
            for candidate in self._candidate_account_ids(account_id):
                row = conn.execute(
                    "SELECT * FROM account_bindings WHERE account_id = ? AND persona_name = ?",
                    (candidate, persona_name)
                ).fetchone()
                if row:
                    return self._row_to_binding(row)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return {
                **DEFAULT_ACCOUNT_BINDING,
                "account_id": account_id,
                "persona_name": persona_name,
                "created_at": now,
                "updated_at": now,
                "_exists": False,
            }

    def save_binding(self, account_id: str, persona_name: str, data: dict):
        """保存账号绑定配置"""
        account_id = self._canonical_account_id(account_id)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_psychology_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM account_bindings WHERE account_id = ? AND persona_name = ?",
                (account_id, persona_name)
            ).fetchone()
            if row:
                conn.execute("""
                    UPDATE account_bindings SET
                        relationship_type = ?, intimacy_level = ?, custom_name = ?,
                        custom_honorific = ?, trust_level = ?, interaction_style = ?,
                        boundaries = ?, notes = ?, updated_at = ?
                    WHERE account_id = ? AND persona_name = ?
                """, (
                    data.get("relationship_type", "朋友"),
                    data.get("intimacy_level", 50),
                    data.get("custom_name", ""),
                    data.get("custom_honorific", ""),
                    data.get("trust_level", 50),
                    data.get("interaction_style", "默认"),
                    json.dumps(data.get("boundaries", {}), ensure_ascii=False),
                    data.get("notes", ""),
                    now,
                    account_id, persona_name
                ))
            else:
                conn.execute("""
                    INSERT INTO account_bindings
                    (account_id, persona_name, relationship_type, intimacy_level, custom_name,
                     custom_honorific, trust_level, interaction_style, boundaries, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    account_id, persona_name,
                    data.get("relationship_type", "朋友"),
                    data.get("intimacy_level", 50),
                    data.get("custom_name", ""),
                    data.get("custom_honorific", ""),
                    data.get("trust_level", 50),
                    data.get("interaction_style", "默认"),
                    json.dumps(data.get("boundaries", {}), ensure_ascii=False),
                    data.get("notes", ""),
                    now, now
                ))

    def get_account_bindings(self, account_id: str) -> list:
        """获取指定账号的所有人设绑定"""
        with self.db.get_psychology_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM account_bindings WHERE account_id = ?",
                (account_id,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_persona_bindings(self, persona_name: str) -> list:
        """获取指定人设的所有账号绑定"""
        with self.db.get_psychology_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM account_bindings WHERE persona_name = ?",
                (persona_name,)
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_binding(self, account_id: str, persona_name: str):
        """删除指定绑定"""
        with self.db.get_psychology_conn() as conn:
            for candidate in self._candidate_account_ids(account_id):
                conn.execute(
                    "DELETE FROM account_bindings WHERE account_id = ? AND persona_name = ?",
                    (candidate, persona_name)
                )

    def list_all_bindings(self) -> list:
        """列出所有绑定"""
        with self.db.get_psychology_conn() as conn:
            rows = conn.execute("SELECT * FROM account_bindings ORDER BY account_id, persona_name").fetchall()
            return [dict(r) for r in rows]
