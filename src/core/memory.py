# by UBAI
"""
memory.py
滑动窗口记忆 - 支持数据库持久化
"""
from dataclasses import dataclass, field
from datetime import datetime
from .database import Database


@dataclass
class Message:
    role: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)


class BufferMemory:
    """滑动窗口记忆：保留最近 N 轮对话，持久化到数据库"""

    def __init__(self, user_id: str, max_turns: int = 12):
        self.user_id = user_id
        self.max_turns = max_turns
        self.messages: list[Message] = []
        self.db = Database(user_id=self.user_id)
        self._ensure_table()
        self._load()

    def _ensure_table(self):
        """确保表存在"""
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    user_msg TEXT NOT NULL,
                    ai_reply TEXT NOT NULL,
                    emotion TEXT DEFAULT '平静'
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_hist_user ON chat_history(user_id)"
            )

    def _load(self):
        """从数据库加载历史"""
        try:
            with self.db.get_conn() as conn:
                rows = conn.execute(
                    "SELECT user_msg, ai_reply FROM chat_history "
                    "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
                    (self.user_id, self.max_turns),
                ).fetchall()
            for row in reversed(rows):
                self.messages.append(Message(role="user", content=row["user_msg"]))
                self.messages.append(Message(role="assistant", content=row["ai_reply"]))
        except Exception:
            pass

    def add(self, user_msg: str, assistant_msg: str) -> None:
        """添加一轮对话，先写数据库再更新内存"""
        # 持久化（先写DB）
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self.db.get_conn() as conn:
                conn.execute(
                    "INSERT INTO chat_history (user_id, timestamp, user_msg, ai_reply) "
                    "VALUES (?, ?, ?, ?)",
                    (self.user_id, now, user_msg[:500], assistant_msg[:500]),
                )
                # 清理旧记录
                conn.execute(
                    "DELETE FROM chat_history WHERE user_id = ? AND id NOT IN "
                    "(SELECT id FROM chat_history WHERE user_id = ? ORDER BY id DESC LIMIT 500)",
                    (self.user_id, self.user_id),
                )
        except Exception:
            pass

        # DB 写入成功后再更新内存
        self.messages.append(Message(role="user", content=user_msg))
        self.messages.append(Message(role="assistant", content=assistant_msg))
        max_count = self.max_turns * 2
        if len(self.messages) > max_count:
            self.messages = self.messages[-max_count:]

    def get_context(self) -> list[dict]:
        """获取历史消息，格式为 API 需要的 dict 列表"""
        return [{"role": m.role, "content": m.content} for m in self.messages]

    def get_context_text(self) -> str:
        """获取历史消息的纯文本版本"""
        if not self.messages:
            return ""
        lines = ["[最近对话记录]"]
        for m in self.messages[-10:]:
            role = "用户" if m.role == "user" else "你"
            lines.append(f"  {role}: {m.content[:80]}")
        return "\n".join(lines)

    def clear(self) -> None:
        """清空所有历史"""
        self.messages.clear()
        try:
            with self.db.get_conn() as conn:
                conn.execute(
                    "DELETE FROM chat_history WHERE user_id = ?",
                    (self.user_id,),
                )
        except Exception:
            pass
