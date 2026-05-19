# by UBAI
"""
long_memory.py
长期记忆系统 - 数据库版
"""
import json
import re
from datetime import datetime
from dataclasses import dataclass

from src.utils.paths import DEBUG_LOG

def dlog(msg):
    with open(DEBUG_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

from .database import Database
from ..core.llm import LLMClient


@dataclass
class Memory:
    id: int
    user_id: str
    category: str
    content: str
    importance: int
    access_count: int
    created_at: str
    last_accessed: str


class LongTermMemory:
    """长期记忆管理器 - 数据库版"""

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = Database()
        self._pending_texts: list[str] = [] 

    def extract_and_store(self, text: str):
        """规则预筛选（轻量，每次调用）"""
        if len(text) < 8:
            return
        self._pending_texts.append(text)

    async def ai_extract_and_store(self, llm):
        """每40条消息用AI判断是否需要记录记忆"""
        if not self._pending_texts:
            return

        recent = self._pending_texts[-20:]
        self._pending_texts = []

        msgs_text = "\n".join(f"- {t[:80]}" for t in recent)
        if not msgs_text.strip():
            return

        prompt = (
            "以下是用户最近的发言。请判断哪些内容值得作为长期记忆保存。\n"
            "只输出值得记住的信息，每行一条。\n"
            "值得记住的：个人信息、兴趣爱好、重要经历、计划、情感事件、习惯\n"
            "不值得记住的：日常闲聊、重复信息、无意义的话、已经知道的信息\n\n"
            f"{msgs_text}\n\n"
            "如果没有任何值得记住的，只输出：无\n"
            "否则每行一条，格式：分类|内容\n"
            "分类：个人信息/兴趣爱好/工作学习/人际关系/习惯/经历/情绪/计划\n\n"
            "示例：\n个人信息|用户名字叫小明\n计划|下周三有考试\n\n"
            "你的输出："
        )

        try:
            messages = [{"role": "user", "content": prompt}]
            result = await llm.chat_light(messages)

            if not result or "无" in result.strip()[:5]:
                return

            for line in result.strip().split("\n"):
                line = line.strip()
                if "|" not in line or not line:
                    continue
                parts = line.split("|", 1)
                if len(parts) == 2:
                    category = parts[0].strip()
                    content = parts[1].strip()
                    if content and len(content) >= 5:
                        importance = self._calc_importance(content, category)
                        self._store(category, content, importance)
                        dlog(f"[memory] AI记录: [{category}] {content[:40]}")

        except Exception as e:
            dlog(f"[memory ai extract err] {e}")


    def _calc_importance(self, text: str, category: str) -> int:
        importance = 1
        if category in ["个人信息", "宠物", "人际关系"]:
            importance += 2
        if any(kw in text for kw in ["很", "非常", "特别", "最"]):
            importance += 1
        if len(text) > 30:
            importance += 1
        return min(importance, 5)

    def _store(self, category: str, content: str, importance: int):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.db.get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM long_term_memory "
                "WHERE user_id = ? AND category = ? AND content = ?",
                (self.user_id, category, content),
            ).fetchone()

            if existing:
                conn.execute(
                    "UPDATE long_term_memory SET access_count = access_count + 1, "
                    "last_accessed = ? WHERE id = ?",
                    (now, existing["id"]),
                )
            else:
                conn.execute(
                    "INSERT INTO long_term_memory "
                    "(user_id, category, content, importance, access_count, created_at, last_accessed) "
                    "VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (self.user_id, category, content, importance, now, now),
                )

    def get_context_text(self, text: str) -> str:
        """获取与当前话题相关的长期记忆上下文"""
        memories = self.recall(text, max_items=5)
        if not memories:
            return ""

        lines = ["[长期记忆] 关于这个用户你记住的事情："]
        for m in memories:
            lines.append(f"- [{m.category}] {m.content}")
        return "\n".join(lines)

    def recall(self, query: str, max_items: int = 5) -> list[Memory]:
        """根据查询召回相关记忆"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, user_id, category, content, importance, "
                "access_count, created_at, last_accessed "
                "FROM long_term_memory WHERE user_id = ? "
                "ORDER BY importance DESC, access_count DESC",
                (self.user_id,),
            ).fetchall()

        if not rows:
            return []

        scored = []
        for row in rows:
            score = float(row["importance"])

            # 关键词匹配加分
            query_lower = query.lower()
            content_lower = row["content"].lower()
            for word in query_lower.split():
                if len(word) >= 2 and word in content_lower:
                    score += 2

            # 高重要度记忆始终保留
            if score >= 2:
                scored.append((
                    score,
                    Memory(
                        id=row["id"],
                        user_id=row["user_id"],
                        category=row["category"],
                        content=row["content"],
                        importance=row["importance"],
                        access_count=row["access_count"],
                        created_at=row["created_at"],
                        last_accessed=row["last_accessed"],
                    ),
                ))

        scored.sort(key=lambda x: x[0], reverse=True)
        recalled = [m[1] for m in scored[:max_items]]

        # 更新访问次数
        if recalled:
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            with self.db.get_conn() as conn:
                for m in recalled:
                    conn.execute(
                        "UPDATE long_term_memory SET access_count = access_count + 1, "
                        "last_accessed = ? WHERE id = ?",
                        (now, m.id),
                    )

        return recalled

    def get_all_memories(self) -> list[Memory]:
        """获取所有记忆"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, user_id, category, content, importance, "
                "access_count, created_at, last_accessed "
                "FROM long_term_memory WHERE user_id = ? "
                "ORDER BY importance DESC, created_at DESC",
                (self.user_id,),
            ).fetchall()

        return [
            Memory(
                id=row["id"],
                user_id=row["user_id"],
                category=row["category"],
                content=row["content"],
                importance=row["importance"],
                access_count=row["access_count"],
                created_at=row["created_at"],
                last_accessed=row["last_accessed"],
            )
            for row in rows
        ]

    def forget(self, keyword: str) -> bool:
        """删除包含关键词的记忆"""
        # 转义 SQL LIKE 通配符
        safe_keyword = keyword.replace('%', '\\%').replace('_', '\\_')
        with self.db.get_conn() as conn:
            result = conn.execute(
                "DELETE FROM long_term_memory "
                "WHERE user_id = ? AND content LIKE ?",
                (self.user_id, f"%{safe_keyword}%"),
            )
            return result.rowcount > 0
    def get_random_recall(self):
        """随机回忆一条记忆（模拟真人突然想起某件事）"""
        import random
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT category, content, importance FROM long_term_memory "
                "WHERE user_id = ?",
                (self.user_id,),
            ).fetchall()

        if not rows:
            return None

        # 重要度越高的记忆越容易被想起
        weights = [float(r["importance"]) for r in rows]
        chosen = random.choices(rows, weights=weights, k=1)[0]
        return f"[{chosen['category']}] {chosen['content']}"

    def get_related_recall(self, query):
        """根据当前话题回忆相关记忆"""
        import random
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT category, content, importance FROM long_term_memory "
                "WHERE user_id = ?",
                (self.user_id,),
            ).fetchall()

        if not rows:
            return None

        # 关键词匹配
        query_chars = set(query)
        scored = []
        for r in rows:
            content_chars = set(r["content"])
            overlap = len(query_chars & content_chars)
            if overlap >= 2:
                scored.append((overlap + r["importance"], r))

        if not scored:
            return None

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:3]
        weights = [s[0] for s in top]
        chosen = random.choices([s[1] for s in top], weights=weights, k=1)[0]
        return f"[{chosen['category']}] {chosen['content']}"
