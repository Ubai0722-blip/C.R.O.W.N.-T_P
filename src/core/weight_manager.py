# by UBAI
"""
weight_manager.py
词汇权重管理 - 支持自动学习、衰减、Prompt注入
"""
import re
from datetime import datetime, timedelta
from ..memory.database import Database


class WeightManager:
    """词汇权重管理器"""

    def __init__(self):
        self.db = Database()
        self._init_table()
        self.learn_step = 0.3       # 每次提到加多少
        self.max_weight = 10.0      # 权重上限
        self.min_weight = 0.1       # 权重下限
        self.decay_rate = 0.05      # 每天衰减多少
        self.decay_days = 7         # 超过多少天没提到开始衰减
        self.prompt_top_n = 10      # Prompt 注入前 N 个高权重词

    def _init_table(self):
        """初始化权重表"""
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS word_weights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    word TEXT NOT NULL UNIQUE,
                    weight REAL DEFAULT 1.0,
                    category TEXT DEFAULT '默认',
                    hit_count INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT
                )
            """)
            # 给旧表加列（兼容已有数据）
            for col_def in [
                "ALTER TABLE word_weights ADD COLUMN hit_count INTEGER DEFAULT 0",
                "ALTER TABLE word_weights ADD COLUMN created_at TEXT DEFAULT ''",
            ]:
                try:
                    conn.execute(col_def)
                except Exception:
                    pass  # 列已存在

    # ========== 基础 CRUD（保留原有功能）==========

    def get_all(self, category=""):
        with self.db.get_conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT word, weight, category, hit_count FROM word_weights WHERE category = ? ORDER BY weight DESC",
                    (category,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT word, weight, category, hit_count FROM word_weights ORDER BY weight DESC"
                ).fetchall()
        return [{"word": r["word"], "weight": r["weight"], "category": r["category"], "hit_count": r["hit_count"]} for r in rows]

    def get_weight(self, word):
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT weight FROM word_weights WHERE word = ?", (word,)
            ).fetchone()
        return row["weight"] if row else 1.0

    def set_weight(self, word, weight, category="默认"):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            with self.db.get_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO word_weights "
                    "(word, weight, category, hit_count, created_at, updated_at) "
                    "VALUES (?, ?, ?, "
                    "COALESCE((SELECT hit_count FROM word_weights WHERE word = ?), 0), "
                    "COALESCE((SELECT created_at FROM word_weights WHERE word = ?), ?), ?)",
                    (word, weight, category, word, word, now, now),
                )
            return True
        except Exception:
            return False

    def delete(self, word):
        with self.db.get_conn() as conn:
            cursor = conn.execute("DELETE FROM word_weights WHERE word = ?", (word,))
        return cursor.rowcount > 0

    def search(self, keyword):
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT word, weight, category, hit_count FROM word_weights WHERE word LIKE ? ORDER BY weight DESC",
                (f"%{keyword}%",),
            ).fetchall()
        return [{"word": r["word"], "weight": r["weight"], "category": r["category"], "hit_count": r["hit_count"]} for r in rows]

    def get_chart(self, top_n=15):
        items = self.get_all()[:top_n]
        if not items:
            return "暂无权重数据"
        max_weight = max(i["weight"] for i in items)
        lines = ["词 权重排名：\n"]
        for i, item in enumerate(items, 1):
            bar_len = int((item["weight"] / max_weight) * 20)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"{i:2d}. {item['word']:<8s} {bar} {item['weight']:.1f} (命中{item['hit_count']}次)")
        return "\n".join(lines)

    def get_category_stats(self):
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) as count, AVG(weight) as avg_weight "
                "FROM word_weights GROUP BY category ORDER BY count DESC"
            ).fetchall()
        if not rows:
            return "暂无数据"
        lines = ["分类统计：\n"]
        for r in rows:
            lines.append(f"  {r['category']}: {r['count']}个词条，平均权重 {r['avg_weight']:.2f}")
        return "\n".join(lines)

    # ========== 新增：自动学习 ==========

    def learn_from_text(self, text):
        """从用户消息中提取关键词并自动加权"""
        keywords = self._extract_keywords(text)
        if not keywords:
            return

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            for word in keywords:
                existing = conn.execute(
                    "SELECT weight, hit_count FROM word_weights WHERE word = ?", (word,)
                ).fetchone()

                if existing:
                    # 已存在：加权 + 命中次数+1
                    new_weight = min(existing["weight"] + self.learn_step, self.max_weight)
                    new_count = existing["hit_count"] + 1
                    conn.execute(
                        "UPDATE word_weights SET weight = ?, hit_count = ?, updated_at = ? WHERE word = ?",
                        (new_weight, new_count, now, word),
                    )
                else:
                    # 新词：创建，默认权重 1.0
                    conn.execute(
                        "INSERT INTO word_weights (word, weight, category, hit_count, created_at, updated_at) "
                        "VALUES (?, 1.0, '自动', 1, ?, ?)",
                        (word, now, now),
                    )

    def _extract_keywords(self, text):
        """从文本中提取有意义的关键词"""
        # 去掉标点和常见语气词
        stop_words = {
            '的', '了', '是', '在', '我', '你', '他', '她', '它',
            '吗', '吧', '呢', '啊', '哦', '嗯', '呀', '哈',
            '就', '都', '也', '还', '又', '才', '很', '太',
            '和', '与', '或', '但', '而', '所以', '因为',
            '这', '那', '这个', '那个', '什么', '怎么',
            '可以', '应该', '想要', '没有', '不是', '知道',
            '觉得', '感觉', '今天', '明天', '昨天',
            '一个', '一些', '真的', '其实', '然后',
        }

        # 提取中文词（2-6个字的连续中文）
        words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)

        # 过滤停用词和太短的词
        keywords = [w for w in words if w not in stop_words and len(w) >= 2]

        # 去重保序
        seen = set()
        result = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                result.append(w)

        return result[:15]  # 最多取15个词

    # ========== 新增：自动衰减 ==========

    def decay_weights(self):
        """衰减长期未提到的词汇权重"""
        cutoff = (datetime.now() - timedelta(days=self.decay_days)).strftime("%Y-%m-%d %H:%M:%S")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_conn() as conn:
            # 找到超过 decay_days 天没更新的词
            rows = conn.execute(
                "SELECT word, weight FROM word_weights WHERE updated_at < ? AND category = '自动'",
                (cutoff,),
            ).fetchall()

            decayed = []
            for r in rows:
                new_weight = max(r["weight"] - self.decay_rate, self.min_weight)
                if new_weight <= self.min_weight:
                    # 权重降到最低，直接删除
                    conn.execute("DELETE FROM word_weights WHERE word = ?", (r["word"],))
                    decayed.append(f"{r['word']}(已删除)")
                else:
                    conn.execute(
                        "UPDATE word_weights SET weight = ?, updated_at = ? WHERE word = ?",
                        (new_weight, now, r["word"]),
                    )
                    decayed.append(f"{r['word']}({r['weight']:.1f}->{new_weight:.1f})")

        return decayed

    # ========== 新增：Prompt 注入 ==========

    def get_prompt_text(self):
        """获取高权重词，用于注入 Prompt"""
        items = self.get_all()[:self.prompt_top_n]
        if not items:
            return ""

        lines = []
        for item in items:
            if item["weight"] >= 2.0:
                lines.append(f"「{item['word']}」(权重{item['weight']:.1f})")

        if not lines:
            return ""

        return (
            "用户关注的高频话题/词汇（回复时可以自然地融入这些话题）：\n"
            + "、".join(lines)
        )
