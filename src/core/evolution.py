# by UBAI
"""
evolution.py
进化引擎 - 让生活、人设、成长三个模块在对话中自动完善
"""
import json
from datetime import datetime
from ..memory.database import Database


# 话题分类（与 growth.py 一致）
TOPIC_KEYWORDS = {
    "画画": ["画画", "画", "插画", "绘图", "板绘", "手绘", "上色", "线稿"],
    "游戏": ["游戏", "明日方舟", "方舟", "抽卡", "关卡", "活动", "干员"],
    "音乐": ["歌", "音乐", "听歌", "乐队", "专辑", "演唱会"],
    "美食": ["吃", "喝", "饭", "咖啡", "奶茶", "餐厅", "外卖", "做饭"],
    "旅行": ["旅游", "旅行", "出去玩", "景点", "酒店"],
    "工作": ["工作", "上班", "加班", "甲方", "稿子", "接稿", "收入"],
    "学习": ["学习", "考试", "考研", "上课", "作业", "毕业"],
    "宠物": ["猫", "狗", "宠物", "小卡"],
    "心情": ["心情", "开心", "难过", "累", "烦", "焦虑", "无聊"],
    "日常": ["今天", "昨天", "明天", "刚才", "晚上", "早上"],
    "感情": ["恋爱", "喜欢", "对象", "男朋友", "女朋友"],
    "书影": ["电影", "剧", "动漫", "番", "书", "小说", "阅读"],
}


class EvolutionEngine:
    """
    进化引擎。
    跟踪对话数据，分析模式，自动调整生活事件权重和人设行为。
    """

    def __init__(self):
        self.db = Database()
        self._evolve_interval = 50  # 每50次对话进化一次

    # ========== 记录对话 ==========

    def log_conversation(
        self,
        user_id: str,
        user_text: str,
        ai_reply: str,
        emotion: str = "平静",
        event_type: str = "日常问候",
    ):
        """记录一次对话的元数据"""
        # 提取话题
        topic = self._extract_topic(user_text)

        # 计算参与度分数
        engagement = self._calc_engagement(user_text, ai_reply)

        # 是否包含问号
        has_question = 1 if ("?" in user_text or "？" in user_text) else 0

        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO conversation_log "
                "(user_id, timestamp, topic, emotion, user_msg_length, "
                "ai_msg_length, engagement_score, event_type, has_question) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id, now, topic, emotion,
                    len(user_text), len(ai_reply),
                    engagement, event_type, has_question,
                ),
            )

        # 检查是否需要进化
        self._check_evolve(user_id)

    def _extract_topic(self, text: str) -> str:
        """提取对话话题"""
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    return topic
        return "日常"

    def _calc_engagement(self, user_text: str, ai_reply: str) -> float:
        """
        计算用户参与度分数（0-10）。
        分数越高说明用户越投入。
        """
        score = 3.0  # 基础分

        # 用户消息长度（越长越投入）
        if len(user_text) > 100:
            score += 2.0
        elif len(user_text) > 50:
            score += 1.5
        elif len(user_text) > 20:
            score += 1.0
        elif len(user_text) < 5:
            score -= 1.0

        # 用户是否提问（提问说明在深入交流）
        if "?" in user_text or "？" in user_text:
            score += 1.0

        # 用户是否表达情感
        emotion_words = ["哈哈", "呜呜", "好", "太", "真的", "确实", "嗯嗯"]
        if any(w in user_text for w in emotion_words):
            score += 0.5

        # 用户是否引用上文（说明在认真对话）
        ref_words = ["那", "刚才", "之前", "你说的", "那个"]
        if any(w in user_text for w in ref_words):
            score += 0.5

        return min(10.0, max(0.0, score))

    # ========== 进化分析 ==========

    def _check_evolve(self, user_id: str):
        """检查是否需要执行进化分析"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM evolution_state "
                "WHERE user_id = ? AND key = 'conversation_count'",
                (user_id,),
            ).fetchone()

            count = int(row["value"]) + 1 if row else 1

            conn.execute(
                "INSERT INTO evolution_state (user_id, key, value, updated_at) "
                "VALUES (?, 'conversation_count', ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = ?, updated_at = ?",
                (user_id, str(count),
                 datetime.now().strftime("%Y-%m-%d %H:%M"),
                 str(count),
                 datetime.now().strftime("%Y-%m-%d %H:%M")),
            )

        if count % self._evolve_interval == 0:
            self._evolve(user_id)

    def _evolve(self, user_id: str):
        """执行进化分析"""
        with self.db.get_conn() as conn:
            # 取最近50条对话记录
            rows = conn.execute(
                "SELECT topic, emotion, engagement_score, event_type, has_question, ai_msg_length "
                "FROM conversation_log WHERE user_id = ? "
                "ORDER BY id DESC LIMIT 50",
                (user_id,),
            ).fetchall()

        if len(rows) < 5:
            return

        # 1. 分析话题参与度
        topic_scores = {}
        for row in rows:
            topic = row["topic"] or "日常"
            engagement = row["engagement_score"] or 3.0
            if topic not in topic_scores:
                topic_scores[topic] = []
            topic_scores[topic].append(engagement)

        topic_avg = {}
        for topic, scores in topic_scores.items():
            topic_avg[topic] = sum(scores) / len(scores)

        # 2. 分析回复风格效果
        style_data = {"short": [], "medium": [], "long": []}
        for row in rows:
            ai_len = row["ai_msg_length"] or 0
            engagement = row["engagement_score"] or 3.0
            if ai_len < 30:
                style_data["short"].append(engagement)
            elif ai_len < 80:
                style_data["medium"].append(engagement)
            else:
                style_data["long"].append(engagement)

        style_scores = {}
        for style, scores in style_data.items():
            if scores:
                style_scores[style] = sum(scores) / len(scores)

        # 3. 分析情绪模式
        emotion_counts = {}
        for row in rows:
            emotion = row["emotion"] or "平静"
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + 1

        # 4. 分析提问频率
        question_rate = sum(1 for r in rows if r["has_question"]) / len(rows)

        # 5. 保存进化结果
        evolution_data = {
            "topic_scores": topic_avg,
            "style_scores": style_scores,
            "emotion_pattern": emotion_counts,
            "question_rate": round(question_rate, 2),
            "total_analyzed": len(rows),
        }

        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO evolution_state (user_id, key, value, updated_at) "
                "VALUES (?, 'evolution_data', ?, ?) "
                "ON CONFLICT(user_id, key) DO UPDATE SET value = ?, updated_at = ?",
                (user_id, json.dumps(evolution_data, ensure_ascii=False),
                 now, json.dumps(evolution_data, ensure_ascii=False), now),
            )

    # ========== 获取进化结果 ==========

    def get_life_weights(self, user_id: str) -> dict[str, float]:
        """
        获取生活事件的权重调整。
        用户参与度高的话题，对应的事件权重更高。
        """
        data = self._get_evolution_data(user_id)
        if not data:
            return {}

        topic_scores = data.get("topic_scores", {})

        # 生活事件分类到话题的映射
        life_to_topic = {
            "画画": "画画",
            "游戏": "游戏",
            "小卡": "宠物",
            "日常": "日常",
            "心情": "心情",
            "饮食": "美食",
            "旅游": "旅行",
            "听歌": "音乐",
            "看书": "书影",
            "挚友日常": "日常",
        }

        weights = {}
        for life_cat, topic in life_to_topic.items():
            if topic in topic_scores:
                # 参与度越高权重越大，最低0.5，最高3.0
                avg = topic_scores[topic]
                weight = max(0.5, min(3.0, avg / 3.0))
                weights[life_cat] = weight

        return weights

    def get_persona_adaptation(self, user_id: str) -> str:
        """
        获取人设适应性调整提示。
        根据对话分析结果，告诉 AI 应该怎么调整风格。
        """
        data = self._get_evolution_data(user_id)
        if not data:
            return ""

        lines = []
        style_scores = data.get("style_scores", {})
        topic_scores = data.get("topic_scores", {})
        question_rate = data.get("question_rate", 0)

        # 回复风格建议
        if style_scores:
            best_style = max(style_scores, key=style_scores.get)
            style_hints = {
                "short": "用户更喜欢简短直接的回复，少说废话",
                "medium": "用户喜欢适中长度的回复，既有内容又不啰嗦",
                "long": "用户不介意较长的回复，可以详细展开聊",
            }
            lines.append(style_hints.get(best_style, ""))

        # 话题偏好
        if topic_scores:
            sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
            top_topics = [t[0] for t in sorted_topics[:3]]
            lines.append(f"用户最感兴趣的话题：{'、'.join(top_topics)}，聊天时可以多涉及")

            # 不感兴趣的话题
            if len(sorted_topics) > 3:
                low_topics = [t[0] for t in sorted_topics[-2:]]
                lines.append(f"用户不太感兴趣的话题：{'、'.join(low_topics)}，少主动提起")

        # 提问习惯
        if question_rate > 0.5:
            lines.append("用户经常提问，喜欢深入了解，回答时可以更详细")
        elif question_rate < 0.2:
            lines.append("用户不太提问，更喜欢轻松闲聊，不要总是反问")

        return "\n".join([l for l in lines if l])

    def get_evolution_context(self, user_id: str) -> str:
        """
        获取完整的进化上下文，注入 Prompt。
        """
        persona_hint = self.get_persona_adaptation(user_id)
        if not persona_hint:
            return ""

        return f"[对话进化分析]\n{persona_hint}"

    def _get_evolution_data(self, user_id: str) -> dict | None:
        """获取进化数据"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT value FROM evolution_state "
                "WHERE user_id = ? AND key = 'evolution_data'",
                (user_id,),
            ).fetchone()

        if row:
            try:
                return json.loads(row["value"])
            except json.JSONDecodeError:
                return None
        return None

    # ========== 管理命令 ==========

    def get_status(self, user_id: str) -> str:
        """获取进化状态（供 /evolution 命令使用）"""
        with self.db.get_conn() as conn:
            count_row = conn.execute(
                "SELECT value FROM evolution_state "
                "WHERE user_id = ? AND key = 'conversation_count'",
                (user_id,),
            ).fetchone()

            evo_row = conn.execute(
                "SELECT value, updated_at FROM evolution_state "
                "WHERE user_id = ? AND key = 'evolution_data'",
                (user_id,),
            ).fetchone()

        count = int(count_row["value"]) if count_row else 0
        next_evolve = self._evolve_interval - (count % self._evolve_interval)

        lines = [f"已记录 {count} 次对话，距离下次进化还有 {next_evolve} 次"]

        if evo_row:
            try:
                data = json.loads(evo_row["value"])
                lines.append(f"上次进化：{evo_row['updated_at']}")
                lines.append(f"分析样本：{data.get('total_analyzed', 0)} 条对话")

                topic_scores = data.get("topic_scores", {})
                if topic_scores:
                    sorted_topics = sorted(topic_scores.items(), key=lambda x: x[1], reverse=True)
                    lines.append("话题参与度排名：")
                    for topic, score in sorted_topics[:5]:
                        bar = "█" * int(score)
                        lines.append(f"  {topic}: {bar} ({score:.1f})")

                style_scores = data.get("style_scores", {})
                if style_scores:
                    lines.append("回复风格效果：")
                    for style, score in sorted(style_scores.items(), key=lambda x: x[1], reverse=True):
                        style_name = {"short": "简短", "medium": "适中", "long": "详细"}.get(style, style)
                        lines.append(f"  {style_name}: {score:.1f}")

            except json.JSONDecodeError:
                lines.append("进化数据解析失败")

        return "\n".join(lines)
