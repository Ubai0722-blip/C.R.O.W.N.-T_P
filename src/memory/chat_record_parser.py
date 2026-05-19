# by UBAI
"""
chat_record_parser.py
QQ聊天记录二次解析模块

功能：
1. 解析转发的QQ聊天记录（实时转发 + 压缩包导入）
2. 提取结构化数据（发送者、时间戳、内容、情感）
3. 生成用户行为分析画像
4. 存入数据库供后续检索和分析
5. 为pipeline提供增强上下文
"""

import re
import json
import sqlite3
import zipfile
import os
import io
from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from ..memory.database import Database


@dataclass
class ChatMessage:
    """单条聊天消息"""
    sender: str = ""
    sender_id: str = ""
    timestamp: str = ""
    content: str = ""
    msg_type: str = "text"  # text / image / sticker / file / system
    emotion: str = "平静"
    word_count: int = 0
    has_question: bool = False
    has_emoji: bool = False


@dataclass
class ChatRecordAnalysis:
    """聊天记录分析结果"""
    total_messages: int = 0
    participants: dict = field(default_factory=dict)  # {sender: {msg_count, avg_length, ...}}
    time_range: str = ""
    topic_keywords: list = field(default_factory=list)
    emotion_summary: str = ""
    interaction_pattern: str = ""  # 谁主导、回复速度等
    user_behavior: dict = field(default_factory=dict)


class ChatRecordParser:
    """
    QQ聊天记录解析器
    
    支持两种输入：
    1. 实时转发消息（从forward API获取的原始数据）
    2. QQ导出的聊天记录压缩包（HTML/TXT格式）
    """

    def __init__(self):
        self.db = Database()
        self._ensure_tables()

    def _ensure_tables(self):
        """确保聊天记录分析相关表存在"""
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    record_source TEXT NOT NULL,
                    sender TEXT NOT NULL,
                    sender_id TEXT DEFAULT '',
                    timestamp TEXT DEFAULT '',
                    content TEXT NOT NULL,
                    msg_type TEXT DEFAULT 'text',
                    emotion TEXT DEFAULT '平静',
                    word_count INTEGER DEFAULT 0,
                    has_question INTEGER DEFAULT 0,
                    has_emoji INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_record_analysis (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    record_source TEXT NOT NULL,
                    total_messages INTEGER DEFAULT 0,
                    participants TEXT DEFAULT '{}',
                    time_range TEXT DEFAULT '',
                    topic_keywords TEXT DEFAULT '[]',
                    emotion_summary TEXT DEFAULT '',
                    interaction_pattern TEXT DEFAULT '',
                    user_behavior TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_records_user
                ON chat_records(user_id)
            """)

    # ========== 实时转发消息解析 ==========

    def parse_forward_messages(self, forward_data: dict, user_id: str) -> tuple[str, ChatRecordAnalysis]:
        """
        解析转发的QQ聊天记录（从forward API获取的数据）
        
        返回: (格式化文本, 分析结果)
        """
        messages = forward_data.get("messages", [])
        parsed_msgs = []
        
        for msg in messages:
            sender = msg.get("sender", {})
            nickname = sender.get("nickname", "未知")
            sender_id = str(sender.get("user_id", ""))
            
            # 提取时间戳
            timestamp = ""
            if "time" in msg:
                try:
                    timestamp = datetime.fromtimestamp(msg["time"]).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    pass
            
            # 提取内容
            content = ""
            msg_type = "text"
            for seg in msg.get("message", []):
                seg_type = seg.get("type", "")
                seg_data = seg.get("data", {})
                if seg_type == "text":
                    content += seg_data.get("text", "")
                elif seg_type == "image":
                    content += "[图片]"
                    msg_type = "image"
                elif seg_type == "face":
                    content += f"[表情:{seg_data.get('id', '')}]"
                elif seg_type == "sticker":
                    content += "[贴纸]"
                    msg_type = "sticker"
                elif seg_type == "file":
                    content += f"[文件:{seg_data.get('file', '')}]"
                    msg_type = "file"
            
            if content.strip():
                parsed_msg = ChatMessage(
                    sender=nickname,
                    sender_id=sender_id,
                    timestamp=timestamp,
                    content=content.strip(),
                    msg_type=msg_type,
                    word_count=len(content.strip()),
                    has_question="?" in content or "？" in content,
                    has_emoji=bool(re.search(r'\[表情|emoji', content)),
                )
                parsed_msgs.append(parsed_msg)
        
        # 存入数据库
        source = f"forward_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self._store_messages(parsed_msgs, user_id, source)
        
        # 生成分析结果
        analysis = self._analyze_messages(parsed_msgs, user_id, source)
        
        # 生成格式化文本
        formatted = self._format_for_pipeline(parsed_msgs, analysis)
        
        return formatted, analysis

    # ========== 压缩包导入解析 ==========

    def parse_archive(self, archive_path: str, user_id: str) -> tuple[str, ChatRecordAnalysis]:
        """
        解析QQ导出的聊天记录压缩包
        
        支持格式：
        - QQ导出的HTML格式聊天记录
        - QQ导出的TXT格式聊天记录
        - 包含多个HTML/TXT文件的压缩包
        
        返回: (格式化文本, 分析结果)
        """
        parsed_msgs = []
        source = f"archive_{Path(archive_path).stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if archive_path.endswith('.zip'):
            with zipfile.ZipFile(archive_path) as zf:
                for name in zf.namelist():
                    if name.endswith('/') or not any(name.endswith(ext) for ext in ['.html', '.htm', '.txt', '.mht']):
                        continue
                    try:
                        with zf.open(name) as f:
                            content = f.read().decode('utf-8', errors='replace')
                            if name.endswith(('.html', '.htm', '.mht')):
                                msgs = self._parse_html_record(content)
                            else:
                                msgs = self._parse_txt_record(content)
                            parsed_msgs.extend(msgs)
                    except Exception as e:
                        print(f"[ChatRecordParser] 解析 {name} 失败: {e}")
        elif archive_path.endswith(('.html', '.htm')):
            with open(archive_path, 'r', encoding='utf-8', errors='replace') as f:
                parsed_msgs = self._parse_html_record(f.read())
        elif archive_path.endswith('.txt'):
            with open(archive_path, 'r', encoding='utf-8', errors='replace') as f:
                parsed_msgs = self._parse_txt_record(f.read())
        
        # 存入数据库
        self._store_messages(parsed_msgs, user_id, source)
        
        # 生成分析结果
        analysis = self._analyze_messages(parsed_msgs, user_id, source)
        
        # 生成格式化文本
        formatted = self._format_for_pipeline(parsed_msgs, analysis)
        
        return formatted, analysis

    def parse_text_content(self, text_content: str, user_id: str, source_name: str = "manual_text") -> tuple[str, ChatRecordAnalysis]:
        """
        解析直接粘贴的聊天记录文本（TXT/HTML 混合容错）。
        """
        raw = (text_content or "").strip()
        if not raw:
            return "", ChatRecordAnalysis()

        source = f"text_{source_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if "<html" in raw.lower() or "<div" in raw.lower() or "<p" in raw.lower():
            parsed_msgs = self._parse_html_record(raw)
        else:
            parsed_msgs = self._parse_txt_record(raw)

        # fallback: 普通多行文本（没有 QQ 导出格式）时，按非空行逐条入库
        if not parsed_msgs:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            parsed_msgs = [
                ChatMessage(
                    sender="user",
                    sender_id=user_id,
                    timestamp=now,
                    content=line.strip(),
                    msg_type="text",
                    word_count=len(line.strip()),
                    has_question=("?" in line or "？" in line),
                    has_emoji=False,
                )
                for line in raw.splitlines()
                if line.strip()
            ]

        self._store_messages(parsed_msgs, user_id, source)
        analysis = self._analyze_messages(parsed_msgs, user_id, source)
        formatted = self._format_for_pipeline(parsed_msgs, analysis)
        return formatted, analysis

    def _parse_html_record(self, html_content: str) -> list[ChatMessage]:
        """
        解析QQ导出的HTML格式聊天记录
        
        QQ导出的HTML格式通常是：
        <div class="message">
            <div class="sender">发送者</div>
            <div class="time">时间</div>
            <div class="content">内容</div>
        </div>
        
        或者更常见的格式：
        <p>发送者 时间</p>
        <p>内容</p>
        """
        messages = []
        
        # 尝试多种QQ导出格式
        # 格式1: 带class的div结构
        pattern1 = r'<div[^>]*class="[^"]*message[^"]*"[^>]*>.*?</div>'
        # 格式2: 简单的p标签结构 (发送者 时间\n内容)
        pattern2 = r'<p[^>]*>(.*?)</p>'
        # 格式3: QQ新版导出格式
        pattern3 = r'<[^>]*nick="([^"]*)"[^>]*time="(\d+)"[^>]*>(.*?)</[^>]*>'
        
        # 先尝试格式3
        matches = re.findall(pattern3, html_content, re.DOTALL)
        if matches:
            for nick, timestamp, content in matches:
                # 清理HTML标签
                clean_content = re.sub(r'<[^>]+>', '', content).strip()
                if clean_content:
                    try:
                        ts = datetime.fromtimestamp(int(timestamp)).strftime("%Y-%m-%d %H:%M:%S")
                    except:
                        ts = ""
                    messages.append(ChatMessage(
                        sender=nick.strip(),
                        timestamp=ts,
                        content=clean_content,
                        word_count=len(clean_content),
                        has_question="?" in clean_content or "？" in clean_content,
                    ))
            if messages:
                return messages
        
        # 尝试格式2
        p_matches = re.findall(pattern2, html_content, re.DOTALL)
        current_sender = ""
        current_time = ""
        for p_content in p_matches:
            clean = re.sub(r'<[^>]+>', '', p_content).strip()
            if not clean:
                continue
            
            # 检查是否是 "发送者 时间" 格式
            sender_time_match = re.match(r'^([^\s]+)\s+(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)', clean)
            if sender_time_match:
                current_sender = sender_time_match.group(1)
                current_time = sender_time_match.group(2)
                continue
            
            # 否则是消息内容
            if current_sender:
                messages.append(ChatMessage(
                    sender=current_sender,
                    timestamp=current_time,
                    content=clean,
                    word_count=len(clean),
                    has_question="?" in clean or "？" in clean,
                ))
                current_sender = ""
                current_time = ""
            else:
                # 可能是连续内容
                messages.append(ChatMessage(
                    sender="未知",
                    content=clean,
                    word_count=len(clean),
                ))
        
        return messages

    def _parse_txt_record(self, txt_content: str) -> list[ChatMessage]:
        """
        解析QQ导出的TXT格式聊天记录
        
        常见格式：
        发送者 2024-01-01 12:00:00
        消息内容
        
        或：
        [2024-01-01 12:00:00] 发送者: 消息内容
        """
        messages = []
        lines = txt_content.split('\n')
        
        # 格式1: 发送者 时间\n内容
        pattern1 = re.compile(r'^([^\s]+)\s+(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)$')
        # 格式2: [时间] 发送者: 内容
        pattern2 = re.compile(r'^\[(\d{4}-\d{1,2}-\d{1,2}\s+\d{1,2}:\d{2}(?::\d{2})?)\]\s*([^:：]+)[：:]\s*(.*)$')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # 尝试格式2
            m2 = pattern2.match(line)
            if m2:
                messages.append(ChatMessage(
                    sender=m2.group(2).strip(),
                    timestamp=m2.group(1),
                    content=m2.group(3).strip(),
                    word_count=len(m2.group(3).strip()),
                    has_question="?" in m2.group(3) or "？" in m2.group(3),
                ))
                i += 1
                continue
            
            # 尝试格式1
            m1 = pattern1.match(line)
            if m1:
                sender = m1.group(1)
                timestamp = m1.group(2)
                # 下一行是内容
                content_lines = []
                i += 1
                while i < len(lines):
                    next_line = lines[i].strip()
                    if not next_line:
                        break
                    if pattern1.match(next_line) or pattern2.match(next_line):
                        break
                    content_lines.append(next_line)
                    i += 1
                content = '\n'.join(content_lines)
                if content:
                    messages.append(ChatMessage(
                        sender=sender,
                        timestamp=timestamp,
                        content=content,
                        word_count=len(content),
                        has_question="?" in content or "？" in content,
                    ))
                continue
            
            # 跳过无法识别的行
            i += 1
        
        return messages

    # ========== 数据库存储 ==========

    def _store_messages(self, messages: list[ChatMessage], user_id: str, source: str):
        """将解析的消息存入数据库"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            for msg in messages:
                conn.execute(
                    "INSERT INTO chat_records (user_id, record_source, sender, sender_id, timestamp, content, msg_type, emotion, word_count, has_question, has_emoji, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (user_id, source, msg.sender, msg.sender_id, msg.timestamp, msg.content, msg.msg_type, msg.emotion, msg.word_count, int(msg.has_question), int(msg.has_emoji), now)
                )

    # ========== 分析生成 ==========

    def _analyze_messages(self, messages: list[ChatMessage], user_id: str, source: str) -> ChatRecordAnalysis:
        """分析聊天记录，生成行为画像"""
        if not messages:
            return ChatRecordAnalysis()
        
        analysis = ChatRecordAnalysis(
            total_messages=len(messages),
        )
        
        # 参与者统计
        participants = {}
        for msg in messages:
            if msg.sender not in participants:
                participants[msg.sender] = {
                    "msg_count": 0,
                    "total_words": 0,
                    "questions": 0,
                    "avg_length": 0,
                }
            participants[msg.sender]["msg_count"] += 1
            participants[msg.sender]["total_words"] += msg.word_count
            if msg.has_question:
                participants[msg.sender]["questions"] += 1
        
        for sender, stats in participants.items():
            if stats["msg_count"] > 0:
                stats["avg_length"] = round(stats["total_words"] / stats["msg_count"], 1)
        
        analysis.participants = participants
        
        # 时间范围
        timestamps = [m.timestamp for m in messages if m.timestamp]
        if timestamps:
            analysis.time_range = f"{timestamps[0]} ~ {timestamps[-1]}"
        
        # 关键词提取（简单实现）
        all_text = " ".join(m.content for m in messages)
        # 移除标点符号
        clean_text = re.sub(r'[^\w\s]', '', all_text)
        words = clean_text.split()
        word_freq = {}
        for w in words:
            if len(w) >= 2:
                word_freq[w] = word_freq.get(w, 0) + 1
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:10]
        analysis.topic_keywords = [w[0] for w in sorted_words]
        
        # 互动模式分析
        if len(participants) >= 2:
            sorted_participants = sorted(participants.items(), key=lambda x: x[1]["msg_count"], reverse=True)
            leader = sorted_participants[0]
            analysis.interaction_pattern = f"{leader[0]}主导对话（{leader[1]['msg_count']}条/{analysis.total_messages}条）"
        
        # 用户行为分析（针对发送者列表中的第一个非"未知"用户）
        for sender, stats in participants.items():
            if sender != "未知":
                analysis.user_behavior = {
                    "dominant_sender": sender,
                    "message_frequency": stats["msg_count"],
                    "avg_message_length": stats["avg_length"],
                    "question_ratio": round(stats["questions"] / stats["msg_count"] * 100, 1) if stats["msg_count"] > 0 else 0,
                }
                break
        
        # 存入分析结果
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO chat_record_analysis (user_id, record_source, total_messages, participants, time_range, topic_keywords, emotion_summary, interaction_pattern, user_behavior, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, source, analysis.total_messages, json.dumps(analysis.participants, ensure_ascii=False), analysis.time_range, json.dumps(analysis.topic_keywords, ensure_ascii=False), analysis.emotion_summary, analysis.interaction_pattern, json.dumps(analysis.user_behavior, ensure_ascii=False), now)
            )
        
        return analysis

    # ========== 格式化输出 ==========

    def _format_for_pipeline(self, messages: list[ChatMessage], analysis: ChatRecordAnalysis) -> str:
        """
        格式化为pipeline可用的文本
        
        包含：
        - 结构化的聊天记录
        - 分析摘要
        """
        lines = []
        
        # 添加分析摘要
        if analysis.participants:
            summary_parts = []
            for sender, stats in analysis.participants.items():
                summary_parts.append(f"{sender}({stats['msg_count']}条)")
            lines.append(f"[聊天记录摘要] 参与者: {', '.join(summary_parts)}")
            if analysis.time_range:
                lines.append(f"时间范围: {analysis.time_range}")
            if analysis.topic_keywords:
                lines.append(f"关键词: {', '.join(analysis.topic_keywords[:5])}")
            lines.append("")
        
        # 添加消息内容
        lines.append("[聊天记录开始]")
        for msg in messages:
            time_str = f"[{msg.timestamp}] " if msg.timestamp else ""
            lines.append(f"{time_str}{msg.sender}: {msg.content}")
        lines.append("[聊天记录结束]")
        
        return "\n".join(lines)

    # ========== 查询接口 ==========

    def get_user_records(self, user_id: str, limit: int = 50) -> list[dict]:
        """获取用户的聊天记录"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_records WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_user_analysis(self, user_id: str, limit: int = 10) -> list[dict]:
        """获取用户的聊天记录分析"""
        with self.db.get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chat_record_analysis WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_record_stats(self, user_id: str) -> dict:
        """获取用户的聊天记录统计"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) as total_records, COUNT(DISTINCT record_source) as total_sources FROM chat_records WHERE user_id = ?",
                (user_id,)
            ).fetchone()
            return dict(row) if row else {"total_records": 0, "total_sources": 0}
