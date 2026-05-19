"""
db_paths.py - 新版数据库路径解析器
提供统一的路径查询接口，供 prts_config.py 和数据库 API 使用
"""
from pathlib import Path


class DBPathResolver:
    """新版数据库路径解析器（账户-人设格式）"""

    def __init__(self, base_dir):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.accounts_dir = self.data_dir / "accounts"
        self.personas_dir = self.data_dir / "personas"
        self.shared_dir = self.data_dir / "shared"

    # ========== 用户相关 ==========

    def list_users(self):
        """列出所有用户账户"""
        if not self.accounts_dir.exists():
            return []
        return sorted([
            d.name for d in self.accounts_dir.iterdir()
            if d.is_dir()
        ])

    def list_personas_for_user(self, user_id):
        """列出某个用户下所有人设"""
        user_dir = self.accounts_dir / user_id
        if not user_dir.exists():
            return []
        return sorted([
            d.name for d in user_dir.iterdir()
            if d.is_dir() and (d / "user_data.db").exists()
        ])

    def get_user_db(self, user_id, persona):
        """获取指定用户+人设的数据库路径"""
        return self.accounts_dir / user_id / persona / "user_data.db"

    def get_all_user_dbs(self):
        """获取所有用户数据库 [(user_id, persona, path), ...]"""
        result = []
        if not self.accounts_dir.exists():
            return result
        for user_dir in self.accounts_dir.iterdir():
            if not user_dir.is_dir():
                continue
            for persona_dir in user_dir.iterdir():
                if not persona_dir.is_dir():
                    continue
                db_path = persona_dir / "user_data.db"
                if db_path.exists():
                    result.append((user_dir.name, persona_dir.name, db_path))
        return result

    # ========== 人设相关 ==========

    def list_personas(self):
        """列出所有人设"""
        if not self.personas_dir.exists():
            return []
        return sorted([
            d.name for d in self.personas_dir.iterdir()
            if d.is_dir()
        ])

    def get_persona_global_db(self, persona):
        """获取人设级全局数据库"""
        return self.personas_dir / persona / "global.db"

    def get_persona_yaml(self, persona):
        """获取人设配置文件"""
        return self.personas_dir / persona / "persona.yaml"

    def get_persona_scenes(self, persona):
        """获取人设场景配置"""
        return self.personas_dir / persona / "scenes.yaml"

    def get_persona_tones(self, persona):
        """获取人设语气配置"""
        return self.personas_dir / persona / "tones.yaml"

    # ========== 共享相关 ==========

    def get_shared_psychology_db(self):
        """获取共享心理画像数据库"""
        return self.shared_dir / "psychology.db"

    # ========== 综合查询 ==========

    def get_active_persona(self):
        """从 config.yaml 获取当前活跃人设"""
        try:
            import yaml
            config_path = self.base_dir / "config.yaml"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    config = yaml.safe_load(f) or {}
                return config.get("default_persona", "default")
        except Exception:
            pass
        return "default"

    def get_all_db_paths(self):
        """
        获取所有可用数据库路径（新版结构）
        返回: [{"type": "user"|"persona_global"|"shared", "user": ..., "persona": ..., "path": ...}, ...]
        """
        result = []

        # 用户数据库
        for user_id, persona, path in self.get_all_user_dbs():
            result.append({
                "type": "user",
                "user": user_id,
                "persona": persona,
                "path": path,
            })

        # 人设全局数据库
        for persona in self.list_personas():
            global_db = self.get_persona_global_db(persona)
            if global_db.exists():
                result.append({
                    "type": "persona_global",
                    "user": None,
                    "persona": persona,
                    "path": global_db,
                })

        # 共享心理画像
        shared_db = self.get_shared_psychology_db()
        if shared_db.exists():
            result.append({
                "type": "shared",
                "user": None,
                "persona": None,
                "path": shared_db,
            })

        return result

    def resolve_query_db(self, persona=None, user_id=None):
        """
        根据查询意图解析应该读取的数据库路径列表
        - persona=None, user_id=None → 所有数据库
        - persona=X → 该人设下的所有数据库（全局+所有用户）
        - user_id=Y → 该用户的所有人设数据库
        - persona=X, user_id=Y → 精确匹配单个数据库
        """
        result = []

        if user_id and persona:
            # 精确匹配
            db_path = self.get_user_db(user_id, persona)
            if db_path.exists():
                result.append(db_path)
            global_db = self.get_persona_global_db(persona)
            if global_db.exists():
                result.append(global_db)
            return result

        if persona:
            # 指定人设下所有
            global_db = self.get_persona_global_db(persona)
            if global_db.exists():
                result.append(global_db)
            for uid, pname, path in self.get_all_user_dbs():
                if pname == persona:
                    result.append(path)
            return result

        if user_id:
            # 指定用户下所有人设
            for uid, pname, path in self.get_all_user_dbs():
                if uid == user_id:
                    result.append(path)
            return result

        # 全部
        for entry in self.get_all_db_paths():
            result.append(entry["path"])
        return result
