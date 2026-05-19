# by UBAI
"""
database.py
数据库管理模块 - SQLite（支持人设隔离）
"""
import sqlite3
import threading
import shutil
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime

DB_PATH = Path("data/chatbot.db")
SHARED_DB_PATH = Path("data/chatbot_shared.db")


class Database:
    """数据库管理器（单例 + 连接复用 + 人设隔离）"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._local = threading.local()
        self._current_persona = "default"
        self._current_user_id = ""  # 当前活跃用户 ID（用于 per-user 路由）
        self._psychology_shared = True  # 默认共享心理画像
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    def set_persona(self, persona_name: str):
        """切换人设数据库"""
        if persona_name == self._current_persona:
            return
        old_persona = self._current_persona
        self._current_persona = persona_name
        # 清除当前线程的连接缓存，下次 get_conn 会连新库
        if hasattr(self._local, 'conn'):
            try:
                self._local.conn.close()
            except:
                pass
            del self._local.conn
        # 确保新数据库有表结构
        self._init_tables()
        print(f"[DB] 数据库切换: {old_persona} -> {persona_name}")

    def set_psychology_shared(self, shared: bool):
        """设置心理画像是否共享"""
        self._psychology_shared = shared

    @property
    def current_db_path(self) -> Path:
        """当前人设的数据库路径（新版结构：per-user per-persona）"""
        # 优先使用新版 accounts 目录结构
        # 如果有活跃用户，使用 user_data.db；否则回退到旧结构
        if hasattr(self, '_current_user_id') and self._current_user_id:
            user_db = Path(f"data/accounts/{self._current_user_id}/{self._current_persona}/user_data.db")
            user_db.parent.mkdir(parents=True, exist_ok=True)
            return user_db
        if self._current_persona == "default":
            return DB_PATH
        return Path(f"data/chatbot_{self._current_persona}.db")

    def set_user(self, user_id: str):
        """设置当前用户（用于 per-user 数据库路由）"""
        if user_id == getattr(self, "_current_user_id", ""):
            return
        self._current_user_id = user_id
        # 清除连接缓存以切换到正确的数据库
        if hasattr(self._local, 'conn'):
            try:
                self._local.conn.close()
            except:
                pass
            del self._local.conn
        self._init_tables()

    @property
    def psychology_db(self) -> Path:
        """心理画像使用的数据库路径"""
        if self._psychology_shared:
            return SHARED_DB_PATH
        return self.current_db_path

    def _get_thread_conn(self):
        """获取当前线程的复用连接"""
        conn = getattr(self._local, 'conn', None)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except:
                try:
                    conn.close()
                except:
                    pass
        db_path = self.current_db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=30)
        self._configure_conn(conn)
        self._local.conn = conn
        return conn

    def _get_shared_conn(self):
        """获取共享数据库连接（用于心理画像共享模式）"""
        conn = getattr(self._local, 'shared_conn', None)
        if conn is not None:
            try:
                conn.execute("SELECT 1")
                return conn
            except:
                try:
                    conn.close()
                except:
                    pass
        SHARED_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(SHARED_DB_PATH), timeout=30)
        self._configure_conn(conn)
        self._local.shared_conn = conn
        return conn

    def _configure_conn(self, conn):
        """统一 SQLite 连接参数，降低长期运行时的锁库和半写入风险。"""
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA wal_autocheckpoint=1000")

    @contextmanager
    def get_conn(self):
        """获取数据库连接（线程复用）"""
        conn = self._get_thread_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @contextmanager
    def get_psychology_conn(self):
        """获取心理画像数据库连接（根据共享设置选择库）"""
        if self._psychology_shared:
            conn = self._get_shared_conn()
        else:
            conn = self._get_thread_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def clear_persona_data(self, persona_name: str):
        """清空指定人设的数据库"""
        db_path = Path(f"data/chatbot_{persona_name}.db")
        if persona_name == "default":
            db_path = DB_PATH
        if db_path.exists():
            conn = sqlite3.connect(str(db_path))
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for (table,) in tables:
                if table != 'sqlite_master':
                    conn.execute(f"DELETE FROM [{table}]")
            conn.commit()
            conn.close()
            print(f"[DB] 已清空人设 {persona_name} 的数据库")

    def clear_shared_psychology(self):
        """清空共享心理画像数据"""
        if SHARED_DB_PATH.exists():
            conn = sqlite3.connect(str(SHARED_DB_PATH))
            conn.execute("DELETE FROM user_psychology")
            conn.execute("DELETE FROM psychology_history")
            conn.commit()
            conn.close()
            print("[DB] 已清空共享心理画像数据")

    def merge_psychology_to_shared(self, primary_persona: str):
        """将所有人设的心理画像融合到共享库，当前人设为主，其余为辅"""
        import glob
        SHARED_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

        # 1. 清空共享库
        shared_conn = sqlite3.connect(str(SHARED_DB_PATH), timeout=10)
        shared_conn.row_factory = sqlite3.Row
        shared_conn.execute("PRAGMA journal_mode=WAL")
        shared_conn.execute("DELETE FROM user_psychology")
        shared_conn.execute("DELETE FROM psychology_history")

        # 2. 扫描所有人设数据库
        db_dir = Path("data")
        all_dbs = list(db_dir.glob("chatbot*.db"))

        primary_data = {}   # 当前人设的画像数据
        other_data = {}     # 其余人设的画像数据

        for db_file in all_dbs:
            if db_file.name == "chatbot_shared.db":
                continue
            persona_name = db_file.stem.replace("chatbot_", "").replace("chatbot", "default")
            try:
                src_conn = sqlite3.connect(str(db_file), timeout=5)
                src_conn.row_factory = sqlite3.Row
                rows = src_conn.execute("SELECT * FROM user_psychology").fetchall()
                for row in rows:
                    row_dict = dict(row)
                    uid = row_dict["user_id"]
                    if persona_name == primary_persona:
                        primary_data[uid] = row_dict
                    else:
                        if uid not in other_data:
                            other_data[uid] = []
                        other_data[uid].append(row_dict)
                src_conn.close()
            except Exception as e:
                print(f"[DB] 读取 {db_file.name} 心理画像失败: {e}")

        # 3. 融合：当前人设为主，其余为辅
        # 先写入当前人设的数据（主要）
        for uid, data in primary_data.items():
            cols = ", ".join(data.keys())
            placeholders = ", ".join(["?"] * len(data))
            shared_conn.execute(
                f"INSERT OR REPLACE INTO user_psychology ({cols}) VALUES ({placeholders})",
                list(data.values())
            )

        # 再融合其余人设的数据（补充未覆盖的字段）
        for uid, others in other_data.items():
            if uid in primary_data:
                # 当前人设已有此用户，用其余人设补充空字段
                primary = primary_data[uid]
                for other in others:
                    for key, val in other.items():
                        if key in ("user_id", "analysis_count", "last_analyzed"):
                            continue
                        current_val = primary.get(key, "")
                        if (not current_val or current_val in ("未知", "[]", "{}", "正常")) and val and val not in ("未知", "[]", "{}", "正常"):
                            shared_conn.execute(
                                f"UPDATE user_psychology SET [{key}] = ? WHERE user_id = ?",
                                (val, uid)
                            )
            else:
                # 当前人设没有此用户，直接写入
                for other in others:
                    cols = ", ".join(other.keys())
                    placeholders = ", ".join(["?"] * len(other))
                    try:
                        shared_conn.execute(
                            f"INSERT INTO user_psychology ({cols}) VALUES ({placeholders})",
                            list(other.values())
                        )
                    except Exception:
                        pass

        # 4. 融合历史记录
        for db_file in all_dbs:
            if db_file.name == "chatbot_shared.db":
                continue
            try:
                src_conn = sqlite3.connect(str(db_file), timeout=5)
                src_conn.row_factory = sqlite3.Row
                rows = src_conn.execute("SELECT * FROM psychology_history").fetchall()
                for row in rows:
                    d = dict(row)
                    cols = ", ".join(d.keys())
                    placeholders = ", ".join(["?"] * len(d))
                    try:
                        shared_conn.execute(
                            f"INSERT INTO psychology_history ({cols}) VALUES ({placeholders})",
                            list(d.values())
                        )
                    except Exception:
                        pass
                src_conn.close()
            except Exception:
                pass

        shared_conn.commit()
        shared_conn.close()
        print(f"[DB] 心理画像融合完成: {primary_persona} 为主, {len(other_data)} 个用户有辅助数据")

    def save_shared_to_persona(self, persona_name: str):
        """将共享心理画像数据保存到指定人设的专用数据库（关闭共享时调用）"""
        if not SHARED_DB_PATH.exists():
            return

        target_db = Path(f"data/chatbot_{persona_name}.db")
        if persona_name == "default":
            target_db = DB_PATH
        if not target_db.exists():
            return

        try:
            shared_conn = sqlite3.connect(str(SHARED_DB_PATH), timeout=5)
            shared_conn.row_factory = sqlite3.Row
            target_conn = sqlite3.connect(str(target_db), timeout=5)
            target_conn.row_factory = sqlite3.Row

            # 确保目标库有心理画像表
            target_conn.execute("""CREATE TABLE IF NOT EXISTS user_psychology (
                user_id TEXT PRIMARY KEY, personality TEXT DEFAULT '{}',
                emotional_stability TEXT DEFAULT '未知', communication_style TEXT DEFAULT '未知',
                emotional_needs TEXT DEFAULT '[]', mental_state TEXT DEFAULT '正常',
                social_preference TEXT DEFAULT '未知', values_keywords TEXT DEFAULT '[]',
                stress_indicators TEXT DEFAULT '[]', coping_style TEXT DEFAULT '未知',
                attachment_style TEXT DEFAULT '未知', analysis_count INTEGER DEFAULT 0,
                last_analyzed TEXT DEFAULT '', raw_traits TEXT DEFAULT '[]'
            )""")
            target_conn.execute("""CREATE TABLE IF NOT EXISTS psychology_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL, dimension TEXT NOT NULL,
                old_value TEXT, new_value TEXT, trigger_text TEXT, confidence REAL DEFAULT 0.5
            )""")

            # 复制心理画像数据
            rows = shared_conn.execute("SELECT * FROM user_psychology").fetchall()
            for row in rows:
                d = dict(row)
                cols = ", ".join(d.keys())
                placeholders = ", ".join(["?"] * len(d))
                target_conn.execute(
                    f"INSERT OR REPLACE INTO user_psychology ({cols}) VALUES ({placeholders})",
                    list(d.values())
                )

            # 复制历史记录
            rows = shared_conn.execute("SELECT * FROM psychology_history").fetchall()
            for row in rows:
                d = dict(row)
                d.pop("id", None)  # 让目标库自动生成 ID
                cols = ", ".join(d.keys())
                placeholders = ", ".join(["?"] * len(d))
                target_conn.execute(
                    f"INSERT INTO psychology_history ({cols}) VALUES ({placeholders})",
                    list(d.values())
                )

            target_conn.commit()
            shared_conn.close()
            target_conn.close()
            print(f"[DB] 共享心理画像已保存到 {persona_name} 专用数据库")
        except Exception as e:
            print(f"[DB] 保存共享心理画像失败: {e}")

    def list_persona_databases(self) -> list[dict]:
        """列出所有人设数据库"""
        import os
        result = []
        db_dir = Path("data")
        for f in db_dir.glob("chatbot*.db"):
            size = os.path.getsize(f)
            name = f.stem.replace("chatbot_", "").replace("chatbot", "default")
            result.append({"name": name, "file": f.name, "size": size})
        return result

    # ========== 时间提及管理 ==========

    def save_time_mention(self, user_id: str, mentioned_time: str, context: str = "", expires_at: str = "") -> None:
        """
        保存用户提到的时间信息。
        mentioned_time: 用户提到的时间描述（如“明天下午3点”）
        context: 上下文信息
        expires_at: 过期时间（ISO 格式）
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not expires_at:
            # 默认 12 小时后过期
            from datetime import timedelta
            expires_at = (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            conn.execute(
                "INSERT INTO temp_time_mentions (user_id, mentioned_time, context, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, mentioned_time, context, now, expires_at),
            )

    def get_active_time_mentions(self, user_id: str) -> list[dict]:
        """
        获取用户当前有效的时间提及（未过期的）。
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            rows = conn.execute(
                "SELECT id, mentioned_time, context, created_at, expires_at "
                "FROM temp_time_mentions WHERE user_id = ? AND expires_at > ? "
                "ORDER BY created_at DESC",
                (user_id, now),
            ).fetchall()
        return [dict(r) for r in rows]

    def cleanup_expired_time_mentions(self) -> int:
        """
        清理过期的时间提及记录。返回清理的数量。
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM temp_time_mentions WHERE expires_at <= ?",
                (now,),
            )
            return cursor.rowcount

    def _init_tables(self):
        """初始化所有表（当前人设数据库 + 共享数据库）"""
        schema = """
            CREATE TABLE IF NOT EXISTS life_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                persona TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                mood TEXT NOT NULL,
                time TEXT NOT NULL,
                expire_hours INTEGER DEFAULT 72,
                shared INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                nickname TEXT DEFAULT '',
                relationship_level INTEGER DEFAULT 5,
                relationship_exp INTEGER DEFAULT 0,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                total_messages INTEGER DEFAULT 0,
                total_days INTEGER DEFAULT 0,
                shared_experiences INTEGER DEFAULT 0,
                emotional_bonds INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS growth_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                time TEXT NOT NULL,
                event TEXT NOT NULL,
                category TEXT NOT NULL,
                emotion TEXT DEFAULT '平静',
                user_involved INTEGER DEFAULT 1,
                impact INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS long_term_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 1,
                access_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                last_accessed TEXT
            );
            CREATE TABLE IF NOT EXISTS active_days (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                UNIQUE(user_id, date)
            );
            CREATE TABLE IF NOT EXISTS mood_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                emotion TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS favorite_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                category TEXT NOT NULL,
                count INTEGER DEFAULT 1,
                UNIQUE(user_id, category)
            );
            CREATE TABLE IF NOT EXISTS conversation_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                topic TEXT,
                emotion TEXT,
                user_msg_length INTEGER DEFAULT 0,
                ai_msg_length INTEGER DEFAULT 0,
                engagement_score REAL DEFAULT 0,
                event_type TEXT DEFAULT '',
                has_question INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS evolution_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, key)
            );
            CREATE TABLE IF NOT EXISTS emotion_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL UNIQUE,
                mood_value REAL DEFAULT 0.0,
                dominant_emotion TEXT DEFAULT '平静',
                streak_count INTEGER DEFAULT 0,
                last_emotion TEXT DEFAULT '平静',
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chat_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                user_msg TEXT NOT NULL,
                ai_reply TEXT NOT NULL,
                emotion TEXT DEFAULT '平静'
            );
            CREATE TABLE IF NOT EXISTS word_weights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                word TEXT NOT NULL UNIQUE,
                weight REAL DEFAULT 1.0,
                category TEXT DEFAULT '默认',
                hit_count INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_life_persona ON life_events(persona);
            CREATE INDEX IF NOT EXISTS idx_growth_user ON growth_memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_memory_user ON long_term_memory(user_id);
            CREATE INDEX IF NOT EXISTS idx_active_user ON active_days(user_id);
            CREATE INDEX IF NOT EXISTS idx_mood_user ON mood_history(user_id);
            CREATE INDEX IF NOT EXISTS idx_topic_user ON favorite_topics(user_id);
            CREATE INDEX IF NOT EXISTS idx_evo_log_user ON conversation_log(user_id);
            CREATE TABLE IF NOT EXISTS temp_time_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                mentioned_time TEXT NOT NULL,
                context TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_time_mentions_user ON temp_time_mentions(user_id);
            CREATE INDEX IF NOT EXISTS idx_time_mentions_expires ON temp_time_mentions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_chat_user ON chat_history(user_id);

            CREATE TABLE IF NOT EXISTS chat_whitelist (
                qq_id TEXT PRIMARY KEY,
                nickname TEXT DEFAULT '',
                enabled INTEGER DEFAULT 1,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS proactive_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                state_key TEXT NOT NULL,
                state_value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, state_key)
            );
            CREATE INDEX IF NOT EXISTS idx_proactive_user ON proactive_state(user_id);

            CREATE TABLE IF NOT EXISTS pad_state (
                user_id TEXT PRIMARY KEY,
                p_value REAL DEFAULT 0.0,
                a_value REAL DEFAULT 0.0,
                d_value REAL DEFAULT 0.0,
                base_p REAL DEFAULT 0.0,
                base_a REAL DEFAULT 0.0,
                base_d REAL DEFAULT 0.0,
                last_update TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS persona_control (
                user_id TEXT PRIMARY KEY,
                cumulative_state TEXT DEFAULT '{}',
                residual_history TEXT DEFAULT '[]',
                last_correction TEXT DEFAULT '',
                correction_count INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS persona_residuals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                residual_data TEXT NOT NULL,
                magnitude REAL DEFAULT 0.0,
                dominant_dim TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS drift_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                is_drifting INTEGER DEFAULT 0,
                drift_score REAL DEFAULT 0.0,
                drift_dimensions TEXT DEFAULT '[]',
                correction_hint TEXT DEFAULT '',
                trigger_text TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS relationship_state (
                user_id TEXT PRIMARY KEY,
                type_id TEXT NOT NULL DEFAULT 'default',
                switched_at TEXT NOT NULL,
                custom_data TEXT DEFAULT '{}',
                enabled INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS narrative_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                narrative_type TEXT NOT NULL,
                content TEXT NOT NULL,
                emotion TEXT DEFAULT '平静',
                trigger TEXT DEFAULT '',
                timestamp TEXT NOT NULL
            );

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
            );
            CREATE INDEX IF NOT EXISTS idx_episodic_user ON episodic_memories(user_id);
        """

        psych_schema = """
            CREATE TABLE IF NOT EXISTS user_psychology (
                user_id TEXT PRIMARY KEY,
                personality TEXT DEFAULT '{}',
                emotional_stability TEXT DEFAULT '未知',
                communication_style TEXT DEFAULT '未知',
                emotional_needs TEXT DEFAULT '[]',
                mental_state TEXT DEFAULT '正常',
                social_preference TEXT DEFAULT '未知',
                values_keywords TEXT DEFAULT '[]',
                stress_indicators TEXT DEFAULT '[]',
                coping_style TEXT DEFAULT '未知',
                attachment_style TEXT DEFAULT '未知',
                analysis_count INTEGER DEFAULT 0,
                last_analyzed TEXT DEFAULT '',
                raw_traits TEXT DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS psychology_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                dimension TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                trigger_text TEXT,
                confidence REAL DEFAULT 0.5
            );
            CREATE INDEX IF NOT EXISTS idx_psych_user ON user_psychology(user_id);
            CREATE INDEX IF NOT EXISTS idx_psych_hist_user ON psychology_history(user_id);
        """

        # 初始化当前人设数据库（包含所有表）
        with self.get_conn() as conn:
            conn.executescript(schema)
            if not self._psychology_shared:
                conn.executescript(psych_schema)

        # 初始化共享数据库（仅心理画像表）
        SHARED_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(SHARED_DB_PATH), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            conn.executescript(psych_schema)
            conn.commit()
        finally:
            conn.close()
