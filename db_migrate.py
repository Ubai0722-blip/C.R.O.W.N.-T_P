"""
db_migrate.py - 自动迁移旧版 data/ 目录到新版 账户-人设 格式
启动时自动检测并执行迁移，幂等安全（重复运行不会破坏数据）

旧版结构：
  data/chatbot.db, data/chatbot_{persona}.db, data/chatbot_shared.db
  data/scenes.yaml, data/tones.yaml, data/relationship_types.yaml
  personas/{name}.yaml

新版结构：
  data/
    _migrated.flag                     # 迁移完成标记
    accounts/
      {user_id}/
        {persona}/
          user_data.db                 # 该用户在该人设下的所有数据
    personas/
      {persona}/
        global.db                      # 人设级全局数据 (life_events, whitelist, relationship_state)
        persona.yaml                   # 人设配置副本
        scenes.yaml, tones.yaml        # 场景/语气配置
    shared/
      psychology.db                    # 跨人设共享心理画像
    relationship_types.yaml
"""
import sqlite3
import shutil
import yaml
from pathlib import Path
from datetime import datetime


def _get_user_tables():
    """返回包含 user_id 列的表名列表"""
    return [
        'user_profiles', 'growth_memories', 'long_term_memory',
        'active_days', 'mood_history', 'favorite_topics',
        'conversation_log', 'evolution_state', 'emotion_state',
        'chat_history', 'drift_reports', 'narrative_log',
        'episodic_memories', 'pad_state', 'persona_control',
        'persona_residuals', 'temp_time_mentions', 'proactive_state',
        'word_weights',
    ]


def _get_global_tables():
    """返回不包含 user_id 列的全局表名列表"""
    return ['life_events', 'chat_whitelist', 'relationship_state']


def _ensure_table_exists(conn, table_name, source_conn):
    """在目标连接中创建与源相同的表结构"""
    row = source_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    ).fetchone()
    if row and row[0]:
        # 加 IF NOT EXISTS 防止重复创建
        sql = row[0].replace('CREATE TABLE', 'CREATE TABLE IF NOT EXISTS', 1)
        conn.execute(sql)


def _migrate_persona_db(persona_name, src_db_path, data_dir):
    """
    迁移单个人设数据库到新版结构
    - 全局表 → data/personas/{persona}/global.db
    - 按 user_id 拆分 → data/accounts/{user_id}/{persona}/user_data.db
    """
    accounts_dir = data_dir / "accounts"
    personas_dir = data_dir / "personas" / persona_name
    accounts_dir.mkdir(parents=True, exist_ok=True)
    personas_dir.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(str(src_db_path))
    src_conn.row_factory = sqlite3.Row

    # 获取所有表
    all_tables = [r[0] for r in src_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()]

    user_tables = [t for t in _get_user_tables() if t in all_tables]
    global_tables = [t for t in _get_global_tables() if t in all_tables]

    # 1. 迁移全局表到 global.db
    global_db_path = personas_dir / "global.db"
    if global_tables:
        g_conn = sqlite3.connect(str(global_db_path))
        for table in global_tables:
            _ensure_table_exists(g_conn, table, src_conn)
            rows = src_conn.execute(f"SELECT * FROM [{table}]").fetchall()
            if rows:
                cols = [d[1] for d in src_conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
                placeholders = ", ".join(["?"] * len(cols))
                col_str = ", ".join([f"[{c}]" for c in cols])
                for row in rows:
                    try:
                        g_conn.execute(f"INSERT OR REPLACE INTO [{table}] ({col_str}) VALUES ({placeholders})", list(row))
                    except Exception:
                        pass
        g_conn.commit()
        g_conn.close()

    # 2. 收集所有 user_id
    user_ids = set()
    for table in user_tables:
        if table not in all_tables:
            continue
        try:
            rows = src_conn.execute(f"SELECT DISTINCT user_id FROM [{table}]").fetchall()
            for r in rows:
                if r[0]:
                    user_ids.add(r[0])
        except Exception:
            pass

    # 如果没有 user_id 但有数据，用 "default" 作为 user_id
    if not user_ids:
        has_data = False
        for table in user_tables:
            if table not in all_tables:
                continue
            count = src_conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
            if count > 0:
                has_data = True
                break
        if has_data:
            user_ids.add("default")

    # 3. 按 user_id 拆分迁移到各自的 user_data.db
    for user_id in user_ids:
        user_db_dir = accounts_dir / user_id / persona_name
        user_db_dir.mkdir(parents=True, exist_ok=True)
        user_db_path = user_db_dir / "user_data.db"

        u_conn = sqlite3.connect(str(user_db_path))
        for table in user_tables:
            if table not in all_tables:
                continue
            _ensure_table_exists(u_conn, table, src_conn)
            try:
                rows = src_conn.execute(
                    f"SELECT * FROM [{table}] WHERE user_id = ?", (user_id,)
                ).fetchall()
                if rows:
                    cols = [d[1] for d in src_conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
                    placeholders = ", ".join(["?"] * len(cols))
                    col_str = ", ".join([f"[{c}]" for c in cols])
                    for row in rows:
                        try:
                            u_conn.execute(f"INSERT OR REPLACE INTO [{table}] ({col_str}) VALUES ({placeholders})", list(row))
                        except Exception:
                            pass
            except Exception:
                pass
        u_conn.commit()
        u_conn.close()

    src_conn.close()
    return len(user_ids)


def migrate_if_needed(base_dir):
    """
    主迁移入口：检测旧版格式并自动迁移
    返回: (migrated: bool, message: str)
    """
    base_dir = Path(base_dir)
    data_dir = base_dir / "data"
    flag_file = data_dir / "_migrated.flag"

    # 已迁移，跳过
    if flag_file.exists():
        return False, "已迁移，跳过"

    # 检测旧版文件
    old_dbs = list(data_dir.glob("chatbot*.db"))
    if not old_dbs:
        # 没有旧版数据库，直接标记完成
        flag_file.write_text(f"no legacy dbs found\nmigrated: {datetime.now().isoformat()}\n", encoding="utf-8")
        return False, "无旧版数据库"

    print(f"[MIGRATE] 检测到 {len(old_dbs)} 个旧版数据库，开始迁移...")

    # 备份旧文件到 _legacy_backup
    legacy_dir = data_dir / "_legacy_backup"
    legacy_dir.mkdir(parents=True, exist_ok=True)

    migrated_personas = []

    for db_path in old_dbs:
        db_name = db_path.name
        # 跳过 WAL/SHM 文件
        if db_name.endswith(('-wal', '-shm')):
            continue

        # 确定人设名
        if db_name == "chatbot.db":
            persona = "default"
        elif db_name == "chatbot_shared.db":
            # 共享心理画像 → data/shared/psychology.db
            shared_dir = data_dir / "shared"
            shared_dir.mkdir(parents=True, exist_ok=True)
            dst = shared_dir / "psychology.db"
            if not dst.exists():
                shutil.copy2(db_path, dst)
                # 同时复制 WAL/SHM
                for suffix in ['-wal', '-shm']:
                    wal = db_path.with_suffix(db_path.suffix + suffix)
                    if wal.exists():
                        shutil.copy2(wal, dst.with_suffix(dst.suffix + suffix))
                print(f"[MIGRATE] 共享心理画像 → shared/psychology.db")
            continue
        elif db_name.startswith("chatbot_") and db_name.endswith(".db"):
            persona = db_name[len("chatbot_"):-len(".db")]
        else:
            continue

        # 迁移这个人设的数据库
        count = _migrate_persona_db(persona, db_path, data_dir)
        migrated_personas.append((persona, count))
        print(f"[MIGRATE] {db_name} → persona={persona}, {count} 个用户账户")

        # 备份原文件
        shutil.copy2(db_path, legacy_dir / db_name)
        for suffix in ['-wal', '-shm']:
            wal = db_path.with_suffix(db_path.suffix + suffix)
            if wal.exists():
                shutil.copy2(wal, legacy_dir / (db_name + suffix))

    # 迁移配置文件
    for yaml_name in ['scenes.yaml', 'tones.yaml', 'relationship_types.yaml']:
        src = data_dir / yaml_name
        if src.exists():
            # 复制到每个已迁移人设的目录下（scenes/tones）
            if yaml_name in ('scenes.yaml', 'tones.yaml'):
                for persona, _ in migrated_personas:
                    persona_dir = data_dir / "personas" / persona
                    persona_dir.mkdir(parents=True, exist_ok=True)
                    dst = persona_dir / yaml_name
                    if not dst.exists():
                        shutil.copy2(src, dst)
            # 备份
            shutil.copy2(src, legacy_dir / yaml_name)

    # 复制 personas/ 下的 yaml 到新版结构
    personas_src = base_dir / "personas"
    if personas_src.exists():
        for yaml_file in personas_src.glob("*.yaml"):
            persona = yaml_file.stem
            persona_dir = data_dir / "personas" / persona
            persona_dir.mkdir(parents=True, exist_ok=True)
            dst = persona_dir / "persona.yaml"
            if not dst.exists():
                shutil.copy2(yaml_file, dst)

    # 写入迁移标记
    with open(flag_file, "w", encoding="utf-8") as f:
        f.write(f"migrated: {datetime.now().isoformat()}\n")
        for persona, count in migrated_personas:
            f.write(f"  {persona}: {count} users\n")

    # 清理 __pycache__
    pycache = base_dir / "__pycache__"
    if pycache.exists():
        try:
            shutil.rmtree(pycache)
        except Exception:
            pass

    msg = f"迁移完成: {', '.join(f'{p}({c}用户)' for p, c in migrated_personas)}"
    print(f"[MIGRATE] {msg}")
    return True, msg


def get_legacy_data_info(data_dir):
    """检测旧版数据目录信息（供 webui 显示）"""
    data_dir = Path(data_dir)
    info = {"is_legacy": False, "dbs": [], "needs_migration": False}

    # 检查是否已迁移
    if (data_dir / "_migrated.flag").exists():
        return info

    # 检测旧版文件
    for db_path in sorted(data_dir.glob("chatbot*.db")):
        if db_path.name.endswith(('-wal', '-shm')):
            continue
        size = db_path.stat().st_size
        info["dbs"].append({"name": db_path.name, "size": size})

    if info["dbs"]:
        info["is_legacy"] = True
        info["needs_migration"] = True

    return info
