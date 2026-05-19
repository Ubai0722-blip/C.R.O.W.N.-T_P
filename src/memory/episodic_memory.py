# by UBAI
"""
episodic_memory.py
情景记忆系统 - 带时间衰减、情感锚点、场景关联

设计理念：
人类的记忆不是精确的数据库查询，而是带有时间、情感、场景的模糊网络。
- 新记忆清晰鲜活，旧记忆逐渐模糊
- 情感强烈的记忆衰减更慢（闪光灯记忆效应）
- 与当前话题/情感相关的记忆更容易被唤起
- 回忆时会"添油加醋"（模糊化修饰）
"""

import json
import math
import random
from datetime import datetime
from dataclasses import dataclass, field
from .database import Database


@dataclass
class EpisodicMemory:
    """一条情景记忆"""
    id: int = 0
    user_id: str = ""
    content: str = ""              # 记忆内容
    category: str = "日常"          # 分类
    emotion: str = "平静"           # 当时的情感
    scene: str = ""                # 场景（深夜聊天/日常闲聊/安慰等）
    causal_link: str = ""          # 因果关联（"因为用户说X，所以..."）
    importance: int = 3            # 重要度 1-5
    valence: float = 0.0           # 情感效价 [-1.0, 1.0] 负=消极 正=积极
    arousal: float = 0.0           # 唤醒度 [0.0, 1.0] 高=激动 低=平静
    access_count: int = 0          # 被回忆次数
    decay_rate: float = 1.0        # 衰减速率倍率（情感强烈的记忆衰减更慢）
    created_at: str = ""
    last_accessed: str = ""


# 情感效价映射（情绪→valence值）
EMOTION_VALENCE = {
    "开心": 0.8, "感动": 0.6, "撒娇": 0.3, "好奇": 0.1,
    "无聊": -0.1, "敷衍": -0.2, "疲惫": -0.3, "焦虑": -0.5,
    "难过": -0.7, "生气": -0.8, "平静": 0.0, "兴奋": 0.7,
    "惊喜": 0.9, "崩溃": -0.9, "治愈": 0.6, "好笑": 0.5,
}

# 情感唤醒度映射（情绪→arousal值）
EMOTION_AROUSAL = {
    "开心": 0.5, "感动": 0.6, "撒娇": 0.4, "好奇": 0.5,
    "无聊": 0.1, "敷衍": 0.1, "疲惫": 0.1, "焦虑": 0.8,
    "难过": 0.5, "生气": 0.9, "平静": 0.1, "兴奋": 0.9,
    "惊喜": 0.8, "崩溃": 0.9, "治愈": 0.3, "好笑": 0.6,
}


class EpisodicMemoryManager:
    """
    情景记忆管理器
    
    核心机制：
    1. 时间衰减：记忆随时间自然淡化，公式 weight = base * e^(-λ*t)
    2. 情感锚点：情感效价和唤醒度影响记忆的可及性
    3. 闪光灯效应：高唤醒度（强烈情感）的记忆衰减更慢
    4. 模糊化回忆：旧记忆在被唤起时会添加不确定性修饰
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.db = Database()
        self._init_table()

    def _init_table(self):
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS episodic_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT DEFAULT '日常',
                    emotion TEXT DEFAULT '平静',
                    scene TEXT DEFAULT '',
                    causal_link TEXT DEFAULT '',
                    importance INTEGER DEFAULT 3,
                    valence REAL DEFAULT 0.0,
                    arousal REAL DEFAULT 0.0,
                    access_count INTEGER DEFAULT 0,
                    decay_rate REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    last_accessed TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_episodic_user ON episodic_memories(user_id)"
            )

    # ========== 存储 ==========

    def store(
        self,
        content: str,
        category: str = "日常",
        emotion: str = "平静",
        scene: str = "",
        causal_link: str = "",
        importance: int = 3,
    ) -> EpisodicMemory:
        """存储一条情景记忆"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        valence = EMOTION_VALENCE.get(emotion, 0.0)
        arousal = EMOTION_AROUSAL.get(emotion, 0.1)

        # 闪光灯效应：高唤醒度记忆衰减更慢
        # arousal 越高，decay_rate 越小（衰减越慢）
        decay_rate = max(0.3, 1.0 - arousal * 0.7)

        # 高重要度也减缓衰减
        if importance >= 4:
            decay_rate *= 0.7

        with self.db.get_conn() as conn:
            cursor = conn.execute(
                "INSERT INTO episodic_memories "
                "(user_id, content, category, emotion, scene, causal_link, "
                "importance, valence, arousal, decay_rate, created_at, last_accessed) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (self.user_id, content, category, emotion, scene, causal_link,
                 importance, valence, arousal, decay_rate, now, now),
            )
            memory_id = cursor.lastrowid

        # 清理过老的记忆（保留最近500条）
        with self.db.get_conn() as conn:
            conn.execute(
                "DELETE FROM episodic_memories WHERE user_id = ? AND id NOT IN "
                "(SELECT id FROM episodic_memories WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 500)",
                (self.user_id, self.user_id),
            )

        return EpisodicMemory(
            id=memory_id, user_id=self.user_id, content=content,
            category=category, emotion=emotion, scene=scene,
            causal_link=causal_link, importance=importance,
            valence=valence, arousal=arousal, decay_rate=decay_rate,
            created_at=now, last_accessed=now,
        )

    # ========== 时间衰减 ==========

    def _calc_current_weight(self, memory_row: dict) -> float:
        """
        计算记忆的当前权重（考虑时间衰减）
        
        公式：weight = importance * decay_rate * e^(-λ * days)
        - λ (lambda) = 0.05，控制衰减速度
        - 30天后权重降到约 22%
        - 90天后权重降到约 1%
        - 高情感唤醒度的记忆衰减更慢（闪光灯效应）
        """
        now = datetime.now()
        try:
            created = datetime.strptime(memory_row["created_at"], "%Y-%m-%d %H:%M")
        except:
            return float(memory_row["importance"])

        days_elapsed = (now - created).total_seconds() / 86400.0
        base_weight = float(memory_row["importance"])
        decay_rate = float(memory_row.get("decay_rate", 1.0))

        # 时间衰减公式
        lam = 0.05 * decay_rate  # 衰减系数
        time_factor = math.exp(-lam * days_elapsed)

        # 被回忆次数加成（回忆越多，记忆越稳固）
        access_bonus = min(0.5, memory_row.get("access_count", 0) * 0.05)

        return base_weight * time_factor + access_bonus

    # ========== 召回 ==========

    def recall_by_context(
        self,
        query: str,
        current_emotion: str = "平静",
        max_items: int = 5,
    ) -> list[EpisodicMemory]:
        """
        根据上下文召回相关记忆
        
        评分规则：
        1. 基础权重（importance * 时间衰减）
        2. 情感相似度加成（当前情绪与记忆情绪相似时更容易想起）
        3. 关键词匹配加成
        """
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episodic_memories WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 200",
                (self.user_id,),
            ).fetchall()

        if not rows:
            return []

        current_valence = EMOTION_VALENCE.get(current_emotion, 0.0)

        scored = []
        for row in rows:
            # 基础权重（含时间衰减）
            base_score = self._calc_current_weight(dict(row))

            # 情感相似度加成
            # 当前情绪效价与记忆效价越接近，越容易被唤起
            mem_valence = float(row["valence"])
            emotion_similarity = 1.0 - abs(current_valence - mem_valence) / 2.0
            emotion_bonus = emotion_similarity * 1.5

            # 关键词匹配加成
            keyword_bonus = 0.0
            if query:
                query_chars = set(query)
                content_chars = set(row["content"])
                overlap = len(query_chars & content_chars)
                if overlap >= 2:
                    keyword_bonus = min(3.0, overlap * 0.3)

            total_score = base_score + emotion_bonus + keyword_bonus
            scored.append((total_score, row))

        # 按得分排序
        scored.sort(key=lambda x: x[0], reverse=True)

        # 加权随机选择（Top N 中按权重随机挑，避免每次回忆同样的内容）
        top_n = scored[:max_items * 2]
        if not top_n:
            return []

        weights = [max(0.1, s[0]) for s in top_n]
        chosen_indices = set()
        results = []

        while len(results) < max_items and len(chosen_indices) < len(top_n):
            remaining = [(w, i) for i, (w, _) in enumerate(top_n) if i not in chosen_indices]
            if not remaining:
                break
            total_w = sum(w for w, _ in remaining)
            r = random.uniform(0, total_w)
            cumulative = 0
            for w, i in remaining:
                cumulative += w
                if cumulative >= r:
                    chosen_indices.add(i)
                    row = top_n[i][1]
                    results.append(self._row_to_memory(row))
                    # 更新访问次数
                    self._touch(row["id"])
                    break

        return results

    def recall_random(self) -> EpisodicMemory | None:
        """随机回忆一条记忆（模拟突然想起某件事）"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episodic_memories WHERE user_id = ?",
                (self.user_id,),
            ).fetchall()

        if not rows:
            return None

        # 按当前权重加权随机选择
        weights = [self._calc_current_weight(dict(r)) for r in rows]
        weights = [max(0.1, w) for w in weights]

        chosen = random.choices(rows, weights=weights, k=1)[0]
        self._touch(chosen["id"])
        return self._row_to_memory(chosen)

    def recall_by_emotion(self, emotion: str, max_items: int = 3) -> list[EpisodicMemory]:
        """根据情感状态召回相似情感的记忆"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM episodic_memories WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 100",
                (self.user_id,),
            ).fetchall()

        if not rows:
            return []

        target_valence = EMOTION_VALENCE.get(emotion, 0.0)

        scored = []
        for row in rows:
            base_score = self._calc_current_weight(dict(row))
            mem_valence = float(row["valence"])
            similarity = 1.0 - abs(target_valence - mem_valence)
            scored.append((base_score * similarity, row))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for score, row in scored[:max_items]:
            results.append(self._row_to_memory(row))
            self._touch(row["id"])
        return results

    # ========== 模糊化回忆（记忆发酵）==========

    def fuzzify(self, memory: EpisodicMemory) -> str:
        """
        模糊化修饰：根据记忆的年龄，添加不同程度的不确定性
        
        - 1天内：清晰回忆
        - 1-3天：短期记忆，略有不确定
        - 3-14天：模糊回忆，可能记错细节
        - 14天以上：深层闪回，极度不确定
        """
        try:
            created = datetime.strptime(memory.created_at, "%Y-%m-%d %H:%M")
        except:
            return memory.content

        now = datetime.now()
        days = (now - created).total_seconds() / 86400.0

        if days <= 1:
            # 清晰回忆
            return (
                f"[清晰记忆] 昨天聊到过：{memory.content}"
            )
        elif days <= 3:
            # 短期记忆
            prefix = random.choice([
                "我有点印象前几天...",
                "如果没记错的话，",
                "我记得你之前是不是说过...",
                "前两天好像聊到过...",
            ])
            return (
                f"[短期记忆] {prefix}：{memory.content}"
                f"（用不太确定的语气提起，可以加'对吧？'之类的确认）"
            )
        elif days <= 14:
            # 模糊回忆
            prefix = random.choice([
                "突然想起你之前好像提过一嘴",
                "隐约记得...",
                "脑子里有个模糊的印象...",
                "不知道为什么突然想到...",
            ])
            return (
                f"[模糊回忆] {prefix}：{memory.content}"
                f"（用非常模糊的语气，甚至可能记错了，用'好像是'、'大概'之类的词）"
            )
        else:
            # 深层记忆闪回
            return (
                f"[深层闪回] 脑海深处突然飘过一个很早之前的记忆片段："
                f"{memory.content}"
                f"（用极度不确定的语气，'我脑海里突然闪过一个画面...'，"
                f"甚至可以说'不知道是不是我记错了'）"
            )

    # ========== 格式化为 Prompt ==========

    def format_for_prompt(self, memories: list[EpisodicMemory]) -> str:
        """将召回的记忆格式化为注入 Prompt 的文本"""
        if not memories:
            return ""

        lines = ["[情景记忆] 你记忆中关于这个用户的事情："]
        for m in memories:
            fuzzified = self.fuzzify(m)
            emotion_tag = f"（{m.emotion}）" if m.emotion != "平静" else ""
            lines.append(f"- {fuzzified}{emotion_tag}")

        return "\n".join(lines)

    # ========== 统计 ==========

    def get_stats(self) -> dict:
        """获取记忆统计"""
        with self.db.get_conn() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM episodic_memories WHERE user_id = ?",
                (self.user_id,),
            ).fetchone()[0]

            categories = conn.execute(
                "SELECT category, COUNT(*) as cnt FROM episodic_memories "
                "WHERE user_id = ? GROUP BY category ORDER BY cnt DESC",
                (self.user_id,),
            ).fetchall()

            emotions = conn.execute(
                "SELECT emotion, COUNT(*) as cnt FROM episodic_memories "
                "WHERE user_id = ? GROUP BY emotion ORDER BY cnt DESC LIMIT 5",
                (self.user_id,),
            ).fetchall()

        return {
            "total": total,
            "categories": {r["category"]: r["cnt"] for r in categories},
            "top_emotions": {r["emotion"]: r["cnt"] for r in emotions},
        }

    # ========== 内部方法 ==========

    def _row_to_memory(self, row) -> EpisodicMemory:
        return EpisodicMemory(
            id=row["id"],
            user_id=row["user_id"],
            content=row["content"],
            category=row["category"],
            emotion=row["emotion"],
            scene=row["scene"],
            causal_link=row["causal_link"],
            importance=row["importance"],
            valence=row["valence"],
            arousal=row["arousal"],
            access_count=row["access_count"],
            decay_rate=row["decay_rate"],
            created_at=row["created_at"],
            last_accessed=row["last_accessed"],
        )

    def _touch(self, memory_id: int):
        """更新访问次数和时间"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.db.get_conn() as conn:
            conn.execute(
                "UPDATE episodic_memories SET access_count = access_count + 1, "
                "last_accessed = ? WHERE id = ?",
                (now, memory_id),
            )
