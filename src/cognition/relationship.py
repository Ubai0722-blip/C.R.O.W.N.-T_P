# by UBAI
"""
relationship.py
关系定制系统 - 模块化设计
支持多种关系类型，每种类型有独立的等级体系、交互规则和人格调整
"""
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from ..memory.database import Database


@dataclass
class LevelInfo:
    """单个等级的信息"""
    level: int
    name: str
    hint: str


@dataclass
class PersonalityConfig:
    """关系人格配置"""
    tone: str = "自然随意"
    intimacy_level: int = 0       # 亲密程度 0-3
    can_flirt: bool = False       # 是否可以调情
    can_jealous: bool = False     # 是否可以吃醋
    pet_names: list[str] = field(default_factory=list)  # 可用称呼


@dataclass
class RelationshipType:
    """关系类型定义"""
    id: str                        # 类型 ID（如 "lover", "bestie"）
    name: str                      # 显示名称
    description: str               # 描述
    levels: dict[int, LevelInfo]   # 等级体系
    exp_multiplier: float = 1.0    # 经验值倍率
    personality: PersonalityConfig = field(default_factory=PersonalityConfig)
    prompt_template: str = ""      # Prompt 模板
    level_up_events: dict[int, str] = field(default_factory=dict)  # 升级事件描述


class RelationshipManager:
    """关系定制管理器"""

    def __init__(self, config_path: str = "data/relationship_types.yaml"):
        self.config_path = Path(config_path)
        self.db = Database()
        self._types: dict[str, RelationshipType] = {}
        self._active_cache: dict[str, str] = {}  # user_id -> type_id
        self._init_table()
        self._load_types()

    def _init_table(self):
        """创建关系类型表"""
        with self.db.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relationship_state (
                    user_id TEXT PRIMARY KEY,
                    type_id TEXT NOT NULL DEFAULT 'default',
                    switched_at TEXT NOT NULL,
                    custom_data TEXT DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 1
                )
            """)
            # 兼容旧数据库：尝试添加 enabled 列（已存在则忽略）
            try:
                conn.execute("ALTER TABLE relationship_state ADD COLUMN enabled INTEGER NOT NULL DEFAULT 1")
            except Exception:
                pass  # 列已存在

    def _load_types(self):
        """从 YAML 加载关系类型配置"""
        if not self.config_path.exists():
            return

        with open(self.config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        for type_id, data in raw.items():
            if type_id.startswith("_"):
                # 以 _ 开头的是默认配置，跳过但可以被引用
                continue

            levels = {}
            for lvl_num, lvl_data in data.get("levels", {}).items():
                levels[int(lvl_num)] = LevelInfo(
                    level=int(lvl_num),
                    name=lvl_data.get("name", f"Lv.{lvl_num}"),
                    hint=lvl_data.get("hint", ""),
                )

            personality_raw = data.get("personality", {})
            personality = PersonalityConfig(
                tone=personality_raw.get("tone", "自然随意"),
                intimacy_level=personality_raw.get("intimacy_level", 0),
                can_flirt=personality_raw.get("can_flirt", False),
                can_jealous=personality_raw.get("can_jealous", False),
                pet_names=personality_raw.get("pet_names", []),
            )

            level_up_events = {}
            for lvl_num, desc in data.get("level_up_events", {}).items():
                level_up_events[int(lvl_num)] = desc

            self._types[type_id] = RelationshipType(
                id=type_id,
                name=data.get("name", type_id),
                description=data.get("description", ""),
                levels=levels,
                exp_multiplier=data.get("exp_multiplier", 1.0),
                personality=personality,
                prompt_template=data.get("prompt_template", ""),
                level_up_events=level_up_events,
            )

    def reload(self):
        """重新加载配置"""
        self._types.clear()
        self._load_types()

    # ========== 查询 ==========

    def list_types(self) -> list[dict]:
        """列出所有可用的关系类型"""
        result = []
        for type_id, rt in self._types.items():
            result.append({
                "id": type_id,
                "name": rt.name,
                "description": rt.description,
                "max_level": max(rt.levels.keys()) if rt.levels else 10,
                "exp_multiplier": rt.exp_multiplier,
            })
        return result

    def get_type(self, type_id: str) -> RelationshipType | None:
        """获取关系类型定义"""
        return self._types.get(type_id)

    def get_active_type_id(self, user_id: str) -> str:
        """获取用户当前激活的关系类型 ID"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT type_id FROM relationship_state WHERE user_id = ?",
                (user_id,),
            ).fetchone()

        type_id = row["type_id"] if row else "default"
        self._active_cache[user_id] = type_id
        return type_id

    def get_active_type(self, user_id: str) -> RelationshipType:
        """获取用户当前的关系类型对象"""
        type_id = self.get_active_type_id(user_id)
        return self._types.get(type_id, self._types.get("default", self._create_fallback()))

    def _create_fallback(self) -> RelationshipType:
        """创建兜底的关系类型"""
        return RelationshipType(
            id="default",
            name="朋友",
            description="普通朋友关系",
            levels={i: LevelInfo(i, f"Lv.{i}", "") for i in range(5, 11)},
        )

    # ========== 切换 ==========

    def set_active_type(self, user_id: str, type_id: str) -> tuple[bool, str]:
        """
        切换用户的关系类型。
        激活一个关系时自动关闭其他关系（互斥逻辑）。
        返回 (success, message)。
        """
        if type_id not in self._types:
            available = ", ".join(self._types.keys())
            return False, f"未知的关系类型：{type_id}\n可用类型：{available}"

        now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.get_conn() as conn:
            # 互斥逻辑：先将该用户所有关系设为禁用
            conn.execute(
                "UPDATE relationship_state SET enabled = 0 WHERE user_id = ?",
                (user_id,),
            )
            # 然后激活目标关系
            conn.execute(
                "INSERT OR REPLACE INTO relationship_state (user_id, type_id, switched_at, enabled) "
                "VALUES (?, ?, ?, 1)",
                (user_id, type_id, now),
            )

        self._active_cache[user_id] = type_id
        rt = self._types[type_id]

        # 写入关系切换记忆
        with self.db.get_conn() as conn:
            conn.execute(
                "INSERT INTO long_term_memory "
                "(user_id, category, content, importance, access_count, created_at, last_accessed) "
                "VALUES (?, ?, ?, ?, 0, ?, ?)",
                (user_id, "关系变化", f"关系类型切换为：{rt.name}", 4, now, now),
            )

        return True, f"关系已切换为：{rt.name}\n{rt.description}"

    def is_type_enabled(self, user_id: str, type_id: str) -> bool:
        """检查某关系类型是否启用"""
        with self.db.get_conn() as conn:
            row = conn.execute(
                "SELECT enabled FROM relationship_state WHERE user_id = ? AND type_id = ?",
                (user_id, type_id),
            ).fetchone()
        return bool(row["enabled"]) if row else False

    def set_type_enabled(self, user_id: str, type_id: str, enabled: bool) -> None:
        """设置某关系类型的启用/禁用状态"""
        now = __import__("datetime").datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self.db.get_conn() as conn:
            existing = conn.execute(
                "SELECT 1 FROM relationship_state WHERE user_id = ? AND type_id = ?",
                (user_id, type_id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE relationship_state SET enabled = ? WHERE user_id = ? AND type_id = ?",
                    (1 if enabled else 0, user_id, type_id),
                )
            else:
                conn.execute(
                    "INSERT INTO relationship_state (user_id, type_id, switched_at, enabled) VALUES (?, ?, ?, ?)",
                    (user_id, type_id, now, 1 if enabled else 0),
                )

    # ========== Prompt 生成 ==========

    def get_relationship_hint(self, user_id: str, level: int) -> str:
        """
        生成关系相关的 Prompt 提示。
        整合了关系类型 + 当前等级 + 人格调整。
        """
        rt = self.get_active_type(user_id)
        level_info = rt.levels.get(level, rt.levels.get(max(rt.levels.keys(), default=5)))

        parts = []

        # 关系类型基础信息
        parts.append(f"[关系定制]")
        parts.append(f"关系类型：{rt.name}")
        parts.append(f"当前等级：{level_info.name}（Lv.{level}）")
        parts.append(f"相处方式：{level_info.hint}")

        # 人格调整
        p = rt.personality
        adjustments = []
        if p.tone:
            adjustments.append(f"语气风格：{p.tone}")
        if p.can_flirt:
            adjustments.append("可以适当调情和撒娇")
        if p.can_jealous:
            adjustments.append("可以吃醋和小情绪")
        if p.pet_names:
            adjustments.append(f"可用称呼：{'、'.join(p.pet_names)}")
        if adjustments:
            parts.append("人格调整：")
            for adj in adjustments:
                parts.append(f"  - {adj}")

        # 关系专属 Prompt
        if rt.prompt_template:
            parts.append(rt.prompt_template.strip())

        return "\n".join(parts)

    def get_level_up_event(self, user_id: str, new_level: int) -> str | None:
        """获取升级事件描述"""
        rt = self.get_active_type(user_id)
        return rt.level_up_events.get(new_level)

    def get_exp_multiplier(self, user_id: str) -> float:
        """获取经验值倍率"""
        rt = self.get_active_type(user_id)
        return rt.exp_multiplier

    # ========== 调试 ==========

    def get_status_text(self, user_id: str) -> str:
        """获取关系状态的可读文本（供 /relationship 命令使用）"""
        rt = self.get_active_type(user_id)
        type_id = self.get_active_type_id(user_id)

        lines = [
            f"💕 关系状态：",
            f"  类型：{rt.name}（{type_id}）",
            f"  描述：{rt.description}",
            f"  经验倍率：{rt.exp_multiplier}x",
        ]

        p = rt.personality
        lines.append(f"\n🎭 人格配置：")
        lines.append(f"  语气：{p.tone}")
        lines.append(f"  亲密等级：{p.intimacy_level}/3")
        lines.append(f"  可调情：{'✅' if p.can_flirt else '❌'}")
        lines.append(f"  可吃醋：{'✅' if p.can_jealous else '❌'}")
        if p.pet_names:
            lines.append(f"  称呼：{'、'.join(p.pet_names)}")

        lines.append(f"\n📊 等级体系：")
        for lvl in sorted(rt.levels.keys()):
            li = rt.levels[lvl]
            lines.append(f"  Lv.{lvl} {li.name}")

        # 可切换的类型
        all_types = self.list_types()
        lines.append(f"\n🔄 可切换类型：")
        for t in all_types:
            marker = " ← 当前" if t["id"] == type_id else ""
            lines.append(f"  {t['id']}: {t['name']}（{t['description']}）{marker}")

        return "\n".join(lines)
