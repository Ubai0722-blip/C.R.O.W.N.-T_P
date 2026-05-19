"""
C.R.O.W.N 个性化配置 Web UI
C.R.O.W.N 风格管理界面 - 《明日方舟》罗德岛终端风格
完全重写版 — 严格遵循 C.R.O.W.N. 设计规范
"""
import os
import json
import yaml
import shutil
import uuid
import tempfile
import logging
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)


class _WebUINoiseFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return "hybridaction" not in message and "zybTracker" not in message


logging.getLogger("werkzeug").addFilter(_WebUINoiseFilter())


# ========== 路径配置 ==========
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
PERSONAS_DIR = BASE_DIR / "personas"
SCENES_PATH = BASE_DIR / "data" / "scenes.yaml"
TONES_PATH = BASE_DIR / "data" / "tones.yaml"
DATA_DIR = BASE_DIR / "data"
EVAL_REPORTS_DIR = DATA_DIR / "eval_reports"
PLUGINS_DIR = BASE_DIR / "src" / "plugins"

# ========== 自动迁移旧版数据 ==========
try:
    from db_migrate import migrate_if_needed
    _migrated, _msg = migrate_if_needed(BASE_DIR)
    if _migrated:
        print(f"[C.R.O.W.N] {_msg}")
except Exception as e:
    print(f"[C.R.O.W.N] 迁移检查失败: {e}")

# ========== 数据库路径解析器 ==========
from db_paths import DBPathResolver
_db_resolver = DBPathResolver(BASE_DIR)

# ========== 自动生成目录结构 ==========
REQUIRED_DIRS = [
    DATA_DIR,
    DATA_DIR / "voice",
    DATA_DIR / "stickers",
    DATA_DIR / "profiles",
    DATA_DIR / "memory",
    DATA_DIR / "life",
    DATA_DIR / "backups",
    EVAL_REPORTS_DIR,
    PERSONAS_DIR,
    PLUGINS_DIR,
    BASE_DIR / "logs",
]

for d in REQUIRED_DIRS:
    d.mkdir(parents=True, exist_ok=True)

# ========== 默认模板 ==========
DEFAULT_CONFIG = {
    "llm": {
        "api_base": "https://token-plan-cn.xiaomimimo.com/v1",
        "api_key": "YOUR_API_KEY",
        "model": "mimo-v2.5-pro",
        "light_model": "mimo-v2.5",
        "max_tokens": 512,
        "temperature": 0.75,
        "timeout": 60.0,
    },
    "tts": {
        "enabled": True,
        "api_base": "https://token-plan-cn.xiaomimimo.com/v1",
        "api_key": "YOUR_API_KEY",
        "model": "mimo-v2.5-tts-voiceclone",
        "reference_audio": "./voice/Theresa.wav",
    },
    "search": {
        "api_key": "YOUR_TAVILY_KEY",
        "max_results": 3,
    },
    "default_persona": "Theresa",
}

DEFAULT_SCENES = {
    "scenes": {
        "comfort": {"name": "安慰陪伴", "description": "用户难过时", "trigger_hint": "用户表达负面情绪", "tone": "gentle_comfort", "extra_hint": "如果用户不想说，不要追问"},
        "casual": {"name": "日常闲聊", "description": "普通闲聊", "trigger_hint": "轻松日常对话", "tone": "casual_lazy", "extra_hint": "回复简短自然"},
        "deep_talk": {"name": "深夜谈心", "description": "深入话题", "trigger_hint": "涉及人生意义选择", "tone": "deep_sincere", "extra_hint": "不要回避沉重话题"},
    }
}

DEFAULT_TONES = {
    "tones": {
        "gentle_comfort": {"name": "温柔安慰", "description": "对方难过时", "style": "语气温柔，先认同感受", "verbal_tics": ["没事的", "我在呢"], "sentence_pattern": "短句少问句"},
        "casual_lazy": {"name": "随意懒散", "description": "日常闲聊", "style": "最放松的状态", "verbal_tics": ["嗯", "噢"], "sentence_pattern": "极短"},
        "deep_sincere": {"name": "真诚深聊", "description": "深入话题", "style": "认真对待", "verbal_tics": ["说实话", "我也想过"], "sentence_pattern": "可以长一点"},
    }
}

DEFAULT_PERSONA = {
    "name": "Theresa",
    "color": "#ffffff",
    "identity": {
        "description": "自由插画师",
        "personality": "温和、有耐心",
        "background": "视觉传达专业毕业",
    },
    "speaking_style": {
        "tone": "温和随意",
        "verbal_tics": ["嗯", "啊"],
        "vocabulary_level": "日常",
        "emoji_usage": "偶尔",
        "sentence_length": "短句为主",
        "core_principles": "像真人发消息",
    },
    "behavior": {"rules": ["永远不要跳出角色"], "greeting": "嗯？来了啊"},
    "knowledge": {"scope": "画画、游戏、日常", "opinions": []},
    "examples": [{"user": "在干嘛？", "assistant": "画画"}],
}

# 自动生成缺失文件
if not CONFIG_PATH.exists():
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_CONFIG, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"[C.R.O.W.N] 已生成默认 config.yaml")

if not SCENES_PATH.exists():
    with open(SCENES_PATH, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_SCENES, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"[C.R.O.W.N] 已生成默认 scenes.yaml")

if not TONES_PATH.exists():
    with open(TONES_PATH, "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_TONES, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"[C.R.O.W.N] 已生成默认 tones.yaml")

if not any(PERSONAS_DIR.glob("*.yaml")):
    with open(PERSONAS_DIR / "Theresa.yaml", "w", encoding="utf-8") as f:
        yaml.dump(DEFAULT_PERSONA, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"[C.R.O.W.N] 已生成默认 Theresa.yaml")


def load_yaml(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def check_backups_limit(backup_dir, max_backups=50):
    """备份文件数量限制，超出时删除最早的"""
    try:
        backups = sorted(backup_dir.glob("*"), key=lambda f: f.stat().st_mtime)
        while len(backups) > max_backups:
            oldest = backups.pop(0)
            oldest.unlink(missing_ok=True)
    except Exception:
        pass


def save_yaml(path, data):
    backup_dir = BASE_DIR / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{path.suffix}"
    backup = backup_dir / backup_name
    if path.exists():
        shutil.copy2(path, backup)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    check_backups_limit(backup_dir)


def load_persona(name):
    path = PERSONAS_DIR / f"{name}.yaml"
    if path.exists():
        return load_yaml(path)
    return {}


def save_persona(name, data):
    path = PERSONAS_DIR / f"{name}.yaml"
    backup_dir = BASE_DIR / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_name = f"{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.yaml"
    if path.exists():
        shutil.copy2(path, backup_dir / backup_name)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    check_backups_limit(backup_dir)


def get_active_db_path():
    """获取当前活跃人设的数据库路径（新版结构优先，回退旧版）"""
    try:
        persona = _db_resolver.get_active_persona()
        if persona and persona != "default":
            # 新版结构：查找人设全局数据库
            global_db = _db_resolver.get_persona_global_db(persona)
            if global_db.exists():
                return global_db
            # 回退旧版结构
            persona_db = DATA_DIR / f"chatbot_{persona}.db"
            if persona_db.exists():
                return persona_db
    except Exception:
        pass
    return DATA_DIR / "chatbot.db"

def get_all_db_paths():
    """获取所有可用的数据库路径（新版+旧版兼容）"""
    paths = []
    for entry in _db_resolver.get_all_db_paths():
        paths.append((entry.get("persona", entry.get("user", "unknown")), entry["path"]))
    # 回退：如果新版目录不存在，扫描旧版
    if not paths:
        main_db = DATA_DIR / "chatbot.db"
        if main_db.exists():
            paths.append(("default", main_db))
        for db_file in sorted(DATA_DIR.glob("chatbot_*.db")):
            if db_file.name == "chatbot_shared.db":
                continue
            persona = db_file.stem.replace("chatbot_", "")
            paths.append((persona, db_file))
        shared_db = DATA_DIR / "chatbot_shared.db"
        if shared_db.exists():
            paths.append(("shared", shared_db))
    return paths


@app.route("/api/config", methods=["GET"])
def get_config():
    return jsonify(load_yaml(CONFIG_PATH))


@app.route("/api/config", methods=["POST"])
def save_config():
    data = request.json
    current_config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    def deep_update(d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                deep_update(d[k], v)
            else:
                d[k] = v
    deep_update(current_config, data)
    save_yaml(CONFIG_PATH, current_config)
    return jsonify({"ok": True, "msg": "config.yaml 已保存"})


@app.route("/api/personas", methods=["GET"])
def list_personas():
    return jsonify([p.stem for p in PERSONAS_DIR.glob("*.yaml")])


@app.route("/api/persona/<name>", methods=["GET"])
def get_persona(name):
    return jsonify(load_persona(name))


@app.route("/api/persona/<name>", methods=["POST"])
def save_persona_route(name):
    data = request.json
    save_persona(name, data)
    return jsonify({"ok": True, "msg": f"{name}.yaml 已保存"})


@app.route("/api/scenes", methods=["GET"])
def get_scenes():
    return jsonify(load_yaml(SCENES_PATH))


@app.route("/api/scenes", methods=["POST"])
def save_scenes():
    data = request.json
    save_yaml(SCENES_PATH, data)
    return jsonify({"ok": True, "msg": "scenes.yaml 已保存"})


@app.route("/api/tones", methods=["GET"])
def get_tones():
    return jsonify(load_yaml(TONES_PATH))


@app.route("/api/tones", methods=["POST"])
def save_tones():
    data = request.json
    save_yaml(TONES_PATH, data)
    return jsonify({"ok": True, "msg": "tones.yaml 已保存"})


@app.route("/api/stats", methods=["GET"])
def get_stats():
    db_path = get_active_db_path()
    voice_dir = DATA_DIR / "voice"
    sticker_dir = DATA_DIR / "stickers"
    backup_dir = DATA_DIR / "backups"
    scenes_data = load_yaml(SCENES_PATH) if SCENES_PATH.exists() else {}
    tones_data = load_yaml(TONES_PATH) if TONES_PATH.exists() else {}
    # 收集所有数据库大小（新版结构）
    total_db_size = 0
    db_files = []
    for entry in _db_resolver.get_all_db_paths():
        p = entry["path"]
        sz = p.stat().st_size if p.exists() else 0
        total_db_size += sz
        db_files.append({
            "name": p.name,
            "type": entry["type"],
            "user": entry.get("user"),
            "persona": entry.get("persona"),
            "size": sz,
        })
    # 回退旧版
    if not db_files:
        for persona, dbp in get_all_db_paths():
            sz = dbp.stat().st_size if dbp.exists() else 0
            total_db_size += sz
            db_files.append({"name": dbp.name, "persona": persona, "size": sz})

    stats = {
        "db_size": total_db_size,
        "active_db": db_path.name,
        "db_files": db_files,
        "voice_count": len(list(voice_dir.glob("*.silk"))) if voice_dir.exists() else 0,
        "sticker_count": len(list(sticker_dir.glob("*"))) if sticker_dir.exists() else 0,
        "persona_count": len(list(PERSONAS_DIR.glob("*.yaml"))),
        "backup_count": len(list(backup_dir.glob("*"))) if backup_dir.exists() else 0,
        "scenes_count": len(scenes_data.get("scenes", {})),
        "tones_count": len(tones_data.get("tones", {})),
    }
    return jsonify(stats)


@app.route("/api/backups", methods=["GET"])
def list_backups():
    backup_dir = DATA_DIR / "backups"
    if not backup_dir.exists():
        return jsonify([])
    files = sorted(backup_dir.glob("*"), key=lambda f: f.stat().st_mtime, reverse=True)
    return jsonify([{"name": f.name, "size": f.stat().st_size, "time": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")} for f in files[:50]])


@app.route("/api/path/status", methods=["GET"])
def path_status():
    import subprocess
    result = subprocess.run("echo %PATH%", shell=True, capture_output=True, text=True)
    user_path = result.stdout.strip()
    project_dir = str(BASE_DIR).rstrip("\\")
    in_path = project_dir in user_path
    return jsonify({"in_path": in_path, "project_dir": project_dir})


@app.route("/api/path/register", methods=["POST"])
def register_path():
    import subprocess
    project_dir = str(BASE_DIR).rstrip("\\")
    result = subprocess.run(
        'reg query "HKCU\\Environment" /v Path',
        shell=True, capture_output=True, text=True
    )
    current_path = ""
    for line in result.stdout.split("\n"):
        if "Path" in line and "REG_" in line:
            parts = line.split("    ")
            if len(parts) >= 3:
                current_path = parts[-1].strip()
    if project_dir not in current_path:
        new_path = f"{current_path};{project_dir}" if current_path else project_dir
        subprocess.run(
            f'reg add "HKCU\\Environment" /v Path /t REG_EXPAND_SZ /d "{new_path}" /f',
            shell=True, capture_output=True
        )
        return jsonify({"ok": True, "msg": f"已注册到 PATH: {project_dir}"})
    return jsonify({"ok": True, "msg": "PATH 已包含当前目录"})


@app.route("/api/persona/reset", methods=["POST"])
def reset_persona():
    """恢复默认人格"""
    data = request.json or {}
    persona_name = data.get("name", "Theresa")
    save_persona(persona_name, DEFAULT_PERSONA)
    return jsonify({"ok": True, "msg": f"{persona_name}.yaml 已恢复默认"})


@app.route("/api/persona/create", methods=["POST"])
def create_persona():
    """创建新人设"""
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "msg": "名称不能为空"})
    path = PERSONAS_DIR / f"{name}.yaml"
    if path.exists():
        return jsonify({"ok": False, "msg": f"人设 {name} 已存在"})
    import copy
    new_persona = copy.deepcopy(DEFAULT_PERSONA)
    new_persona["name"] = name
    new_persona["identity"]["description"] = "待填写"
    new_persona["identity"]["personality"] = "待填写"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(new_persona, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    # 为新人设初始化多维性格基线
    try:
        from src.cognition.personality_dimensions import PersonalityDimensionManager
        mgr = PersonalityDimensionManager()
        dims = mgr.analyze_from_persona(name, new_persona)
        mgr.save_dimensions(name, dims, source="baseline", note="创建人设时自动生成")
    except Exception:
        pass
    # 为新人设初始化心理画像基线
    try:
        from src.cognition.persona_psychology import PersonaPsychologyManager
        pmgr = PersonaPsychologyManager()
        pmgr.create_baseline(name, new_persona)
    except Exception:
        pass
    return jsonify({"ok": True, "msg": f"人设 {name} 已创建"})


@app.route("/api/persona/switch_active", methods=["POST"])
def switch_active_persona():
    """切换默认活跃人设（重启后生效）"""
    data = request.json or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"ok": False, "msg": "人设名称不能为空"})
    path = PERSONAS_DIR / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": f"人设 {name} 不存在"})
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    config["default_persona"] = name
    save_yaml(CONFIG_PATH, config)
    return jsonify({"ok": True, "msg": f"默认人设已切换为 {name}，重启后生效"})


@app.route("/api/persona/import_zip", methods=["POST"])
def import_persona_zip():
    """从压缩包导入人设、场景组、语气组、音频组"""
    import zipfile, tempfile, shutil as sh
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "未收到文件"})
    f = request.files['file']
    if not f.filename:
        return jsonify({"ok": False, "msg": "文件名为空"})
    suffix = Path(f.filename).suffix.lower()
    if suffix not in ('.zip', '.rar', '.7z'):
        return jsonify({"ok": False, "msg": "仅支持 zip/rar/7z 格式"})
    # 保存到临时目录
    tmp_dir = Path(tempfile.mkdtemp(prefix="crown_import_"))
    tmp_file = tmp_dir / f.filename
    f.save(tmp_file)
    imported = []
    skipped = []
    errors = []
    try:
        # 解压
        extract_dir = tmp_dir / "extracted"
        extract_dir.mkdir()
        if suffix == '.zip':
            with zipfile.ZipFile(tmp_file, 'r') as zf:
                zf.extractall(extract_dir)
        else:
            # rar/7z 用 Python 尝试
            try:
                import rarfile
                with rarfile.RarFile(tmp_file) as rf:
                    rf.extractall(extract_dir)
            except ImportError:
                return jsonify({"ok": False, "msg": "需要安装 rarfile 库才能解压 rar/7z 文件"})
        # 遍历解压后的文件
        persona_found = False
        for root, dirs, files in os.walk(extract_dir):
            for fname in files:
                fpath = Path(root) / fname
                rel = fpath.relative_to(extract_dir)
                rel_str = str(rel).replace('\\', '/')
                # 检测人设文件（在 personas/ 目录下或根目录的 .yaml）
                if fname.endswith('.yaml') or fname.endswith('.yml'):
                    try:
                        data = load_yaml(fpath)
                    except Exception:
                        continue
                    if not isinstance(data, dict):
                        continue
                    # 判断是人设文件还是场景/语气文件
                    if 'name' in data and ('identity' in data or 'speaking_style' in data or 'behavior' in data):
                        # 人设文件
                        persona_name = data.get('name', fpath.stem)
                        # 用文件名作为标识
                        dest_name = fpath.stem
                        dest = PERSONAS_DIR / f"{dest_name}.yaml"
                        sh.copy2(fpath, dest)
                        imported.append(f"人设: {dest_name}.yaml")
                        persona_found = True
                    elif 'scenes' in data:
                        # 场景组文件
                        dest = DATA_DIR / "scene_groups" / fname
                        sh.copy2(fpath, dest)
                        imported.append(f"场景组: {fname}")
                    elif 'tones' in data:
                        # 语气组文件
                        dest = DATA_DIR / "tone_groups" / fname
                        sh.copy2(fpath, dest)
                        imported.append(f"语气组: {fname}")
                # 检测音频文件
                elif fname.endswith('.wav') or fname.endswith('.mp3') or fname.endswith('.silk'):
                    # 尝试从路径推断音频组名
                    parts = list(rel.parts)
                    if len(parts) >= 2:
                        group_name = parts[0] if len(parts) > 1 else "imported"
                    else:
                        group_name = "imported"
                    audio_dir = DATA_DIR / "audio_groups" / group_name
                    audio_dir.mkdir(parents=True, exist_ok=True)
                    dest = audio_dir / fname
                    sh.copy2(fpath, dest)
                    imported.append(f"音频: {group_name}/{fname}")
        if not persona_found:
            # 检查是否有子目录包含人设文件
            for root, dirs, files in os.walk(extract_dir):
                for fname in files:
                    if fname.endswith('.yaml'):
                        fpath = Path(root) / fname
                        try:
                            data = load_yaml(fpath)
                            if isinstance(data, dict) and 'name' in data:
                                dest_name = fpath.stem
                                dest = PERSONAS_DIR / f"{dest_name}.yaml"
                                sh.copy2(fpath, dest)
                                imported.append(f"人设: {dest_name}.yaml")
                                persona_found = True
                                break
                        except Exception:
                            continue
                if persona_found:
                    break
        if not persona_found:
            errors.append("未检测到人设文件（必须包含 name 和 identity/speaking_style 字段）")
    except zipfile.BadZipFile:
        errors.append("压缩包格式损坏")
    except Exception as e:
        errors.append(f"导入失败: {str(e)[:200]}")
    finally:
        try:
            sh.rmtree(tmp_dir)
        except Exception:
            pass
    if errors and not imported:
        return jsonify({"ok": False, "msg": "; ".join(errors)})
    msg = f"导入完成: {len(imported)} 项"
    if imported:
        msg += "\n" + "\n".join(imported)
    if skipped:
        msg += f"\n跳过: {len(skipped)} 项"
    if errors:
        err_text = '; '.join(errors)
        msg += f"\n警告: {err_text}"
    return jsonify({"ok": True, "msg": msg})


@app.route("/api/config/reset", methods=["POST"])
def reset_config():
    """清空所有配置为默认值"""
    save_yaml(CONFIG_PATH, DEFAULT_CONFIG)
    save_yaml(SCENES_PATH, DEFAULT_SCENES)
    save_yaml(TONES_PATH, DEFAULT_TONES)
    return jsonify({"ok": True, "msg": "config.yaml / scenes.yaml / tones.yaml 已重置为默认值"})


@app.route("/api/plugins", methods=["GET"])
def list_plugins():
    """扫描插件目录，解析真实插件信息"""
    import ast
    plugins = []
    state_file = BASE_DIR / "plugin_states.json"
    states = {}
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                states = json.load(f)
        except Exception:
            pass

    scan_dirs = [
        PLUGINS_DIR / "builtin",
        PLUGINS_DIR / "custom",
    ]

    for scan_dir in scan_dirs:
        if not scan_dir.exists():
            continue
        for item in sorted(scan_dir.iterdir()):
            if not item.is_dir():
                continue
            init_file = item / "__init__.py"
            if not init_file.exists():
                continue

            info = {
                "name": item.name,
                "version": "1.0.0",
                "description": "",
                "author": "",
                "triggers": [],
                "priority": 50,
                "require_prefix": True,
                "path": str(item.relative_to(BASE_DIR)),
                "enabled": states.get(item.name, False),
                "location": "builtin" if "builtin" in str(scan_dir) else "custom",
            }

            manifest = item / "manifest.yaml"
            if manifest.exists():
                try:
                    m = load_yaml(manifest)
                    if m:
                        info["description"] = m.get("description", info["description"])
                        info["author"] = m.get("author", info["author"])
                        info["version"] = m.get("version", info["version"])
                        if m.get("enabled") is False:
                            info["enabled"] = False
                except Exception:
                    pass

            try:
                with open(init_file, "r", encoding="utf-8") as f:
                    source = f.read()
                tree = ast.parse(source)
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        for item_node in node.body:
                            if isinstance(item_node, ast.FunctionDef) and item_node.name == "get_info":
                                for stmt in ast.walk(item_node):
                                    if isinstance(stmt, ast.keyword):
                                        if stmt.arg == "name" and isinstance(stmt.value, ast.Constant):
                                            info["name"] = stmt.value.value
                                        elif stmt.arg == "version" and isinstance(stmt.value, ast.Constant):
                                            info["version"] = stmt.value.value
                                        elif stmt.arg == "description" and isinstance(stmt.value, ast.Constant):
                                            info["description"] = stmt.value.value
                                        elif stmt.arg == "author" and isinstance(stmt.value, ast.Constant):
                                            info["author"] = stmt.value.value
                                        elif stmt.arg == "priority" and isinstance(stmt.value, ast.Constant):
                                            info["priority"] = stmt.value.value
                                        elif stmt.arg == "require_prefix" and isinstance(stmt.value, ast.Constant):
                                            info["require_prefix"] = stmt.value.value
                                        elif stmt.arg == "triggers" and isinstance(stmt.value, ast.List):
                                            info["triggers"] = [
                                                elt.value for elt in stmt.value.elts
                                                if isinstance(elt, ast.Constant)
                                            ]
            except Exception:
                pass

            plugins.append(info)

    plugins.sort(key=lambda x: x["priority"])
    return jsonify(plugins)


@app.route("/api/plugin/upload", methods=["POST"])
def upload_plugin():
    """上传插件压缩包"""
    import zipfile
    import io
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "未收到文件"})
    file = request.files['file']
    if not file.filename.endswith('.zip'):
        return jsonify({"ok": False, "msg": "仅支持 .zip 格式"})
    custom_dir = PLUGINS_DIR / "custom"
    custom_dir.mkdir(parents=True, exist_ok=True)
    try:
        zip_data = io.BytesIO(file.read())
        with zipfile.ZipFile(zip_data) as zf:
            # 检查插件结构
            names = zf.namelist()
            # 找到插件根目录（包含 __init__.py 的目录）
            plugin_root = None
            for name in names:
                if name.endswith('__init__.py'):
                    parts = name.split('/')
                    if len(parts) >= 2:
                        plugin_root = parts[0]
                    break
            if not plugin_root:
                return jsonify({"ok": False, "msg": "压缩包内未找到 __init__.py，不是有效插件"})
            target_dir = custom_dir / plugin_root
            if target_dir.exists():
                import shutil
                shutil.rmtree(target_dir)
            zf.extractall(str(custom_dir))
        return jsonify({"ok": True, "msg": f"插件 {plugin_root} 已安装到 src/plugins/custom/"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"解压失败: {e}"})


@app.route("/api/plugin/toggle", methods=["POST"])
def toggle_plugin():
    """开关插件 - 写入 plugin_states.json"""
    data = request.json
    name = data.get("name", "")
    enabled = data.get("enabled", True)

    state_file = BASE_DIR / "plugin_states.json"
    states = {}
    if state_file.exists():
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                states = json.load(f)
        except Exception:
            pass

    states[name] = enabled
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(states, f, ensure_ascii=False, indent=4)
        return jsonify({"ok": True, "msg": f"插件 {name} 已{'启用' if enabled else '禁用'}（重启机器人后生效）"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"保存失败: {e}"})


@app.route("/api/plugins/reload", methods=["POST"])
def reload_plugin():
    """重载插件状态（从 plugin_states.json 重新读取）"""
    return jsonify({"ok": True, "msg": "插件状态已刷新"})


@app.route("/api/file/<path:filepath>", methods=["GET"])
def get_file(filepath):
    """读取项目文件内容（安全限制在 BASE_DIR 内）"""
    try:
        target = (BASE_DIR / filepath).resolve()
        if not str(target).startswith(str(BASE_DIR.resolve())):
            return jsonify({"ok": False, "msg": "禁止访问项目目录外的文件"}), 403
        if not target.exists():
            return jsonify({"ok": False, "msg": f"文件不存在: {filepath}"}), 404
        if target.stat().st_size > 512 * 1024:
            return jsonify({"ok": False, "msg": "文件过大（>512KB）"}), 413
        content = target.read_text(encoding="utf-8", errors="replace")
        return jsonify({"ok": True, "path": filepath, "content": content})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/api/readme", methods=["GET"])
def get_readme():
    """读取 README.md 内容"""
    readme_path = BASE_DIR / "README.md"
    if readme_path.exists():
        return jsonify({"content": readme_path.read_text(encoding="utf-8")})
    return jsonify({"content": "README.md 未找到"})


# ========== 前端 ==========


@app.route("/api/heartbeat", methods=["POST"])
def heartbeat():
    """浏览器心跳 - 用于检测浏览器关闭"""
    import threading
    global _last_heartbeat
    _last_heartbeat = datetime.now().timestamp()
    return jsonify({"ok": True})

_last_heartbeat = datetime.now().timestamp()
_server_start_time = datetime.now().timestamp()

def _auto_shutdown_check():
    """定期检查心跳，如果浏览器超过10分钟没发心跳就关闭服务（启动后5分钟内不检查）"""
    import time, os
    global _last_heartbeat
    while True:
        time.sleep(30)
        # 启动后5分钟内不检查（给用户时间打开浏览器）
        if datetime.now().timestamp() - _server_start_time < 300:
            continue
        elapsed = datetime.now().timestamp() - _last_heartbeat
        if elapsed > 600:
            print("[C.R.O.W.N] 浏览器已关闭，自动停止服务...")
            os._exit(0)


# ========== 数据库管理 ==========
@app.route("/api/db/clear", methods=["POST"])
def clear_all_databases():
    """清空全部数据库和运行时数据（跳过受保护文件）"""
    import glob
    cleared = []
    errors = []
    skipped = []

    # 读取受保护文件列表
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    protected = set(config.get("protected_files", []))

    # 清空所有 SQLite 数据库
    import sqlite3
    db_files = []
    # 主数据库
    for db_file in DATA_DIR.glob("*.db"):
        if db_file.name.endswith("-shm") or db_file.name.endswith("-wal"):
            continue
        db_files.append(db_file)
    # accounts 目录下的数据库
    accounts_dir = DATA_DIR / "accounts"
    if accounts_dir.exists():
        for db_file in accounts_dir.rglob("*.db"):
            if not db_file.name.endswith("-shm") and not db_file.name.endswith("-wal"):
                db_files.append(db_file)
    # personas 目录下的全局数据库
    personas_data_dir = DATA_DIR / "personas"
    if personas_data_dir.exists():
        for db_file in personas_data_dir.rglob("*.db"):
            if not db_file.name.endswith("-shm") and not db_file.name.endswith("-wal"):
                db_files.append(db_file)
    # shared 目录下的数据库
    shared_dir = DATA_DIR / "shared"
    if shared_dir.exists():
        for db_file in shared_dir.rglob("*.db"):
            if not db_file.name.endswith("-shm") and not db_file.name.endswith("-wal"):
                db_files.append(db_file)
    # 逐个清空
    for db_path in db_files:
        try:
            conn = sqlite3.connect(str(db_path))
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            for (table,) in tables:
                if table != 'sqlite_master':
                    conn.execute(f"DELETE FROM [{table}]")
            conn.commit()
            conn.close()
            rel = str(db_path.relative_to(BASE_DIR)).replace('\\', '/')
            cleared.append(f"{rel} (所有表已清空)")
        except Exception as e:
            rel = str(db_path.relative_to(BASE_DIR)).replace('\\', '/')
            errors.append(f"{rel}: {e}")

    # 清空 JSON 数据文件
    for pattern in ["data/profiles/*.json", "data/memory/*.json", "data/life/*.json"]:
        for f in glob.glob(str(BASE_DIR / pattern)):
            rel = str(Path(f).relative_to(BASE_DIR)).replace('\\', '/')
            if rel in protected:
                skipped.append(rel)
                continue
            try:
                os.remove(f)
                cleared.append(os.path.basename(f))
            except Exception as e:
                errors.append(f"{os.path.basename(f)}: {e}")

    # 清空语音文件
    voice_dir = DATA_DIR / "voice"
    if voice_dir.exists():
        for f in voice_dir.glob("*.silk"):
            try:
                f.unlink()
                cleared.append(f.name)
            except:
                pass

    # 清空表情包
    sticker_dir = DATA_DIR / "stickers"
    if sticker_dir.exists():
        for f in sticker_dir.glob("*"):
            try:
                f.unlink()
                cleared.append(f.name)
            except:
                pass

    # 清空备份（跳过受保护的）
    backup_dir = DATA_DIR / "backups"
    if backup_dir.exists():
        for f in backup_dir.glob("*"):
            rel = str(f.relative_to(BASE_DIR)).replace('\\', '/')
            if rel in protected:
                skipped.append(rel)
                continue
            try:
                f.unlink()
                cleared.append(f.name)
            except:
                pass

    msg = f"已清空 {len(cleared)} 个文件/表"
    if skipped:
        msg += f"，跳过 {len(skipped)} 个受保护文件"
    if errors:
        msg += f"，{len(errors)} 个错误"
    return jsonify({"ok": True, "msg": msg, "cleared": len(cleared), "skipped": skipped, "errors": errors})


# ========== AI 状态 ==========
@app.route("/api/ai/status", methods=["GET"])
def get_ai_status():
    """读取 AI 当前实时状态"""
    import sqlite3
    status = {
        "emotion": {"mood_value": 0, "dominant": "平静", "last": "平静", "streak": 0},
        "growth": {"level": 5, "level_name": "好友", "exp": 0, "messages": 0, "days": 0, "shared": 0, "bonds": 0},
        "persona": "unknown",
        "user_id": "",
        "recent_moods": [],
        "recent_topics": [],
        "lover_mode": False,
        "tts_model": "",
        "llm_model": "",
    }

    # 读取当前配置
    try:
        config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
        status["persona"] = config.get("default_persona", "unknown")
        status["llm_model"] = config.get("llm", {}).get("model", "N/A")
        status["tts_model"] = config.get("tts", {}).get("model", "N/A")
    except Exception:
        pass

    # 优先读取人设专用数据库
    persona = status.get("persona", "")
    persona_db = DATA_DIR / f"chatbot_{persona}.db"
    db_path = persona_db if persona_db.exists() else DATA_DIR / "chatbot.db"
    if not db_path.exists():
        return jsonify(status)

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # 情绪状态
        row = conn.execute("SELECT * FROM emotion_state LIMIT 1").fetchone()
        if row:
            keys = row.keys()
            status["emotion"]["mood_value"] = row["mood_value"] if "mood_value" in keys else 0
            status["emotion"]["dominant"] = row["dominant_emotion"] if "dominant_emotion" in keys else "平静"
            status["emotion"]["last"] = row["last_emotion"] if "last_emotion" in keys else "平静"
            status["emotion"]["streak"] = row["streak_count"] if "streak_count" in keys else 0
            status["user_id"] = row["user_id"] if "user_id" in keys else ""

        # 成长状态
        row = conn.execute("SELECT * FROM user_profiles LIMIT 1").fetchone()
        if row:
            keys = row.keys()
            level = row["relationship_level"] if "relationship_level" in keys else 5
            level_names = {5:"好友",6:"亲近的朋友",7:"好朋友",8:"挚友",9:"最重要的人",10:"无可替代"}
            status["growth"]["level"] = level
            status["growth"]["level_name"] = level_names.get(level, "好友")
            status["growth"]["exp"] = row["relationship_exp"] if "relationship_exp" in keys else 0
            status["growth"]["messages"] = row["total_messages"] if "total_messages" in keys else 0
            status["growth"]["days"] = row["total_days"] if "total_days" in keys else 0
            status["growth"]["shared"] = row["shared_experiences"] if "shared_experiences" in keys else 0
            status["growth"]["bonds"] = row["emotional_bonds"] if "emotional_bonds" in keys else 0

        # 恋人模式
        row = conn.execute("SELECT value FROM evolution_state WHERE key='lover_mode' LIMIT 1").fetchone()
        status["lover_mode"] = row["value"] == "true" if row else True

        # 最近情绪趋势
        rows = conn.execute("SELECT emotion FROM mood_history ORDER BY id DESC LIMIT 5").fetchall()
        status["recent_moods"] = [r["emotion"] for r in rows]

        # 最近话题
        rows = conn.execute("SELECT category, count FROM favorite_topics ORDER BY count DESC LIMIT 3").fetchall()
        status["recent_topics"] = [f"{r['category']}({r['count']})" for r in rows]

        conn.close()
    except Exception as e:
        status["error"] = str(e)

    return jsonify(status)


# ========== 重启机器人 ==========
@app.route("/api/bot/restart", methods=["POST"])
def restart_bot():
    """重启文明（重启聊天ai）"""
    import subprocess, time, threading
    bot_dir = str(BASE_DIR)
    napcat_dir = BASE_DIR / "NapCat"

    def _do_restart():
        # 杀掉 NoneBot
        subprocess.run(['taskkill', '/F', '/FI', 'WINDOWTITLE eq CROWN-Bot*'], capture_output=True, timeout=5)
        # 杀掉 NapCat
        subprocess.run(['taskkill', '/F', '/FI', 'WINDOWTITLE eq NapCat*'], capture_output=True, timeout=5)
        time.sleep(1)
        # 重新启动 NapCat（检查目录是否存在）
        if napcat_dir.exists():
            node_path = BASE_DIR / "nodejs" / "node.exe"
            if node_path.exists():
                node_cmd = f"set PATH={str(BASE_DIR / 'nodejs')};%PATH% && "
            else:
                node_cmd = ""
            napcat_script = napcat_dir / "napcat.mjs"
            if napcat_script.exists():
                subprocess.Popen(
                    f'start "NapCat" cmd /c "cd /d {str(napcat_dir)} && {node_cmd}node napcat.mjs"',
                    shell=True
                )
            else:
                # 尝试 napcat.js
                napcat_js = napcat_dir / "napcat.js"
                if napcat_js.exists():
                    subprocess.Popen(
                        f'start "NapCat" cmd /c "cd /d {str(napcat_dir)} && {node_cmd}node napcat.js"',
                        shell=True
                    )
                else:
                    print("[WARN] NapCat 脚本不存在，跳过启动")
        else:
            print(f"[WARN] NapCat 目录不存在: {napcat_dir}")
        time.sleep(3)
        # 重新启动 NoneBot
        venv_python = BASE_DIR / "venv" / "Scripts" / "python.exe"
        if venv_python.exists():
            subprocess.Popen(
                f'start "CROWN-Bot" cmd /k "cd /d {bot_dir} && venv\\Scripts\\python.exe qq_bot.py"',
                shell=True
            )
        else:
            subprocess.Popen(
                f'start "CROWN-Bot" cmd /k "cd /d {bot_dir} && python qq_bot.py"',
                shell=True
            )

    threading.Thread(target=_do_restart, daemon=True).start()
    return jsonify({"ok": True, "msg": "重启文明启动中..."})


# ========== 重启 WebUI ==========
@app.route("/api/webui/restart", methods=["POST"])
def restart_webui():
    """重启 WebUI 服务"""
    import threading
    import time
    def _restart():
        time.sleep(1)
        os._exit(0)
    # 启动脚本会自动重启
    threading.Thread(target=_restart, daemon=True).start()
    return jsonify({"ok": True, "msg": "WebUI 正在重启..."})



# ========== 备份管理 ==========
@app.route("/api/backup/generate", methods=["POST"])
def generate_backup():
    """手动创建备份"""
    import shutil
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backed = []
    targets = [
        (CONFIG_PATH, f"config_{ts}.yaml"),
        (SCENES_PATH, f"scenes_{ts}.yaml"),
        (TONES_PATH, f"tones_{ts}.yaml"),
    ]
    for persona_file in PERSONAS_DIR.glob("*.yaml"):
        targets.append((persona_file, f"persona_{persona_file.stem}_{ts}.yaml"))
    for src, name in targets:
        if src.exists():
            shutil.copy2(src, backup_dir / name)
            backed.append(name)
    check_backups_limit(backup_dir)
    return jsonify({"ok": True, "msg": f"已创建 {len(backed)} 个备份", "files": backed})

@app.route("/api/backup/delete", methods=["POST"])
def delete_backup():
    """删除指定备份文件"""
    data = request.json
    name = data.get("name", "")
    if not name or ".." in name or "/" in name:
        return jsonify({"ok": False, "msg": "无效文件名"})
    path = DATA_DIR / "backups" / name
    if path.exists():
        path.unlink()
        return jsonify({"ok": True, "msg": f"已删除 {name}"})
    return jsonify({"ok": False, "msg": "文件不存在"})

@app.route("/api/backup/import", methods=["POST"])
def import_backup():
    """导入备份文件（恢复配置）"""
    import shutil
    data = request.json
    name = data.get("name", "")
    if not name or ".." in name or "/" in name:
        return jsonify({"ok": False, "msg": "无效文件名"})
    src = DATA_DIR / "backups" / name
    if not src.exists():
        return jsonify({"ok": False, "msg": "备份文件不存在"})
    # 根据文件名判断目标
    dst = _resolve_backup_target(name)
    if dst is None:
        return jsonify({"ok": False, "msg": "无法识别备份类型"})
    shutil.copy2(src, dst)
    return jsonify({"ok": True, "msg": f"已恢复 {name} → {dst.name}"})


def _resolve_backup_target(name: str):
    """根据备份文件名解析恢复目标路径"""
    if "config" in name:
        return CONFIG_PATH
    elif "scenes" in name:
        return SCENES_PATH
    elif "tones" in name:
        return TONES_PATH
    elif "persona_" in name:
        # 提取人设名：去掉 persona_ 前缀和 .yaml 后缀
        core = name[len("persona_"):]  # e.g. "Theresa_20260514_123045.yaml"
        if core.endswith(".yaml"):
            core = core[:-5]  # e.g. "Theresa_20260514_123045"
        # 去掉时间戳后缀 _YYYYMMDD_HHMMSS (16字符)
        if len(core) > 16 and core[-15:].replace("_", "").isdigit():
            core = core[:-16]  # e.g. "Theresa"
        return PERSONAS_DIR / f"{core}.yaml"
    return None


@app.route("/api/backup/restore_all", methods=["POST"])
def restore_backup_set():
    """一键恢复整个备份集（同时间戳的所有文件）"""
    import shutil
    data = request.json
    ts = data.get("timestamp", "")
    if not ts:
        return jsonify({"ok": False, "msg": "缺少时间戳"})
    backup_dir = DATA_DIR / "backups"
    restored = []
    for f in backup_dir.glob(f"*{ts}*"):
        target = _resolve_backup_target(f.name)
        if target:
            shutil.copy2(f, target)
            restored.append(f.name)
    if not restored:
        return jsonify({"ok": False, "msg": "未找到匹配的备份文件"})
    return jsonify({"ok": True, "msg": f"已恢复 {len(restored)} 个文件", "files": restored})

# ========== 数据库查看 ==========
@app.route("/api/db/tables", methods=["GET"])
def list_db_tables():
    """列出所有数据库表（合并活跃人设的所有数据库）"""
    import sqlite3
    merged_tables = {}

    # 新版结构：合并人设全局库 + 所有用户库
    active_persona = _db_resolver.get_active_persona()
    dbs_to_scan = []

    # 人设全局库
    global_db = _db_resolver.get_persona_global_db(active_persona)
    if global_db.exists():
        dbs_to_scan.append(global_db)

    # 所有用户在该人设下的库
    for user_id in _db_resolver.list_users():
        user_db = _db_resolver.get_user_db(user_id, active_persona)
        if user_db.exists():
            dbs_to_scan.append(user_db)

    # 回退旧版
    if not dbs_to_scan:
        fallback = get_active_db_path()
        if fallback.exists():
            dbs_to_scan.append(fallback)

    for db_path in dbs_to_scan:
        try:
            conn = sqlite3.connect(str(db_path))
            tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            for (table,) in tables:
                if table in merged_tables:
                    continue
                count = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]
                cols = [d[1] for d in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
                merged_tables[table] = {"name": table, "count": count, "columns": cols}
            conn.close()
        except Exception:
            pass

    result = sorted(merged_tables.values(), key=lambda x: x["name"])
    return jsonify({"tables": result})

@app.route("/api/db/table/<name>", methods=["GET"])
def get_table_data(name):
    """获取表数据（合并人设全局库+所有用户库）"""
    import sqlite3
    if ".." in name or "/" in name:
        return jsonify({"error": "invalid name"})
    merged_rows = []
    merged_cols = []
    active_persona = _db_resolver.get_active_persona()
    dbs_to_scan = []
    global_db = _db_resolver.get_persona_global_db(active_persona)
    if global_db.exists():
        dbs_to_scan.append(global_db)
    for user_id in _db_resolver.list_users():
        user_db = _db_resolver.get_user_db(user_id, active_persona)
        if user_db.exists():
            dbs_to_scan.append(user_db)
    if not dbs_to_scan:
        fallback = get_active_db_path()
        if fallback.exists():
            dbs_to_scan.append(fallback)
    for db_path in dbs_to_scan:
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            if not merged_cols:
                merged_cols = [d[1] for d in conn.execute(f"PRAGMA table_info([{name}])").fetchall()]
            try:
                rows = conn.execute(f"SELECT ROWID, * FROM [{name}] ORDER BY ROWID DESC LIMIT 200").fetchall()
                for r in rows:
                    merged_rows.append(dict(r))
            except Exception:
                pass
            conn.close()
        except Exception:
            pass
    merged_rows.sort(key=lambda x: x.get("ROWID", 0) or x.get("rowid", 0) or 0, reverse=True)
    merged_rows = merged_rows[:200]
    return jsonify({"columns": merged_cols, "rows": merged_rows, "total": len(merged_rows)})

@app.route("/api/db/delete_row", methods=["POST"])
def delete_db_row():
    """删除数据库行"""
    import sqlite3
    data = request.get_json(silent=True) or {}
    table = str(data.get("table", "")).strip()
    row_id = data.get("id", data.get("rowid"))
    if not table or row_id is None or str(row_id) == "":
        return jsonify({"ok": False, "msg": "缺少参数"})
    try:
        db_path = get_active_db_path()
        user_id = str(data.get("user_id", "")).strip()
        persona = str(data.get("persona", "")).strip()
        if user_id and persona:
            candidate = _db_resolver.get_user_db(user_id, persona)
            if candidate.exists():
                db_path = candidate
        conn = sqlite3.connect(str(db_path))
        conn.execute(f"DELETE FROM [{table}] WHERE ROWID = ?", (row_id,))
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "msg": "已删除"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

# ========== 数据库表元信息（中文名+作用描述） ==========
DB_TABLE_META = {
    "life_events": {"cn": "生活事件", "desc": "AI角色的日常生活事件记录，影响人格表现和对话风格"},
    "user_profiles": {"cn": "用户档案", "desc": "用户基础信息、亲密度等级、经验值、首次/最近见面时间"},
    "growth_memories": {"cn": "成长记忆", "desc": "角色与用户互动中的成长事件，影响性格发展"},
    "long_term_memory": {"cn": "长期记忆", "desc": "重要信息的持久存储，影响对话连贯性和个性化"},
    "active_days": {"cn": "活跃天数", "desc": "用户每日活跃记录，用于统计互动频率"},
    "mood_history": {"cn": "情绪历史", "desc": "用户每日情绪记录，用于情绪趋势分析"},
    "favorite_topics": {"cn": "偏好话题", "desc": "用户聊天话题偏好统计，影响话题推荐"},
    "conversation_log": {"cn": "对话日志", "desc": "对话摘要记录，包含话题、情绪、参与度评分"},
    "evolution_state": {"cn": "进化状态", "desc": "角色进化引擎的状态键值对，驱动风格自适应"},
    "emotion_state": {"cn": "情绪状态", "desc": "用户当前情绪快照：情绪值、主导情绪、连续计数"},
    "chat_history": {"cn": "聊天历史", "desc": "完整聊天记录，包含用户消息和AI回复"},
    "word_weights": {"cn": "词汇权重", "desc": "自动学习的词汇重要性权重，影响Prompt生成"},
    "temp_time_mentions": {"cn": "时间提及", "desc": "用户提到的时间信息缓存，用于定时提醒"},
    "chat_whitelist": {"cn": "聊天白名单", "desc": "允许与AI聊天的用户列表"},
    "proactive_state": {"cn": "主动消息状态", "desc": "主动消息系统的用户状态追踪"},
    "proactive_events": {"cn": "主动消息事件", "desc": "主动消息调度原因、跳过原因和发送审计"},
    "pad_state": {"cn": "PAD情绪模型", "desc": "愉悦度-唤醒度-支配度三维情绪状态"},
    "persona_control": {"cn": "人格控制", "desc": "人格残差累积状态和修正历史"},
    "persona_residuals": {"cn": "人格残差", "desc": "人格漂移的残差数据记录"},
    "drift_reports": {"cn": "漂移报告", "desc": "人格漂移检测结果和修正建议"},
    "relationship_state": {"cn": "关系状态", "desc": "当前激活的关系类型和自定义数据"},
    "narrative_log": {"cn": "叙事日志", "desc": "自我表露和故事分享的记录"},
    "episodic_memories": {"cn": "情景记忆", "desc": "带情感锚点和时间衰减的事件记忆"},
    "user_psychology": {"cn": "用户心理画像", "desc": "8维度用户心理分析数据"},
    "psychology_history": {"cn": "心理画像历史", "desc": "心理维度变化的历史记录"},
}

@app.route("/api/db/table_meta", methods=["GET"])
def get_table_meta():
    """返回所有表的中文名和作用描述"""
    return jsonify(DB_TABLE_META)

@app.route("/api/db/users", methods=["GET"])
def list_db_users():
    """列出所有用户账号（新版结构扫描 accounts/ 目录）"""
    import sqlite3
    all_users = {}
    nickname_map = {}

    # 新版结构：从 accounts/ 目录扫描
    for user_id in _db_resolver.list_users():
        personas = _db_resolver.list_personas_for_user(user_id)
        for persona in personas:
            db_path = _db_resolver.get_user_db(user_id, persona)
            if not db_path.exists():
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT user_id, nickname, total_messages, first_seen, last_seen, relationship_level, relationship_exp "
                    "FROM user_profiles ORDER BY last_seen DESC"
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    uid = d["user_id"]
                    if uid not in all_users or d.get("total_messages", 0) > all_users[uid].get("total_messages", 0):
                        all_users[uid] = d
                        all_users[uid]["_persona"] = persona
                try:
                    wl = conn.execute("SELECT qq_id, nickname FROM chat_whitelist").fetchall()
                    for r in wl:
                        if r["nickname"]:
                            nickname_map[r["qq_id"]] = r["nickname"]
                except Exception:
                    pass
                conn.close()
            except Exception:
                pass

    # 回退：旧版结构
    if not all_users:
        for persona, db_path in get_all_db_paths():
            if persona == "shared":
                continue
            if not db_path.exists():
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT user_id, nickname, total_messages, first_seen, last_seen, relationship_level, relationship_exp "
                    "FROM user_profiles ORDER BY last_seen DESC"
                ).fetchall()
                for r in rows:
                    d = dict(r)
                    uid = d["user_id"]
                    if uid not in all_users or d.get("total_messages", 0) > all_users[uid].get("total_messages", 0):
                        all_users[uid] = d
                        all_users[uid]["_persona"] = persona
                try:
                    wl = conn.execute("SELECT qq_id, nickname FROM chat_whitelist").fetchall()
                    for r in wl:
                        if r["nickname"]:
                            nickname_map[r["qq_id"]] = r["nickname"]
                except Exception:
                    pass
                conn.close()
            except Exception:
                pass

    for uid, u in all_users.items():
        if not u.get("nickname") and uid in nickname_map:
            u["nickname"] = nickname_map[uid]
    users = sorted(all_users.values(), key=lambda x: x.get("last_seen", ""), reverse=True)
    return jsonify({"users": users})

@app.route("/api/db/user_data/<user_id>", methods=["GET"])
def get_user_data(user_id):
    """获取指定用户在各表中的数据（新版结构：扫描该用户所有人设数据库）"""
    import sqlite3
    if ".." in user_id or "/" in user_id:
        return jsonify({"error": "invalid user_id"})
    merged = {}

    # 新版结构：直接从 accounts/{user_id}/ 下扫描所有人设
    user_personas = _db_resolver.list_personas_for_user(user_id)
    if user_personas:
        for persona in user_personas:
            db_path = _db_resolver.get_user_db(user_id, persona)
            if not db_path.exists():
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (table,) in tables:
                    cols = [d[1] for d in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
                    try:
                        rows = conn.execute(f"SELECT ROWID AS ROWID, * FROM [{table}] ORDER BY ROWID DESC LIMIT 200").fetchall()
                        row_dicts = []
                        for r in rows:
                            item = dict(r)
                            item["_persona"] = persona
                            item["_user_id"] = user_id
                            row_dicts.append(item)
                        if table not in merged:
                            merged[table] = {"columns": cols, "rows": row_dicts, "total": len(row_dicts), "_persona": persona}
                        else:
                            existing_ids = set()
                            for er in merged[table]["rows"]:
                                existing_ids.add(er.get("id") or er.get("ROWID"))
                            for nr in row_dicts:
                                nid = nr.get("id") or nr.get("ROWID")
                                if nid not in existing_ids:
                                    merged[table]["rows"].append(nr)
                            merged[table]["total"] = len(merged[table]["rows"])
                    except Exception:
                        pass
                conn.close()
            except Exception:
                pass
    else:
        # 回退旧版结构
        for persona, db_path in get_all_db_paths():
            if persona == "shared":
                continue
            if not db_path.exists():
                continue
            try:
                conn = sqlite3.connect(str(db_path))
                conn.row_factory = sqlite3.Row
                tables = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                ).fetchall()
                for (table,) in tables:
                    cols = [d[1] for d in conn.execute(f"PRAGMA table_info([{table}])").fetchall()]
                    if "user_id" not in cols:
                        continue
                    try:
                        rows = conn.execute(
                            f"SELECT ROWID AS ROWID, * FROM [{table}] WHERE user_id = ? ORDER BY ROWID DESC LIMIT 200",
                            (user_id,)
                        ).fetchall()
                        row_dicts = []
                        for r in rows:
                            item = dict(r)
                            item["_persona"] = persona
                            item["_user_id"] = user_id
                            row_dicts.append(item)
                        if table not in merged:
                            merged[table] = {"columns": cols, "rows": row_dicts, "total": len(row_dicts)}
                        else:
                            existing_ids = set()
                            for er in merged[table]["rows"]:
                                existing_ids.add(er.get("id") or er.get("ROWID"))
                            for nr in row_dicts:
                                nid = nr.get("id") or nr.get("ROWID")
                                if nid not in existing_ids:
                                    merged[table]["rows"].append(nr)
                            merged[table]["total"] = len(merged[table]["rows"])
                    except Exception:
                        pass
                conn.close()
            except Exception:
                pass

    return jsonify({"data": merged})

@app.route("/api/db/add_row", methods=["POST"])
def add_db_row():
    """向指定表添加新行"""
    import sqlite3
    data = request.json
    table = data.get("table", "")
    row_data = data.get("data", {})
    if not table or not row_data:
        return jsonify({"ok": False, "msg": "缺少参数"})
    try:
        conn = sqlite3.connect(str(get_active_db_path()))
        cols = ", ".join([f"[{k}]" for k in row_data.keys()])
        placeholders = ", ".join(["?"] * len(row_data))
        conn.execute(
            f"INSERT INTO [{table}] ({cols}) VALUES ({placeholders})",
            list(row_data.values())
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "msg": f"已添加到 {table}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

@app.route("/api/db/edit_row", methods=["POST"])
def edit_db_row():
    """编辑指定表的指定行"""
    import sqlite3
    data = request.json
    table = data.get("table", "")
    row_id = data.get("id")
    updates = data.get("data", {})
    if not table or not row_id or not updates:
        return jsonify({"ok": False, "msg": "缺少参数"})
    try:
        conn = sqlite3.connect(str(get_active_db_path()))
        set_clause = ", ".join([f"[{k}] = ?" for k in updates.keys()])
        conn.execute(
            f"UPDATE [{table}] SET {set_clause} WHERE ROWID = ?",
            list(updates.values()) + [row_id]
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "msg": "已更新"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})

@app.route("/api/db/schema/<table_name>", methods=["GET"])
def get_table_schema(table_name):
    """获取表结构（列名、类型、是否主键）"""
    import sqlite3
    if ".." in table_name or "/" in table_name:
        return jsonify({"error": "invalid name"})
    db_path = get_active_db_path()
    if not db_path.exists():
        return jsonify({"columns": []})
    try:
        conn = sqlite3.connect(str(db_path))
        cols = conn.execute(f"PRAGMA table_info([{table_name}])").fetchall()
        result = [{"name": c[1], "type": c[2], "notnull": bool(c[3]), "default": c[4], "pk": bool(c[5])} for c in cols]
        conn.close()
        return jsonify({"columns": result})
    except Exception as e:
        return jsonify({"error": str(e)})

# ========== 增强备份管理 ==========
@app.route("/api/backup/clear_all", methods=["POST"])
def clear_all_backups():
    """清除所有本地备份文件"""
    backup_dir = DATA_DIR / "backups"
    if not backup_dir.exists():
        return jsonify({"ok": True, "msg": "没有备份文件", "count": 0})
    count = 0
    errors = 0
    for f in backup_dir.glob("*"):
        try:
            f.unlink()
            count += 1
        except Exception:
            errors += 1
    msg = f"已清除 {count} 个备份文件"
    if errors:
        msg += f"，{errors} 个删除失败"
    return jsonify({"ok": True, "msg": msg, "count": count})

@app.route("/api/backup/view/<name>", methods=["GET"])
def view_backup(name):
    """查看备份文件内容"""
    if ".." in name or "/" in name:
        return jsonify({"error": "invalid name"})
    path = DATA_DIR / "backups" / name
    if not path.exists():
        return jsonify({"error": "文件不存在"})
    try:
        content = path.read_text(encoding="utf-8")
        return jsonify({"name": name, "content": content, "size": path.stat().st_size})
    except Exception as e:
        return jsonify({"error": str(e)})

# ========== 主动消息配置 ==========
@app.route("/api/proactive", methods=["GET"])
def get_proactive_config():
    """读取主动消息配置"""
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    proactive = config.get("proactive", {})
    defaults = {
        "interval_hours": 2,
        "mutter_enabled": True,
        "mutter_max_per_slot": 1,
        "boot_cooldown_minutes": 30,
        "quiet_hours_start": 0,
        "quiet_hours_end": 7,
        "care_trigger_chance": 0.8,
    }
    for k, v in defaults.items():
        if k not in proactive:
            proactive[k] = v
    return jsonify(proactive)

@app.route("/api/proactive", methods=["POST"])
def save_proactive_config():
    """保存主动消息配置"""
    data = request.json
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    if "proactive" not in config:
        config["proactive"] = {}
    config["proactive"].update(data)
    save_yaml(CONFIG_PATH, config)
    return jsonify({"ok": True, "msg": "主动消息配置已保存（重启机器人后生效）"})

@app.route("/api/proactive/events", methods=["GET"])
def list_proactive_events():
    """读取主动消息调度审计事件。"""
    user_id = request.args.get("user_id", "").strip()
    status = request.args.get("status", "").strip()
    limit = min(max(int(request.args.get("limit", 100) or 100), 1), 500)
    rows = []
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "proactive_events" not in tables:
                conn.close()
                continue
            clauses = []
            params = []
            if user_id:
                clauses.append("user_id = ?")
                params.append(user_id)
            if status:
                clauses.append("status = ?")
                params.append(status)
            sql = "SELECT * FROM proactive_events"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            for r in conn.execute(sql, params).fetchall():
                item = dict(r)
                try:
                    item["meta"] = json.loads(item.get("meta_json") or "{}")
                except Exception:
                    item["meta"] = {}
                item["db_path"] = _rel_db_path(db_path)
                rows.append(item)
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"ok": True, "data": rows[:limit]})

# ========== 模块开关 ==========
@app.route("/api/modules", methods=["GET"])
def get_modules():
    """获取模块开关状态"""
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    modules = config.get("modules", {})
    defaults = {
        "emotion": {"enabled": True, "name": "情绪系统", "desc": "情绪识别+状态机+PAD三维模型"},
        "growth": {"enabled": True, "name": "成长系统", "desc": "亲密度等级+经验值+恋人模式"},
        "evolution": {"enabled": True, "name": "进化引擎", "desc": "话题偏好+回复风格分析"},
        "psychology": {"enabled": True, "name": "心理画像", "desc": "AI驱动8维度用户心理分析"},
        "dimensions": {"enabled": True, "name": "多维性格", "desc": "多维度性格系统"},
        "episodic_memory": {"enabled": True, "name": "情景记忆", "desc": "时间衰减+情感锚点记忆"},
        "memory_fermentation": {"enabled": True, "name": "记忆发酵", "desc": "模糊化回忆+夜间回味"},
        "persona_drift": {"enabled": True, "name": "人格漂移检测", "desc": "5维度漂移分析+修正"},
        "persona_control": {"enabled": True, "name": "人格残差控制", "desc": "9维度残差+可采纳性判定"},
        "life_system": {"enabled": True, "name": "生活事件", "desc": "AI生成角色日常生活"},
        "proactive": {"enabled": True, "name": "主动消息", "desc": "定时主动聊天+碎碎念+关心"},
        "narrative": {"enabled": True, "name": "叙事引擎", "desc": "自我表露+故事分享"},
        "scene_detect": {"enabled": True, "name": "场景识别", "desc": "AI驱动对话场景检测"},
        "tts": {"enabled": True, "name": "语音合成", "desc": "MiMo音色克隆TTS"},
        "search": {"enabled": True, "name": "联网搜索", "desc": "Tavily API搜索"},
        "sticker": {"enabled": True, "name": "表情包识别", "desc": "下载+情绪映射"},
        "weight_manager": {"enabled": True, "name": "词汇权重", "desc": "自动学习+衰减+Prompt注入"},
    }
    for k, v in defaults.items():
        if k not in modules:
            modules[k] = v
        else:
            for dk, dv in v.items():
                if dk not in modules[k]:
                    modules[k][dk] = dv
    return jsonify(modules)

@app.route("/api/modules/toggle", methods=["POST"])
def toggle_module():
    """开关模块"""
    data = request.json
    name = data.get("name", "")
    enabled = data.get("enabled", True)
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    if "modules" not in config:
        config["modules"] = {}
    if name not in config["modules"]:
        config["modules"][name] = {}
    config["modules"][name]["enabled"] = enabled
    save_yaml(CONFIG_PATH, config)
    return jsonify({"ok": True, "msg": f"模块 {name} 已{'启用' if enabled else '禁用'}（重启后生效）"})


# ========== 人设数据库管理 ==========
@app.route("/api/persona/db_info", methods=["GET"])
def get_persona_db_info():
    """获取当前人设数据库信息"""
    from src.memory.database import Database
    db = Database()
    dbs = db.list_persona_databases()
    return jsonify({
        "current_persona": db._current_persona,
        "current_db": str(db.current_db_path),
        "psychology_shared": db._psychology_shared,
        "databases": dbs,
    })

@app.route("/api/persona/psychology_shared", methods=["POST"])
def toggle_psychology_shared():
    """切换心理画像共享模式（含数据融合/保全）"""
    from src.memory.database import Database
    data = request.json
    shared = data.get("shared", True)
    db = Database()
    current_persona = db._current_persona

    if shared:
        # 关→开：融合当前人设为主，其余为辅
        db.merge_psychology_to_shared(current_persona)
    else:
        # 开→关：将共享数据保存到当前人设专用库
        db.save_shared_to_persona(current_persona)

    db.set_psychology_shared(shared)
    # 保存到配置
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    if "modules" not in config:
        config["modules"] = {}
    if "psychology" not in config["modules"]:
        config["modules"]["psychology"] = {}
    config["modules"]["psychology"]["shared"] = shared
    save_yaml(CONFIG_PATH, config)

    if shared:
        msg = f"心理画像已切换为共享模式（{current_persona} 为主，其余为辅，重启后生效）"
    else:
        msg = f"心理画像已切换为独立模式（共享数据已保存到 {current_persona} 专用库，重启后生效）"
    return jsonify({"ok": True, "msg": msg})


# ========== 场景组/语气组管理 ==========
@app.route("/api/scene_groups", methods=["GET"])
def list_scene_groups():
    """列出所有场景组"""
    groups_dir = DATA_DIR / "scene_groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    groups = []
    for f in sorted(groups_dir.glob("*.yaml")):
        data = load_yaml(f) if f.exists() else {}
        scenes = data.get("scenes", {})
        groups.append({"name": f.stem, "file": f.name, "count": len(scenes)})
    # 读取当前激活的场景组
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    active = config.get("active_scene_group", "default")
    return jsonify({"groups": groups, "active": active})

@app.route("/api/scene_group/<name>", methods=["GET"])
def get_scene_group(name):
    """获取指定场景组的内容"""
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"scenes": {}})
    data = load_yaml(path) or {}
    return jsonify(data)

@app.route("/api/scene_group/<name>", methods=["POST"])
def save_scene_group(name):
    """保存场景组"""
    data = request.json
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    save_yaml(path, data)
    return jsonify({"ok": True, "msg": f"场景组 {name} 已保存"})

@app.route("/api/scene_group/create", methods=["POST"])
def create_scene_group():
    """创建新场景组"""
    data = request.json
    name = data.get("name", "").strip()
    if not name or ".." in name or "/" in name:
        return jsonify({"ok": False, "msg": "无效名称"})
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    if path.exists():
        return jsonify({"ok": False, "msg": "场景组已存在"})
    save_yaml(path, {"scenes": {}})
    return jsonify({"ok": True, "msg": f"场景组 {name} 已创建"})

@app.route("/api/scene_group/switch", methods=["POST"])
def switch_scene_group():
    """切换当前场景组"""
    data = request.json
    name = data.get("name", "default")
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "场景组不存在"})
    # 更新配置
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    config["active_scene_group"] = name
    save_yaml(CONFIG_PATH, config)
    # 同步到 scenes.yaml（供机器人读取）
    shutil.copy2(path, DATA_DIR / "scenes.yaml")
    return jsonify({"ok": True, "msg": f"已切换到场景组 {name}"})

@app.route("/api/scene_group/<name>/add", methods=["POST"])
def add_scene_to_group(name):
    """向场景组添加新场景"""
    data = request.json
    scene_id = data.get("id", "").strip()
    if not scene_id:
        return jsonify({"ok": False, "msg": "缺少场景ID"})
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    group_data = load_yaml(path) if path.exists() else {"scenes": {}}
    if "scenes" not in group_data:
        group_data["scenes"] = {}
    if scene_id in group_data["scenes"]:
        return jsonify({"ok": False, "msg": "场景ID已存在"})
    group_data["scenes"][scene_id] = {
        "name": data.get("name", scene_id),
        "description": data.get("description", ""),
        "trigger_hint": data.get("trigger_hint", ""),
        "tone": data.get("tone", ""),
        "extra_hint": data.get("extra_hint", ""),
    }
    save_yaml(path, group_data)
    # 同步到 scenes.yaml
    shutil.copy2(path, DATA_DIR / "scenes.yaml")
    return jsonify({"ok": True, "msg": f"场景 {scene_id} 已添加"})

@app.route("/api/scene_group/<name>/delete", methods=["POST"])
def delete_scene_from_group(name):
    """从场景组删除场景"""
    data = request.json
    scene_id = data.get("id", "")
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "场景组不存在"})
    group_data = load_yaml(path) or {}
    if scene_id in group_data.get("scenes", {}):
        del group_data["scenes"][scene_id]
        save_yaml(path, group_data)
        shutil.copy2(path, DATA_DIR / "scenes.yaml")
        return jsonify({"ok": True, "msg": f"场景 {scene_id} 已删除"})
    return jsonify({"ok": False, "msg": "场景不存在"})

@app.route("/api/tone_groups", methods=["GET"])
def list_tone_groups():
    """列出所有语气组"""
    groups_dir = DATA_DIR / "tone_groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    groups = []
    for f in sorted(groups_dir.glob("*.yaml")):
        data = load_yaml(f) if f.exists() else {}
        tones = data.get("tones", {})
        groups.append({"name": f.stem, "file": f.name, "count": len(tones)})
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    active = config.get("active_tone_group", "default")
    return jsonify({"groups": groups, "active": active})

@app.route("/api/tone_group/<name>", methods=["GET"])
def get_tone_group(name):
    """获取指定语气组的内容"""
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"tones": {}})
    data = load_yaml(path) or {}
    return jsonify(data)

@app.route("/api/tone_group/<name>", methods=["POST"])
def save_tone_group(name):
    """保存语气组"""
    data = request.json
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    save_yaml(path, data)
    return jsonify({"ok": True, "msg": f"语气组 {name} 已保存"})

@app.route("/api/tone_group/create", methods=["POST"])
def create_tone_group():
    """创建新语气组"""
    data = request.json
    name = data.get("name", "").strip()
    if not name or ".." in name or "/" in name:
        return jsonify({"ok": False, "msg": "无效名称"})
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    if path.exists():
        return jsonify({"ok": False, "msg": "语气组已存在"})
    save_yaml(path, {"tones": {}})
    return jsonify({"ok": True, "msg": f"语气组 {name} 已创建"})

@app.route("/api/tone_group/switch", methods=["POST"])
def switch_tone_group():
    """切换当前语气组"""
    data = request.json
    name = data.get("name", "default")
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "语气组不存在"})
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    config["active_tone_group"] = name
    save_yaml(CONFIG_PATH, config)
    shutil.copy2(path, DATA_DIR / "tones.yaml")
    return jsonify({"ok": True, "msg": f"已切换到语气组 {name}"})

@app.route("/api/tone_group/<name>/add", methods=["POST"])
def add_tone_to_group(name):
    """向语气组添加新语气"""
    data = request.json
    tone_id = data.get("id", "").strip()
    if not tone_id:
        return jsonify({"ok": False, "msg": "缺少语气ID"})
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    group_data = load_yaml(path) if path.exists() else {"tones": {}}
    if "tones" not in group_data:
        group_data["tones"] = {}
    if tone_id in group_data["tones"]:
        return jsonify({"ok": False, "msg": "语气ID已存在"})
    group_data["tones"][tone_id] = {
        "name": data.get("name", tone_id),
        "description": data.get("description", ""),
        "style": data.get("style", ""),
        "verbal_tics": data.get("verbal_tics", []),
        "sentence_pattern": data.get("sentence_pattern", ""),
    }
    save_yaml(path, group_data)
    shutil.copy2(path, DATA_DIR / "tones.yaml")
    return jsonify({"ok": True, "msg": f"语气 {tone_id} 已添加"})

@app.route("/api/tone_group/<name>/delete", methods=["POST"])
def delete_tone_from_group(name):
    """从语气组删除语气"""
    data = request.json
    tone_id = data.get("id", "")
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "语气组不存在"})
    group_data = load_yaml(path) or {}
    if tone_id in group_data.get("tones", {}):
        del group_data["tones"][tone_id]
        save_yaml(path, group_data)
        shutil.copy2(path, DATA_DIR / "tones.yaml")
        return jsonify({"ok": True, "msg": f"语气 {tone_id} 已删除"})
    return jsonify({"ok": False, "msg": "语气不存在"})


@app.route("/api/scene_group/<name>/delete_group", methods=["POST"])
def delete_scene_group(name):
    """删除整个场景组"""
    path = DATA_DIR / "scene_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "场景组不存在"})
    if name == "default":
        return jsonify({"ok": False, "msg": "不能删除默认场景组"})
    path.unlink()
    # 如果删除的是当前激活的，切回 default
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    if config.get("active_scene_group") == name:
        config["active_scene_group"] = "default"
        save_yaml(CONFIG_PATH, config)
        default_path = DATA_DIR / "scene_groups" / "default.yaml"
        if default_path.exists():
            shutil.copy2(default_path, DATA_DIR / "scenes.yaml")
    return jsonify({"ok": True, "msg": f"场景组 {name} 已删除"})


@app.route("/api/tone_group/<name>/delete_group", methods=["POST"])
def delete_tone_group(name):
    """删除整个语气组"""
    path = DATA_DIR / "tone_groups" / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "语气组不存在"})
    if name == "default":
        return jsonify({"ok": False, "msg": "不能删除默认语气组"})
    path.unlink()
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    if config.get("active_tone_group") == name:
        config["active_tone_group"] = "default"
        save_yaml(CONFIG_PATH, config)
        default_path = DATA_DIR / "tone_groups" / "default.yaml"
        if default_path.exists():
            shutil.copy2(default_path, DATA_DIR / "tones.yaml")
    return jsonify({"ok": True, "msg": f"语气组 {name} 已删除"})


@app.route("/api/persona/<name>/delete_file", methods=["POST"])
def delete_persona_file(name):
    """删除人设文件"""
    path = PERSONAS_DIR / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "人设文件不存在"})
    if name == config.get("default_persona", "Theresa"):
        return jsonify({"ok": False, "msg": "不能删除当前默认人设"})
    path.unlink()
    return jsonify({"ok": True, "msg": f"人设 {name} 已删除"})


# ========== 人设-场景/语气绑定 ==========
@app.route("/api/persona/<name>/bindings", methods=["GET"])
def get_persona_bindings_specific(name):
    """获取具体人设的绑定配置"""
    path = PERSONAS_DIR / f"{name}.yaml"
    data = load_yaml(path) if path.exists() else {}
    return jsonify({
        "scene_group": data.get("scene_group", ""),
        "tone_group": data.get("tone_group", ""),
        "audio_group": data.get("audio_group", "")
    })

@app.route("/api/persona/<name>/bindings", methods=["POST"])
def save_persona_bindings_specific(name):
    """保存具体人设的绑定配置到其YAML文件中"""
    req_data = request.json
    path = PERSONAS_DIR / f"{name}.yaml"
    if not path.exists():
        return jsonify({"ok": False, "msg": "人设文件不存在"})
    
    data = load_yaml(path) or {}
    
    # 修复：显式检查 key 是否存在，避免空字符串被当作 falsy 忽略
    if "scene_group" in req_data:
        if req_data["scene_group"]:
            data["scene_group"] = req_data["scene_group"]
        elif "scene_group" in data:
            del data["scene_group"]

    if "tone_group" in req_data:
        if req_data["tone_group"]:
            data["tone_group"] = req_data["tone_group"]
        elif "tone_group" in data:
            del data["tone_group"]

    if "audio_group" in req_data:
        if req_data["audio_group"]:
            data["audio_group"] = req_data["audio_group"]
        elif "audio_group" in data:
            del data["audio_group"]
        
    save_persona(name, data) # reuse exist logic
    return jsonify({"ok": True, "msg": f"{name} 绑定已保存（重启生效）"})

# ========== 音频组管理 ==========
@app.route("/api/audio_groups", methods=["GET"])
def list_audio_groups():
    """列出所有音频组"""
    groups_dir = DATA_DIR / "audio_groups"
    groups_dir.mkdir(parents=True, exist_ok=True)
    groups = []
    for d in sorted(groups_dir.iterdir()):
        if d.is_dir():
            files = list(d.glob("*"))
            audio_files = [f for f in files if f.suffix.lower() in ('.wav', '.mp3', '.ogg', '.flac', '.silk')]
            groups.append({"name": d.name, "count": len(audio_files), "files": [f.name for f in audio_files]})
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    active = config.get("active_audio_group", "")
    return jsonify({"groups": groups, "active": active})

@app.route("/api/audio_group/create", methods=["POST"])
def create_audio_group():
    """创建新音频组"""
    data = request.json
    name = data.get("name", "").strip()
    if not name or ".." in name or "/" in name:
        return jsonify({"ok": False, "msg": "无效名称"})
    path = DATA_DIR / "audio_groups" / name
    if path.exists():
        return jsonify({"ok": False, "msg": "音频组已存在"})
    path.mkdir(parents=True)
    return jsonify({"ok": True, "msg": f"音频组 {name} 已创建"})

@app.route("/api/audio_group/<name>/upload", methods=["POST"])
def upload_audio(name):
    """上传音频到音频组"""
    group_dir = DATA_DIR / "audio_groups" / name
    group_dir.mkdir(parents=True, exist_ok=True)
    if 'file' not in request.files:
        return jsonify({"ok": False, "msg": "未选择文件"})
    file = request.files['file']
    if not file.filename:
        return jsonify({"ok": False, "msg": "文件名为空"})
    # 检查文件类型
    allowed = {'.wav', '.mp3', '.ogg', '.flac', '.silk', '.m4a', '.aac'}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed:
        return jsonify({"ok": False, "msg": f"不支持的格式: {ext}"})
    filepath = group_dir / file.filename
    file.save(str(filepath))
    return jsonify({"ok": True, "msg": f"已上传 {file.filename}", "path": str(filepath)})

@app.route("/api/audio_group/<name>/delete", methods=["POST"])
def delete_audio(name):
    """删除音频组中的文件"""
    data = request.json
    filename = data.get("filename", "")
    if not filename or ".." in filename or "/" in filename:
        return jsonify({"ok": False, "msg": "无效文件名"})
    filepath = DATA_DIR / "audio_groups" / name / filename
    if filepath.exists():
        filepath.unlink()
        return jsonify({"ok": True, "msg": f"已删除 {filename}"})
    return jsonify({"ok": False, "msg": "文件不存在"})

@app.route("/api/audio_group/<name>/set_reference", methods=["POST"])
def set_audio_reference(name):
    """将音频组设为当前 TTS 参考音频"""
    group_dir = DATA_DIR / "audio_groups" / name
    if not group_dir.exists():
        return jsonify({"ok": False, "msg": "音频组不存在"})
    audio_files = [f for f in group_dir.glob("*") if f.suffix.lower() in ('.wav', '.mp3', '.ogg', '.flac')]
    if not audio_files:
        return jsonify({"ok": False, "msg": "音频组中没有可用的音频文件"})
    # 使用第一个音频文件作为参考
    ref_file = audio_files[0]
    # 更新 config.yaml 的 tts.reference_audio
    config = load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}
    if "tts" not in config:
        config["tts"] = {}
    config["tts"]["reference_audio"] = str(ref_file.relative_to(BASE_DIR))
    config["active_audio_group"] = name
    save_yaml(CONFIG_PATH, config)
    return jsonify({"ok": True, "msg": f"已将 {name} 设为 TTS 参考音频（重启后生效）", "file": ref_file.name})

@app.route("/api/audio_group/<name>/files", methods=["GET"])
def list_audio_files(name):
    """列出音频组中的文件"""
    group_dir = DATA_DIR / "audio_groups" / name
    if not group_dir.exists():
        return jsonify({"files": []})
    files = []
    for f in sorted(group_dir.glob("*")):
        if f.is_file():
            files.append({"name": f.name, "size": f.stat().st_size, "ext": f.suffix})
    return jsonify({"files": files})

# ========== 打开文件夹 ==========
@app.route("/api/open_folder", methods=["POST"])
def open_folder():
    """在文件管理器中打开指定文件夹"""
    import subprocess
    data = request.json
    folder = data.get("folder", "")
    # 安全检查：只允许打开项目内的文件夹
    allowed = ["data", "data/scene_groups", "data/tone_groups", "data/audio_groups",
               "data/backups", "data/voice", "data/stickers", "data/profiles",
               "data/memory", "data/life", "personas", "src", "src/plugins", "logs"]
    if folder not in allowed:
        return jsonify({"ok": False, "msg": "不允许打开此文件夹"})
    path = BASE_DIR / folder
    if path.exists():
        subprocess.Popen(f'explorer "{path}"', shell=True)
        return jsonify({"ok": True, "msg": f"已打开 {folder}"})
    return jsonify({"ok": False, "msg": "文件夹不存在"})


# ========== 关系定制系统 API ==========

@app.route("/api/relationships", methods=["GET"])
def list_relationships():
    """列出所有关系类型及用户当前关系状态"""
    try:
        config_path = DATA_DIR / "relationship_types.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        types = []
        for type_id, data in raw.items():
            if type_id.startswith("_"):
                continue
            types.append({
                "id": type_id,
                "name": data.get("name", type_id),
                "description": data.get("description", ""),
                "levels": data.get("levels", {}),
                "exp_multiplier": data.get("exp_multiplier", 1.0),
                "personality": data.get("personality", {}),
                "prompt_template": data.get("prompt_template", ""),
                "level_up_events": data.get("level_up_events", {}),
            })

        # 读取用户当前关系状态
        users = {}
        try:
            from src.memory.database import Database
            db = Database()
            with db.get_conn() as conn:
                rows = conn.execute("SELECT user_id, type_id, switched_at FROM relationship_state").fetchall()
                for r in rows:
                    users[r["user_id"]] = {"type_id": r["type_id"], "switched_at": r["switched_at"]}
        except Exception:
            pass

        return jsonify({"ok": True, "types": types, "users": users})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/relationship/switch", methods=["POST"])
def switch_relationship():
    """切换用户关系类型"""
    data = request.get_json() or {}
    user_id = data.get("user_id", "")
    type_id = data.get("type_id", "")
    if not user_id or not type_id:
        return jsonify({"ok": False, "error": "缺少参数"}), 400
    try:
        from src.memory.database import Database
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db = Database()
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO relationship_state (user_id, type_id, switched_at) VALUES (?, ?, ?)",
                (user_id, type_id, now),
            )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/relationship/save", methods=["POST"])
def save_relationship_type():
    """保存（新增/编辑）关系类型"""
    data = request.get_json() or {}
    type_id = data.get("id", "").strip()
    if not type_id:
        return jsonify({"ok": False, "error": "缺少类型 ID"}), 400
    # 保护基础关系类型
    if type_id == "default" or type_id in BASE_RELATIONSHIP_TYPES:
        return jsonify({"ok": False, "error": "不能修改基础关系类型"}), 400
    import re as _re
    if not _re.match(r'^[a-z_]+$', type_id):
        return jsonify({"ok": False, "error": "ID 只允许小写字母和下划线"}), 400
    try:
        config_path = DATA_DIR / "relationship_types.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        raw[type_id] = {
            "name": data.get("name", type_id),
            "description": data.get("description", ""),
            "levels": data.get("levels", {}),
            "exp_multiplier": data.get("exp_multiplier", 1.0),
            "personality": data.get("personality", {}),
            "prompt_template": data.get("prompt_template", ""),
            "level_up_events": data.get("level_up_events", {}),
        }
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/relationship/auto-generate", methods=["POST"])
def auto_generate_whitelist_bindings():
    """为白名单账号自动生成默认关系配置"""
    try:
        from src.memory.database import Database
        db = Database()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        created = 0
        with db.get_conn() as conn:
            # 获取所有白名单用户
            whitelist = conn.execute("SELECT qq_id FROM chat_whitelist WHERE enabled = 1").fetchall()
            for row in whitelist:
                user_id = "qq_" + row["qq_id"]
                # 检查是否已有关系配置
                existing = conn.execute(
                    "SELECT 1 FROM relationship_state WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                if not existing:
                    conn.execute(
                        "INSERT OR IGNORE INTO relationship_state (user_id, type_id, switched_at) VALUES (?, 'default', ?)",
                        (user_id, now)
                    )
                    created += 1
        return jsonify({"ok": True, "msg": f"已为 {created} 个白名单账号生成默认关系配置"})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)})


@app.route("/api/relationship/brief", methods=["GET"])
def relationship_brief():
    """Read-only relationship timeline summary for WebUI."""
    user_id = request.args.get("user_id", "").strip()
    persona = request.args.get("persona", "").strip()
    limit = min(max(int(request.args.get("limit", 20) or 20), 1), 100)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    result = {
        "ok": True,
        "generated_at": now,
        "filters": {"user_id": user_id, "persona": persona, "limit": limit},
        "summary": {
            "active_relationship": None,
            "account_binding": None,
            "last_contact_at": "",
            "last_relationship_switch_at": "",
            "counts": {
                "relationship_switch": 0,
                "account_binding": 0,
                "goal_event": 0,
                "memory_event": 0,
                "chat_record": 0,
                "long_memory": 0,
            },
        },
        "timeline": [],
        "dbs": [],
    }

    def push_event(item):
        if len(result["timeline"]) < limit * 8:
            result["timeline"].append(item)

    for db_path in _companion_scan_user_dbs():
        conn = None
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = _companion_table_names(conn)
            rel_db = _companion_rel_path(db_path)
            result["dbs"].append(rel_db)

            if "relationship_state" in tables:
                cols = _companion_columns(conn, "relationship_state")
                rows = _companion_fetch_recent(conn, "relationship_state", cols, user_id, persona, limit)
                if rows and not result["summary"]["active_relationship"]:
                    result["summary"]["active_relationship"] = {
                        "user_id": rows[0].get("user_id", ""),
                        "type_id": rows[0].get("type_id", ""),
                        "switched_at": rows[0].get("switched_at", ""),
                        "db_path": rel_db,
                    }
                    result["summary"]["last_relationship_switch_at"] = rows[0].get("switched_at", "")
                for row in rows:
                    result["summary"]["counts"]["relationship_switch"] += 1
                    push_event({
                        "time": row.get("switched_at") or row.get("updated_at") or row.get("created_at") or "",
                        "kind": "relationship_switch",
                        "title": f"关系切换为 {row.get('type_id', 'default')}",
                        "detail": row.get("user_id", ""),
                        "db_path": rel_db,
                    })

            if "account_bindings" in tables:
                cols = _companion_columns(conn, "account_bindings")
                rows = _companion_fetch_recent(conn, "account_bindings", cols, user_id, persona, limit)
                if rows and not result["summary"]["account_binding"]:
                    first = dict(rows[0])
                    first["boundaries"] = _companion_json(first.get("boundaries"), {})
                    first["db_path"] = rel_db
                    result["summary"]["account_binding"] = first
                for row in rows:
                    result["summary"]["counts"]["account_binding"] += 1
                    push_event({
                        "time": row.get("updated_at") or row.get("created_at") or "",
                        "kind": "account_binding",
                        "title": f"账号绑定 {row.get('relationship_type', '朋友')}",
                        "detail": f"{row.get('account_id', '')} / {row.get('persona_name', '')}",
                        "db_path": rel_db,
                    })

            if "growth_goal_events" in tables:
                cols = _companion_columns(conn, "growth_goal_events")
                rows = _companion_fetch_recent(conn, "growth_goal_events", cols, user_id, persona, limit)
                for row in rows:
                    result["summary"]["counts"]["goal_event"] += 1
                    push_event({
                        "time": row.get("created_at") or "",
                        "kind": "goal_event",
                        "title": f"目标事件 {row.get('event_type', '')}",
                        "detail": row.get("content", ""),
                        "db_path": rel_db,
                    })

            if "memory_ledger" in tables:
                cols = _companion_columns(conn, "memory_ledger")
                rows = _companion_fetch_recent(conn, "memory_ledger", cols, user_id, persona, limit * 2)
                for row in rows:
                    memory_type = str(row.get("type", ""))
                    if memory_type not in {"relationship", "event", "goal"}:
                        continue
                    result["summary"]["counts"]["memory_event"] += 1
                    push_event({
                        "time": row.get("created_at") or row.get("last_used_at") or "",
                        "kind": "memory_event",
                        "title": f"记忆账本 {memory_type}",
                        "detail": row.get("content", ""),
                        "db_path": rel_db,
                    })

            if "chat_records" in tables:
                cols = _companion_columns(conn, "chat_records")
                rows = _companion_fetch_recent(conn, "chat_records", cols, user_id, persona, limit)
                for idx, row in enumerate(rows):
                    if idx == 0 and not result["summary"]["last_contact_at"]:
                        result["summary"]["last_contact_at"] = row.get("timestamp") or row.get("created_at") or ""
                    result["summary"]["counts"]["chat_record"] += 1
                    push_event({
                        "time": row.get("timestamp") or row.get("created_at") or "",
                        "kind": "chat_record",
                        "title": f"聊天记录 {row.get('sender', '')}",
                        "detail": row.get("content", ""),
                        "db_path": rel_db,
                    })

            if "long_term_memory" in tables:
                cols = _companion_columns(conn, "long_term_memory")
                rows = _companion_fetch_recent(conn, "long_term_memory", cols, user_id, persona, limit * 2)
                for row in rows:
                    category = str(row.get("category", ""))
                    if category and ("关系" not in category and "记忆" not in category):
                        continue
                    result["summary"]["counts"]["long_memory"] += 1
                    push_event({
                        "time": row.get("last_accessed") or row.get("created_at") or "",
                        "kind": "long_memory",
                        "title": f"长期记忆 {category or '未分类'}",
                        "detail": row.get("content", ""),
                        "db_path": rel_db,
                    })
        except Exception as e:
            result.setdefault("warnings", []).append({"db_path": _companion_rel_path(db_path), "error": str(e)})
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass

    result["timeline"] = sorted(result["timeline"], key=lambda x: x.get("time", ""), reverse=True)[:limit]
    return jsonify(result)


BASE_RELATIONSHIP_TYPES = ['default', 'friend', 'lover', 'family', 'colleague', 'teacher_student']


@app.route("/api/relationship/delete", methods=["POST"])
def delete_relationship_type():
    """删除关系类型"""
    data = request.get_json() or {}
    type_id = data.get("id", "").strip()
    if not type_id:
        return jsonify({"ok": False, "error": "缺少类型 ID"}), 400
    if type_id == "default" or type_id in BASE_RELATIONSHIP_TYPES:
        return jsonify({"ok": False, "error": "不能删除基础关系类型"}), 400
    try:
        config_path = DATA_DIR / "relationship_types.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if type_id not in raw:
            return jsonify({"ok": False, "error": "类型不存在"}), 404
        del raw[type_id]
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(raw, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ========== 白名单管理 API ==========
@app.route("/api/whitelist", methods=["GET"])
def get_whitelist():
    """获取白名单列表"""
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_conn() as conn:
            rows = conn.execute("SELECT qq_id, nickname, enabled, first_seen, last_seen FROM chat_whitelist ORDER BY first_seen DESC").fetchall()
            users = []
            for r in rows:
                users.append({
                    "qq_id": r[0],
                    "nickname": r[1] or "",
                    "enabled": bool(r[2]),
                    "first_seen": r[3],
                    "last_seen": r[4],
                })
            return jsonify({"ok": True, "users": users})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/whitelist/toggle", methods=["POST"])
def toggle_whitelist():
    """切换白名单用户的启用状态"""
    data = request.json
    qq_id = data.get("qq_id", "")
    enabled = data.get("enabled", True)
    if not qq_id:
        return jsonify({"ok": False, "error": "缺少 qq_id"})
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_conn() as conn:
            conn.execute("UPDATE chat_whitelist SET enabled = ? WHERE qq_id = ?", (1 if enabled else 0, qq_id))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

@app.route("/api/whitelist/add", methods=["POST"])
def add_whitelist():
    """手动添加白名单用户"""
    data = request.json
    qq_id = str(data.get("qq_id", "")).strip()
    nickname = data.get("nickname", "")
    if not qq_id:
        return jsonify({"ok": False, "error": "缺少 qq_id"})
    try:
        from src.memory.database import Database
        db = Database()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db.get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO chat_whitelist (qq_id, nickname, enabled, first_seen, last_seen) VALUES (?, ?, 1, ?, ?)",
                (qq_id, nickname, now, now)
            )
        # 自动生成默认关系配置
        try:
            user_id = "qq_" + qq_id
            with db.get_conn() as conn2:
                existing = conn2.execute(
                    "SELECT 1 FROM relationship_state WHERE user_id = ?",
                    (user_id,)
                ).fetchone()
                if not existing:
                    conn2.execute(
                        "INSERT OR IGNORE INTO relationship_state (user_id, type_id, switched_at) VALUES (?, 'default', ?)",
                        (user_id, now)
                    )
        except Exception:
            pass
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/whitelist/remove", methods=["POST"])
def remove_whitelist():
    """删除白名单用户"""
    data = request.json
    qq_id = data.get("qq_id", "")
    if not qq_id:
        return jsonify({"ok": False, "error": "缺少 qq_id"})
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_conn() as conn:
            conn.execute("DELETE FROM chat_whitelist WHERE qq_id = ?", (qq_id,))
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})



# ========== 多维性格 API ==========

@app.route("/api/dimensions/info", methods=["GET"])
def get_dimensions_info():
    """获取多维性格维度定义信息"""
    from src.cognition.personality_dimensions import PERSONALITY_DIMENSIONS
    return jsonify(PERSONALITY_DIMENSIONS)


@app.route("/api/dimensions/<persona_name>", methods=["GET"])
def get_persona_dimensions(persona_name):
    """获取指定人设的多维性格数据"""
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    dims = mgr.get_dimensions(persona_name)
    baseline = mgr.get_baseline(persona_name)
    return jsonify({"dimensions": dims, "baseline": baseline})


@app.route("/api/dimensions/<persona_name>", methods=["POST"])
def save_persona_dimensions(persona_name):
    """保存指定人设的多维性格数据"""
    data = request.json
    dimensions = data.get("dimensions", {})
    note = data.get("note", "手动调整")
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    mgr.save_dimensions(persona_name, dimensions, source="manual", note=note)
    return jsonify({"ok": True, "msg": f"{persona_name} 多维性格已保存"})


@app.route("/api/dimensions/<persona_name>/history", methods=["GET"])
def get_dimensions_history(persona_name):
    """获取多维性格历史记录"""
    hours = request.args.get("hours", 8, type=int)
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    history = mgr.get_history(persona_name, hours=hours)
    return jsonify(history)


@app.route("/api/dimensions/<persona_name>/rollback", methods=["POST"])
def rollback_dimensions(persona_name):
    """回退到指定历史状态"""
    data = request.json
    history_id = data.get("history_id")
    if not history_id:
        return jsonify({"ok": False, "msg": "缺少 history_id"})
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    result = mgr.rollback_to_time(persona_name, history_id)
    return jsonify(result)


@app.route("/api/dimensions/<persona_name>/restore-baseline", methods=["POST"])
def restore_dimensions_baseline(persona_name):
    """恢复到基线多维性格"""
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    dims = mgr.restore_baseline(persona_name)
    return jsonify({"ok": True, "dimensions": dims})


@app.route("/api/dimensions/<persona_name>/analyze", methods=["POST"])
def analyze_dimensions(persona_name):
    """从人设描述自动分析多维性格"""
    persona_data = load_persona(persona_name)
    if not persona_data:
        return jsonify({"ok": False, "msg": f"人设 {persona_name} 不存在"})
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    dims = mgr.analyze_from_persona(persona_name, persona_data)
    mgr.save_dimensions(persona_name, dims, source="ai_analysis", note="从人设描述自动分析")
    return jsonify({"ok": True, "dimensions": dims})


@app.route("/api/dimensions/all", methods=["GET"])
def get_all_dimensions():
    """获取所有人设的多维性格数据"""
    from src.cognition.personality_dimensions import PersonalityDimensionManager
    mgr = PersonalityDimensionManager()
    return jsonify(mgr.get_all_persona_dimensions())


# ========== 人格心理画像 API ==========

@app.route("/api/persona-psychology/info", methods=["GET"])
def get_persona_psychology_info():
    """获取人格心理画像维度定义"""
    from src.cognition.persona_psychology import PERSONA_PSYCHOLOGY_DIMENSIONS
    return jsonify(PERSONA_PSYCHOLOGY_DIMENSIONS)


@app.route("/api/persona-psychology/<persona_name>", methods=["GET"])
def get_persona_psychology(persona_name):
    """获取指定人设的心理画像"""
    from src.cognition.persona_psychology import PersonaPsychologyManager
    mgr = PersonaPsychologyManager()
    return jsonify(mgr.get_profile(persona_name))


@app.route("/api/persona-psychology/<persona_name>", methods=["POST"])
def save_persona_psychology(persona_name):
    """保存指定人设的心理画像"""
    data = request.json
    dimensions = data.get("dimensions", {})
    note = data.get("note", "手动调整")
    from src.cognition.persona_psychology import PersonaPsychologyManager
    mgr = PersonaPsychologyManager()
    mgr.save_profile(persona_name, dimensions, source="manual", note=note)
    return jsonify({"ok": True, "msg": f"{persona_name} 心理画像已保存"})


@app.route("/api/persona-psychology/<persona_name>/baseline", methods=["POST"])
def create_psychology_baseline(persona_name):
    """为人设创建基线心理画像"""
    persona_data = load_persona(persona_name)
    if not persona_data:
        return jsonify({"ok": False, "msg": f"人设 {persona_name} 不存在"})
    from src.cognition.persona_psychology import PersonaPsychologyManager
    mgr = PersonaPsychologyManager()
    dims = mgr.create_baseline(persona_name, persona_data)
    return jsonify({"ok": True, "dimensions": dims})


@app.route("/api/persona-psychology/<persona_name>/restore", methods=["POST"])
def restore_psychology_baseline(persona_name):
    """恢复到基线心理画像"""
    from src.cognition.persona_psychology import PersonaPsychologyManager
    mgr = PersonaPsychologyManager()
    dims = mgr.restore_baseline(persona_name)
    return jsonify({"ok": True, "dimensions": dims})


@app.route("/api/persona-psychology/<persona_name>/history", methods=["GET"])
def get_psychology_history(persona_name):
    """获取心理画像历史"""
    hours = request.args.get("hours", 48, type=int)
    from src.cognition.persona_psychology import PersonaPsychologyManager
    mgr = PersonaPsychologyManager()
    return jsonify(mgr.get_history(persona_name, hours=hours))


@app.route("/api/persona-psychology/all", methods=["GET"])
def get_all_psychology_profiles():
    """获取所有人设的心理画像"""
    from src.cognition.persona_psychology import PersonaPsychologyManager
    mgr = PersonaPsychologyManager()
    return jsonify(mgr.get_all_profiles())


# ========== 心理健康与分析 API ==========
import sqlite3 as _sqlite3
import json as _json

MENTAL_HEALTH_DB = DATA_DIR / "mental_health.db"

def _get_mh_db():
    """获取心理健康数据库连接"""
    MENTAL_HEALTH_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = _sqlite3.connect(str(MENTAL_HEALTH_DB))
    conn.row_factory = _sqlite3.Row
    conn.execute("CREATE TABLE IF NOT EXISTS mental_health_analysis ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "user_id TEXT NOT NULL,"
        "persona_name TEXT NOT NULL,"
        "analysis_data TEXT NOT NULL,"
        "chart_data TEXT NOT NULL,"
        "suggestions TEXT DEFAULT '',"
        "created_at TEXT NOT NULL,"
        "updated_at TEXT NOT NULL,"
        "UNIQUE(user_id, persona_name)"
    ")")
    conn.commit()
    return conn

def _load_psychology_data(user_id):
    """加载用户心理画像数据（兼容旧版）"""
    data = {}
    # 从主数据库读取
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_psychology_conn() as conn:
            row = conn.execute("SELECT * FROM user_psychology WHERE user_id = ?", (user_id,)).fetchone()
            if row:
                data["personality"] = _json.loads(row["personality"]) if row["personality"] else {}
                data["emotional_stability"] = row["emotional_stability"]
                data["communication_style"] = row["communication_style"]
                data["emotional_needs"] = _json.loads(row["emotional_needs"]) if row["emotional_needs"] else []
                data["mental_state"] = row["mental_state"]
                data["social_preference"] = row["social_preference"]
                data["values_keywords"] = _json.loads(row["values_keywords"]) if row["values_keywords"] else []
                data["stress_indicators"] = _json.loads(row["stress_indicators"]) if row["stress_indicators"] else []
                data["coping_style"] = row["coping_style"]
                data["attachment_style"] = row["attachment_style"]
                data["user_type"] = row["user_type"] if "user_type" in row.keys() else "未分类"
                data["analysis_count"] = row["analysis_count"]
                data["last_evidence"] = _json.loads(row["last_evidence"]) if "last_evidence" in row.keys() and row["last_evidence"] else []
                data["last_confidence"] = row["last_confidence"] if "last_confidence" in row.keys() else 0.0
                data["last_source"] = row["last_source"] if "last_source" in row.keys() else "recent_chat"
    except Exception as e:
        pass
    # 从旧版 data 文件夹读取
    if not data:
        for db_file in DATA_DIR.glob("**/user_data.db"):
            try:
                conn = _sqlite3.connect(str(db_file))
                conn.row_factory = _sqlite3.Row
                tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                if "user_psychology" in tables:
                    row = conn.execute("SELECT * FROM user_psychology WHERE user_id = ?", (user_id,)).fetchone()
                    if row:
                        for key in row.keys():
                            val = row[key]
                            if isinstance(val, str) and val.startswith('{'):
                                data[key] = _json.loads(val)
                            elif isinstance(val, str) and val.startswith('['):
                                data[key] = _json.loads(val)
                            else:
                                data[key] = val
                conn.close()
            except:
                pass
    return data

def _load_chat_data(user_id, limit=50):
    """加载聊天记录"""
    messages = []
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_conn() as conn:
            rows = conn.execute("SELECT role, content, timestamp FROM chat_history "
                "WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit)).fetchall()
            for r in rows:
                messages.append({"role": r["role"], "content": r["content"], "time": r["timestamp"]})
    except:
        pass
    return messages

@app.route("/api/safety/state", methods=["GET"])
def list_safety_state():
    """读取 SafetyMonitor 当前风险状态，供后续风险面板使用。"""
    user_filter = request.args.get("user_id", "").strip()
    rows = []
    seen = set()
    db_candidates = [get_active_db_path()]
    db_candidates.extend(DATA_DIR.glob("accounts/*/*/user_data.db"))
    db_candidates.extend(DATA_DIR.glob("chatbot*.db"))

    for db_file in db_candidates:
        db_path = Path(db_file)
        if not db_path.exists() or db_path in seen:
            continue
        seen.add(db_path)
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "safety_state" not in tables:
                conn.close()
                continue
            columns = [c[1] for c in conn.execute("PRAGMA table_info(safety_state)").fetchall()]
            select_cols = ["user_id", "assessment_json", "risk_level", "updated_at"]
            sql = "SELECT " + ", ".join(select_cols) + " FROM safety_state"
            params = []
            if user_filter:
                sql += " WHERE user_id = ?"
                params.append(user_filter)
            for r in conn.execute(sql, params).fetchall():
                item = dict(r)
                try:
                    item["assessment"] = _json.loads(item.get("assessment_json") or "{}")
                except Exception:
                    item["assessment"] = {}
                item["db_path"] = str(db_path.relative_to(BASE_DIR)) if str(db_path).startswith(str(BASE_DIR)) else str(db_path)
                rows.append(item)
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    rows.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return jsonify({"ok": True, "data": rows})

def _scan_user_data_dbs():
    """扫描新版/旧版用户数据库，去重返回 Path 列表。"""
    seen = set()
    candidates = [get_active_db_path()]
    candidates.extend(DATA_DIR.glob("accounts/*/*/user_data.db"))
    candidates.extend(DATA_DIR.glob("chatbot*.db"))
    for db_file in candidates:
        db_path = Path(db_file)
        if not db_path.exists() or db_path in seen:
            continue
        seen.add(db_path)
        yield db_path

def _rel_db_path(db_path: Path) -> str:
    try:
        return str(db_path.relative_to(BASE_DIR))
    except Exception:
        return str(db_path)

_chat_record_parser = None

def _get_chat_record_parser():
    global _chat_record_parser
    if _chat_record_parser is None:
        from src.memory.chat_record_parser import ChatRecordParser
        _chat_record_parser = ChatRecordParser()
    return _chat_record_parser

def _prepare_chat_record_parser(user_id: str, persona: str):
    from src.memory.database import Database
    db = Database()
    if persona:
        db.set_persona(persona)
    if user_id:
        db.set_user(user_id)
    parser = _get_chat_record_parser()
    if persona:
        parser.db.set_persona(persona)
    if user_id:
        parser.db.set_user(user_id)
    return parser

def _ensure_growth_goal_tables(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS growth_goals (
            goal_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            goal_type TEXT DEFAULT '生活习惯',
            status TEXT DEFAULT 'active',
            description TEXT DEFAULT '',
            micro_tasks TEXT DEFAULT '[]',
            next_follow_up TEXT DEFAULT '',
            pressure_level INTEGER DEFAULT 2,
            allow_proactive INTEGER DEFAULT 1,
            source TEXT DEFAULT 'webui',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT DEFAULT ''
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_growth_goals_user ON growth_goals(user_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_growth_goals_follow ON growth_goals(user_id, next_follow_up)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS growth_goal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            goal_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

def _parse_micro_tasks(value):
    if isinstance(value, list):
        return value
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            lines = [x.strip() for x in value.replace("；", "\n").replace(";", "\n").splitlines() if x.strip()]
            return [{"text": x, "done": False} for x in lines]
    return []

def _growth_goal_target_db(user_id: str, persona: str = "") -> Path:
    persona = persona or load_config().get("default_persona", "Theresa")
    if user_id:
        return DATA_DIR / "accounts" / user_id / persona / "user_data.db"
    return get_active_db_path()

@app.route("/api/growth-goals", methods=["GET"])
def list_growth_goals():
    user_id = request.args.get("user_id", "").strip()
    status = request.args.get("status", "").strip()
    query = request.args.get("q", "").strip()
    limit = min(max(int(request.args.get("limit", 200) or 200), 1), 500)
    rows = []
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "growth_goals" not in tables:
                conn.close()
                continue
            clauses = []
            params = []
            if user_id:
                clauses.append("user_id = ?")
                params.append(user_id)
            if status:
                clauses.append("status = ?")
                params.append(status)
            if query:
                clauses.append("(title LIKE ? OR description LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            sql = "SELECT * FROM growth_goals"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 WHEN 'completed' THEN 2 ELSE 3 END, updated_at DESC LIMIT ?"
            params.append(limit)
            for r in conn.execute(sql, params).fetchall():
                item = dict(r)
                item["db_path"] = _rel_db_path(db_path)
                item["micro_tasks"] = _parse_micro_tasks(item.get("micro_tasks"))
                rows.append(item)
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    return jsonify({"ok": True, "data": rows[:limit]})

@app.route("/api/growth-goals", methods=["POST"])
def create_growth_goal():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id", "")).strip()
    title = str(data.get("title", "")).strip()
    if not user_id or not title:
        return jsonify({"ok": False, "msg": "缺少 user_id 或 title"}), 400
    db_path = _growth_goal_target_db(user_id, str(data.get("persona", "")).strip())
    db_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    goal_id = str(uuid.uuid4())
    micro_tasks = _parse_micro_tasks(data.get("micro_tasks"))
    status = str(data.get("status", "active")).strip() or "active"
    if status not in {"active", "paused", "completed", "archived"}:
        status = "active"
    try:
        conn = _sqlite3.connect(str(db_path))
        _ensure_growth_goal_tables(conn)
        conn.execute(
            "INSERT INTO growth_goals "
            "(goal_id, user_id, title, goal_type, status, description, micro_tasks, next_follow_up, "
            "pressure_level, allow_proactive, source, created_at, updated_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                goal_id, user_id, title, str(data.get("goal_type", "其他") or "其他"),
                status, str(data.get("description", "") or ""),
                json.dumps(micro_tasks, ensure_ascii=False),
                str(data.get("next_follow_up", "") or ""),
                max(0, min(5, int(data.get("pressure_level", 2) or 0))),
                1 if data.get("allow_proactive", True) else 0,
                "webui", now, now, now if status == "completed" else "",
            ),
        )
        conn.execute(
            "INSERT INTO growth_goal_events (goal_id, user_id, event_type, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (goal_id, user_id, "created_from_webui", title, now),
        )
        conn.commit()
        conn.close()
        return jsonify({"ok": True, "msg": "已创建目标", "goal_id": goal_id, "db_path": _rel_db_path(db_path)})
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return jsonify({"ok": False, "msg": f"创建失败：{e}"}), 500

@app.route("/api/growth-goals/update", methods=["POST"])
def update_growth_goal():
    data = request.get_json(silent=True) or {}
    goal_id = str(data.get("goal_id", "")).strip()
    if not goal_id:
        return jsonify({"ok": False, "msg": "缺少 goal_id"}), 400
    updated = False
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    allowed = {"title", "goal_type", "status", "description", "micro_tasks", "next_follow_up", "pressure_level", "allow_proactive"}
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "growth_goals" not in tables:
                conn.close()
                continue
            old = conn.execute("SELECT user_id FROM growth_goals WHERE goal_id = ?", (goal_id,)).fetchone()
            if not old:
                conn.close()
                continue
            updates = []
            params = []
            for key in allowed:
                if key not in data:
                    continue
                value = data.get(key)
                if key == "micro_tasks":
                    value = json.dumps(_parse_micro_tasks(value), ensure_ascii=False)
                if key == "pressure_level":
                    value = max(0, min(5, int(value or 0)))
                if key == "allow_proactive":
                    value = 1 if value else 0
                updates.append(f"{key} = ?")
                params.append(value)
            updates.append("updated_at = ?")
            params.append(now)
            if data.get("status") == "completed":
                updates.append("completed_at = ?")
                params.append(now)
            params.append(goal_id)
            conn.execute("UPDATE growth_goals SET " + ", ".join(updates) + " WHERE goal_id = ?", params)
            conn.execute(
                "INSERT INTO growth_goal_events (goal_id, user_id, event_type, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (goal_id, old["user_id"], "updated_from_webui", json.dumps(data, ensure_ascii=False), now),
            )
            conn.commit()
            conn.close()
            updated = True
            break
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    return jsonify({"ok": updated, "msg": "已更新" if updated else "未找到目标"})

@app.route("/api/growth-goals/delete", methods=["POST"])
def delete_growth_goal():
    data = request.get_json(silent=True) or {}
    goal_id = str(data.get("goal_id", "")).strip()
    if not goal_id:
        return jsonify({"ok": False, "msg": "缺少 goal_id"}), 400
    deleted = False
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            cur = conn.execute("DELETE FROM growth_goals WHERE goal_id = ?", (goal_id,))
            conn.execute("DELETE FROM growth_goal_events WHERE goal_id = ?", (goal_id,))
            conn.commit()
            conn.close()
            if cur.rowcount:
                deleted = True
                break
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    return jsonify({"ok": deleted, "msg": "已删除" if deleted else "未找到目标"})

@app.route("/api/memory-ledger/items", methods=["GET"])
def list_memory_ledger_items():
    """读取统一记忆账本。支持 user_id/persona/q/type/include_pending 过滤。"""
    user_id = request.args.get("user_id", "").strip()
    persona = request.args.get("persona", "").strip()
    query = request.args.get("q", "").strip()
    mem_type = request.args.get("type", "").strip()
    status = request.args.get("status", "").strip()
    include_pending = request.args.get("include_pending", "1") in ("1", "true", "yes")
    limit = min(max(int(request.args.get("limit", 100) or 100), 1), 500)

    rows = []
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "memory_ledger" not in tables:
                conn.close()
                continue

            clauses = []
            params = []
            if user_id:
                clauses.append("user_id = ?")
                params.append(user_id)
            if persona:
                clauses.append("persona = ?")
                params.append(persona)
            if mem_type:
                clauses.append("type = ?")
                params.append(mem_type)
            if status:
                clauses.append("consent_status = ?")
                params.append(status)
            if query:
                clauses.append("(content LIKE ? OR evidence LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            if not include_pending:
                clauses.append("consent_status IN ('auto', 'confirmed')")
            sql = "SELECT * FROM memory_ledger"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            for r in conn.execute(sql, params).fetchall():
                item = dict(r)
                item["db_path"] = _rel_db_path(db_path)
                item["is_superseded"] = bool(item.get("consent_status") == "rejected")
                rows.append(item)
            conn.close()
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    rows.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify({"ok": True, "data": rows[:limit]})

@app.route("/api/memory-ledger/supersede", methods=["POST"])
def supersede_memory_ledger_item():
    """用新记忆覆盖旧记忆，保留 supersedes 链并同步 FTS。"""
    data = request.get_json(silent=True) or {}
    old_id = str(data.get("memory_id", "")).strip()
    new_content = str(data.get("content", "")).strip()
    if not old_id or not new_content:
        return jsonify({"ok": False, "msg": "缺少 memory_id 或 content"}), 400

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    created = None
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            if "memory_ledger" not in tables:
                conn.close()
                continue
            old = conn.execute("SELECT * FROM memory_ledger WHERE memory_id = ?", (old_id,)).fetchone()
            if not old:
                conn.close()
                continue
            old = dict(old)
            new_id = str(uuid.uuid4())
            evidence = str(data.get("evidence", "")).strip() or f"WebUI 覆盖旧记忆：{old.get('content', '')[:160]}"
            confidence = float(data.get("confidence", old.get("confidence", 0.75)) or 0.75)
            confidence = max(0.0, min(1.0, confidence))
            status = str(data.get("consent_status", "confirmed")).strip() or "confirmed"
            if status not in {"auto", "confirmed", "pending", "rejected"}:
                status = "confirmed"
            row = (
                new_id,
                old.get("user_id", ""),
                old.get("persona", ""),
                str(data.get("type", old.get("type", "fact")) or "fact"),
                new_content,
                "webui_supersede",
                confidence,
                str(data.get("sensitivity", old.get("sensitivity", "low")) or "low"),
                status,
                now,
                "",
                str(data.get("expires_at", old.get("expires_at", "")) or ""),
                int(old.get("version") or 1) + 1,
                old_id,
                evidence,
            )
            conn.execute(
                "INSERT INTO memory_ledger "
                "(memory_id, user_id, persona, type, content, source, confidence, sensitivity, consent_status, "
                "created_at, last_used_at, expires_at, version, supersedes, evidence) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            conn.execute("UPDATE memory_ledger SET consent_status = 'rejected' WHERE memory_id = ?", (old_id,))
            if "memory_ledger_fts" in tables:
                try:
                    conn.execute(
                        "INSERT INTO memory_ledger_fts (memory_id, content, evidence) VALUES (?, ?, ?)",
                        (new_id, new_content, evidence),
                    )
                except Exception:
                    pass
            conn.commit()
            conn.close()
            created = {"memory_id": new_id, "db_path": _rel_db_path(db_path)}
            break
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            return jsonify({"ok": False, "msg": f"覆盖失败：{e}"}), 500

    return jsonify({"ok": bool(created), "msg": "已覆盖" if created else "未找到旧记忆", "data": created})

@app.route("/api/memory-ledger/consent", methods=["POST"])
def update_memory_ledger_consent():
    """确认/拒绝/挂起账本记忆。"""
    data = request.get_json(silent=True) or {}
    memory_id = str(data.get("memory_id", "")).strip()
    status = str(data.get("status", "")).strip()
    if not memory_id or status not in {"auto", "confirmed", "rejected", "pending"}:
        return jsonify({"ok": False, "msg": "memory_id 或 status 无效"}), 400

    updated = False
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            cur = conn.execute(
                "UPDATE memory_ledger SET consent_status = ? WHERE memory_id = ?",
                (status, memory_id),
            )
            conn.commit()
            conn.close()
            if cur.rowcount:
                updated = True
                break
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    return jsonify({"ok": updated, "msg": "已更新" if updated else "未找到记忆"})

@app.route("/api/memory-ledger/delete", methods=["POST"])
def delete_memory_ledger_item():
    """删除账本记忆，并同步清理 FTS 表。"""
    data = request.get_json(silent=True) or {}
    memory_id = str(data.get("memory_id", "")).strip()
    if not memory_id:
        return jsonify({"ok": False, "msg": "缺少 memory_id"}), 400

    deleted = False
    for db_path in _scan_user_data_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            cur = conn.execute("DELETE FROM memory_ledger WHERE memory_id = ?", (memory_id,))
            if "memory_ledger_fts" in tables:
                conn.execute("DELETE FROM memory_ledger_fts WHERE memory_id = ?", (memory_id,))
            conn.commit()
            conn.close()
            if cur.rowcount:
                deleted = True
                break
        except Exception:
            try:
                conn.close()
            except Exception:
                pass

    return jsonify({"ok": deleted, "msg": "已删除" if deleted else "未找到记忆"})

@app.route("/api/chat-record/import_text", methods=["POST"])
def import_chat_record_text():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id", "")).strip()
    persona = str(data.get("persona", "")).strip()
    text_content = str(data.get("text", "") or data.get("content", "")).strip()
    source_name = str(data.get("source_name", "manual_text")).strip() or "manual_text"
    if not user_id:
        return jsonify({"ok": False, "msg": "缺少 user_id"}), 400
    if not text_content:
        return jsonify({"ok": False, "msg": "缺少聊天记录文本"}), 400
    try:
        parser = _prepare_chat_record_parser(user_id, persona)
        _, analysis = parser.parse_text_content(text_content, user_id, source_name=source_name)
        stats = parser.get_record_stats(user_id)
        return jsonify({
            "ok": True,
            "msg": "导入成功",
            "data": {
                "total_messages": int(getattr(analysis, "total_messages", 0) or 0),
                "participants": getattr(analysis, "participants", {}) or {},
                "time_range": getattr(analysis, "time_range", "") or "",
                "topic_keywords": getattr(analysis, "topic_keywords", []) or [],
                "stats": stats,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"导入失败: {e}"}), 500

@app.route("/api/chat-record/import_file", methods=["POST"])
def import_chat_record_file():
    user_id = str(request.form.get("user_id", "")).strip()
    persona = str(request.form.get("persona", "")).strip()
    if not user_id:
        return jsonify({"ok": False, "msg": "缺少 user_id"}), 400
    if "file" not in request.files:
        return jsonify({"ok": False, "msg": "未收到文件"}), 400
    file = request.files["file"]
    if not file or not file.filename:
        return jsonify({"ok": False, "msg": "文件名为空"}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in {".zip", ".html", ".htm", ".txt", ".mht"}:
        return jsonify({"ok": False, "msg": "仅支持 zip/html/txt/mht"}), 400

    tmp_path = None
    try:
        tmp_dir = Path(tempfile.mkdtemp(prefix="crown_chat_import_", dir=str(DATA_DIR / "backups")))
        tmp_path = tmp_dir / (Path(file.filename).name or f"chat_record{suffix}")
        file.save(tmp_path)
        parser = _prepare_chat_record_parser(user_id, persona)
        _, analysis = parser.parse_archive(str(tmp_path), user_id)
        stats = parser.get_record_stats(user_id)
        return jsonify({
            "ok": True,
            "msg": "导入成功",
            "data": {
                "total_messages": int(getattr(analysis, "total_messages", 0) or 0),
                "participants": getattr(analysis, "participants", {}) or {},
                "time_range": getattr(analysis, "time_range", "") or "",
                "topic_keywords": getattr(analysis, "topic_keywords", []) or [],
                "stats": stats,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"导入失败: {e}"}), 500
    finally:
        try:
            if tmp_path and tmp_path.parent.exists():
                shutil.rmtree(tmp_path.parent, ignore_errors=True)
        except Exception:
            pass

@app.route("/api/chat-record/stats", methods=["GET"])
def get_chat_record_stats():
    user_id = str(request.args.get("user_id", "")).strip()
    persona = str(request.args.get("persona", "")).strip()
    if not user_id:
        return jsonify({"ok": True, "data": {"total_records": 0, "total_sources": 0}})
    try:
        parser = _prepare_chat_record_parser(user_id, persona)
        stats = parser.get_record_stats(user_id)
        return jsonify({"ok": True, "data": stats})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"读取失败: {e}", "data": {"total_records": 0, "total_sources": 0}}), 500

@app.route("/api/chat-record/analysis", methods=["GET"])
def get_chat_record_analysis():
    user_id = str(request.args.get("user_id", "")).strip()
    persona = str(request.args.get("persona", "")).strip()
    limit = min(max(int(request.args.get("limit", 10) or 10), 1), 100)
    if not user_id:
        return jsonify({"ok": True, "data": []})
    try:
        parser = _prepare_chat_record_parser(user_id, persona)
        rows = parser.get_user_analysis(user_id, limit=limit)
        for row in rows:
            for key in ("participants", "topic_keywords", "user_behavior"):
                raw = row.get(key)
                if isinstance(raw, str):
                    try:
                        row[key] = json.loads(raw)
                    except Exception:
                        pass
        return jsonify({"ok": True, "data": rows})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"读取失败: {e}", "data": []}), 500

@app.route("/api/chat-record/items", methods=["GET"])
def get_chat_record_items():
    user_id = str(request.args.get("user_id", "")).strip()
    persona = str(request.args.get("persona", "")).strip()
    limit = min(max(int(request.args.get("limit", 50) or 50), 1), 300)
    if not user_id:
        return jsonify({"ok": True, "data": []})
    try:
        parser = _prepare_chat_record_parser(user_id, persona)
        rows = parser.get_user_records(user_id, limit=limit)
        return jsonify({"ok": True, "data": rows})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"读取失败: {e}", "data": []}), 500

@app.route("/api/chat-record/coldstart_summary", methods=["POST"])
def generate_chat_record_coldstart_summary():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id", "")).strip()
    persona = str(data.get("persona", "")).strip()
    limit = min(max(int(data.get("limit", 200) or 200), 50), 500)
    if not user_id:
        return jsonify({"ok": False, "msg": "缺少 user_id"}), 400
    try:
        parser = _prepare_chat_record_parser(user_id, persona)
        rows = parser.get_user_records(user_id, limit=limit) or []
        if not rows:
            return jsonify({"ok": True, "msg": "暂无可用于冷启动的聊天记录", "data": {"candidates": [], "inserted": {"ledger": 0, "long_term": 0}}})

        analysis_rows = parser.get_user_analysis(user_id, limit=1) or []
        top_analysis = analysis_rows[0] if analysis_rows else {}
        keywords = top_analysis.get("topic_keywords", [])
        if isinstance(keywords, str):
            try:
                keywords = json.loads(keywords)
            except Exception:
                keywords = []
        keywords = [str(k).strip() for k in (keywords or []) if str(k).strip()][:8]

        msg_count = len(rows)
        avg_len = int(sum(len(str(r.get("content", ""))) for r in rows) / max(1, msg_count))
        q_count = sum(1 for r in rows if ("?" in str(r.get("content", "")) or "？" in str(r.get("content", ""))))
        question_ratio = round((q_count / max(1, msg_count)) * 100, 1)
        participants = sorted({str(r.get("sender", "")).strip() for r in rows if str(r.get("sender", "")).strip()})[:6]
        times = [str(r.get("timestamp", "")).strip() for r in rows if str(r.get("timestamp", "")).strip()]
        time_start = times[-1] if times else ""
        time_end = times[0] if times else ""

        topic_text = "、".join(keywords) if keywords else "暂无明显高频话题"
        people_text = "、".join(participants) if participants else "暂无"
        candidates = [
            {
                "memory_type": "event",
                "content": f"聊天冷启动摘要：最近 {msg_count} 条记录显示，主要话题为 {topic_text}。",
                "confidence": 0.62,
                "consent_status": "pending",
            },
            {
                "memory_type": "relationship",
                "content": f"聊天冷启动摘要：近期互动参与者包括 {people_text}，问句占比约 {question_ratio}%。",
                "confidence": 0.60,
                "consent_status": "pending",
            },
            {
                "memory_type": "fact",
                "content": f"聊天冷启动摘要：平均消息长度约 {avg_len} 字，时间范围 {time_start or '未知'} 至 {time_end or '未知'}。",
                "confidence": 0.58,
                "consent_status": "auto",
            },
        ]

        from src.memory.ledger import MemoryLedger
        from src.memory.database import Database
        persona_name = persona or load_config().get("default_persona", "Theresa")
        ledger = MemoryLedger(user_id=user_id, persona=persona_name)
        inserted_ledger = 0
        inserted_long = 0
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        evidence = {
            "source": "chat_records",
            "sample_size": msg_count,
            "keywords": keywords,
            "time_range": {"start": time_start, "end": time_end},
        }
        for item in candidates:
            ledger.add(
                content=item["content"],
                memory_type=item["memory_type"],
                source="chat_coldstart",
                confidence=item["confidence"],
                consent_status=item["consent_status"],
                evidence=evidence,
            )
            inserted_ledger += 1

        db = Database()
        if persona_name:
            db.set_persona(persona_name)
        if user_id:
            db.set_user(user_id)
        with db.get_conn() as conn:
            for item in candidates:
                conn.execute(
                    "INSERT INTO long_term_memory (user_id, category, content, importance, access_count, created_at, last_accessed) "
                    "VALUES (?, ?, ?, ?, 0, ?, ?)",
                    (user_id, "冷启动摘要", item["content"], 3, now, now),
                )
                inserted_long += 1

        return jsonify({
            "ok": True,
            "msg": "冷启动摘要生成完成",
            "data": {
                "candidates": candidates,
                "inserted": {"ledger": inserted_ledger, "long_term": inserted_long},
                "sample_size": msg_count,
                "keywords": keywords,
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "msg": f"生成失败: {e}"}), 500

@app.route("/api/mental-health/users", methods=["GET"])
def list_mh_users():
    """列出所有有心理画像数据的用户"""
    users = set()
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_psychology_conn() as conn:
            rows = conn.execute("SELECT user_id FROM user_psychology").fetchall()
            for r in rows:
                users.add(r["user_id"])
    except:
        pass
    conn = _get_mh_db()
    rows = conn.execute("SELECT DISTINCT user_id FROM mental_health_analysis").fetchall()
    for r in rows:
        users.add(r["user_id"])
    conn.close()
    return jsonify({"ok": True, "users": sorted(list(users))})

@app.route("/api/mental-health/personas", methods=["GET"])
def list_mh_personas():
    """列出所有人设"""
    personas = []
    for f in PERSONAS_DIR.glob("*.yaml"):
        personas.append(f.stem)
    return jsonify({"ok": True, "personas": sorted(personas)})

@app.route("/api/mental-health/data", methods=["GET"])
def get_mental_health_data():
    """获取指定用户+人设的心理健康分析数据"""
    user_id = request.args.get("user_id", "")
    persona_name = request.args.get("persona", "")
    if not user_id:
        return jsonify({"ok": False, "error": "缺少 user_id"})
    psych_data = _load_psychology_data(user_id)
    conn = _get_mh_db()
    row = conn.execute("SELECT * FROM mental_health_analysis WHERE user_id = ? AND persona_name = ?",
        (user_id, persona_name)).fetchone()
    conn.close()
    if row:
        analysis = _json.loads(row["analysis_data"])
        if psych_data:
            for key in ("last_evidence", "last_confidence", "last_source", "last_analyzed"):
                if key in psych_data:
                    analysis[key] = psych_data[key]
        return jsonify({"ok": True, "data": {
            "user_id": row["user_id"],
            "persona_name": row["persona_name"],
            "analysis": analysis,
            "chart": _json.loads(row["chart_data"]),
            "suggestions": row["suggestions"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }})
    return jsonify({"ok": True, "data": None})

@app.route("/api/mental-health/history", methods=["GET"])
def get_mental_health_history():
    """读取心理画像变化历史，包含证据、来源和置信度。"""
    user_id = request.args.get("user_id", "").strip()
    dimension = request.args.get("dimension", "").strip()
    limit = min(max(int(request.args.get("limit", 30) or 30), 1), 100)
    if not user_id:
        return jsonify({"ok": False, "error": "缺少 user_id"}), 400

    try:
        from src.memory.database import Database
        db = Database()
        with db.get_psychology_conn() as conn:
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(psychology_history)").fetchall()}
            select_cols = ["id", "user_id", "timestamp", "dimension", "old_value", "new_value", "trigger_text", "confidence"]
            if "evidence" in cols:
                select_cols.append("evidence")
            if "source" in cols:
                select_cols.append("source")
            sql = "SELECT " + ", ".join(select_cols) + " FROM psychology_history WHERE user_id = ?"
            params = [user_id]
            if dimension:
                sql += " AND dimension = ?"
                params.append(dimension)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = []
            for r in conn.execute(sql, params).fetchall():
                item = dict(r)
                if "evidence" in item:
                    try:
                        item["evidence"] = _json.loads(item["evidence"] or "[]")
                    except Exception:
                        item["evidence"] = []
                else:
                    item["evidence"] = []
                item["source"] = item.get("source") or "recent_chat"
                rows.append(item)
        return jsonify({"ok": True, "data": rows})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/mental-health/generate", methods=["POST"])
def generate_mental_health():
    """生成心理健康分析"""
    data = request.json or {}
    user_id = data.get("user_id", "")
    persona_name = data.get("persona", "")
    if not user_id:
        return jsonify({"ok": False, "error": "缺少 user_id"})
    # 加载数据
    psych_data = _load_psychology_data(user_id)
    chat_data = _load_chat_data(user_id, 30)
    if not psych_data:
        return jsonify({"ok": False, "error": "该用户暂无心理画像数据，请先多聊几次"})
    # 生成图表数据
    personality = psych_data.get("personality", {})
    chart = {
        "radar": {
            "labels": list(personality.keys())[:8],
            "values": list(personality.values())[:8],
        },
        "emotion_stability": psych_data.get("emotional_stability", "未知"),
        "communication": psych_data.get("communication_style", "未知"),
        "mental_state": psych_data.get("mental_state", "正常"),
        "attachment": psych_data.get("attachment_style", "未知"),
        "coping": psych_data.get("coping_style", "未知"),
        "user_type": psych_data.get("user_type", "未分类"),
    }
    # 生成 AI 分析
    suggestions = ""
    try:
        import asyncio as _asyncio
        from src.core.llm import LLMClient
        llm = LLMClient()
        prompt = (
            f"以下是用户 {user_id} 的心理画像数据，请进行心理健康分析并给出建议。\n\n"
            f"性格维度：{_json.dumps(personality, ensure_ascii=False)}\n"
            f"情绪稳定性：{psych_data.get('emotional_stability', '未知')}\n"
            f"沟通风格：{psych_data.get('communication_style', '未知')}\n"
            f"心理状态：{psych_data.get('mental_state', '正常')}\n"
            f"最近证据：{psych_data.get('last_evidence', [])}\n"
            f"置信度：{psych_data.get('last_confidence', 0.0)}\n"
            f"来源：{psych_data.get('last_source', 'recent_chat')}\n"
            f"依恋风格：{psych_data.get('attachment_style', '未知')}\n"
            f"应对方式：{psych_data.get('coping_style', '未知')}\n"
            f"情感需求：{_json.dumps(psych_data.get('emotional_needs', []), ensure_ascii=False)}\n"
            f"压力指标：{_json.dumps(psych_data.get('stress_indicators', []), ensure_ascii=False)}\n"
            f"用户类型：{psych_data.get('user_type', '未分类')}\n\n"
            f"请输出：\n1. 心理健康评估（2-3句）\n2. 潜在风险点（如有）\n3. 个性化建议（3-5条）\n\n"
            f"简洁明了，用中文输出。"
        )
        messages = [{"role": "user", "content": prompt}]
        system_msg = "你是心理健康分析专家。基于用户画像数据进行分析，给出专业但温和的建议。"
        # Flask 同步环境，创建新事件循环
        loop = _asyncio.new_event_loop()
        try:
            suggestions = loop.run_until_complete(
                llm.chat([{"role": "system", "content": system_msg}] + messages)
            )
        finally:
            loop.run_until_complete(llm.close())
            loop.close()
    except Exception as e:
        suggestions = f"AI 分析暂时不可用：{e}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = _get_mh_db()
    conn.execute("INSERT OR REPLACE INTO mental_health_analysis "
        "(user_id, persona_name, analysis_data, chart_data, suggestions, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM mental_health_analysis WHERE user_id=? AND persona_name=?), ?), ?)",
        (user_id, persona_name, _json.dumps(psych_data, ensure_ascii=False),
         _json.dumps(chart, ensure_ascii=False), suggestions, user_id, persona_name, now, now))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "msg": "分析已生成", "data": {
        "analysis": psych_data, "chart": chart, "suggestions": suggestions,
        "updated_at": now
    }})

@app.route("/api/mental-health/delete", methods=["POST"])
def delete_mental_health():
    """删除心理健康分析数据"""
    data = request.json or {}
    user_id = data.get("user_id", "")
    persona_name = data.get("persona", "")
    if not user_id:
        return jsonify({"ok": False, "error": "缺少 user_id"})
    conn = _get_mh_db()
    conn.execute("DELETE FROM mental_health_analysis WHERE user_id = ? AND persona_name = ?",
        (user_id, persona_name))
    conn.commit()
    conn.close()
    return jsonify({"ok": True, "msg": "已删除"})

@app.route("/api/mental-health/open-db", methods=["POST"])
def open_mental_health_db():
    """打开本地心理健康数据库文件"""
    import subprocess
    subprocess.Popen(f'explorer /select,"{MENTAL_HEALTH_DB}"', shell=True)
    return jsonify({"ok": True, "msg": "已打开"})


# ========== 账号配置绑定 API ==========

@app.route("/api/account-binding/<account_id>/<persona_name>", methods=["GET"])
def get_account_binding(account_id, persona_name):
    """获取账号绑定配置"""
    from src.cognition.account_binding import AccountBindingManager
    mgr = AccountBindingManager()
    return jsonify(mgr.get_binding(account_id, persona_name))


@app.route("/api/account-binding/<account_id>/<persona_name>", methods=["POST"])
def save_account_binding(account_id, persona_name):
    """保存账号绑定配置"""
    data = request.json
    from src.cognition.account_binding import AccountBindingManager
    mgr = AccountBindingManager()
    mgr.save_binding(account_id, persona_name, data)
    return jsonify({"ok": True, "msg": "绑定配置已保存"})


@app.route("/api/account-binding/list", methods=["GET"])
def list_account_bindings():
    """列出所有账号绑定"""
    from src.cognition.account_binding import AccountBindingManager
    mgr = AccountBindingManager()
    return jsonify(mgr.list_all_bindings())


@app.route("/api/account-binding/<account_id>/<persona_name>", methods=["DELETE"])
def delete_account_binding(account_id, persona_name):
    """删除账号绑定"""
    from src.cognition.account_binding import AccountBindingManager
    mgr = AccountBindingManager()
    mgr.delete_binding(account_id, persona_name)
    return jsonify({"ok": True})




@app.route("/api/migration/status", methods=["GET"])
def migration_status():
    """检查迁移状态"""
    from db_migrate import get_legacy_data_info
    info = get_legacy_data_info(DATA_DIR)
    flag_file = DATA_DIR / "_migrated.flag"
    migrated = flag_file.exists()
    flag_content = flag_file.read_text(encoding="utf-8") if migrated else ""
    return jsonify({
        "migrated": migrated,
        "flag_content": flag_content,
        "legacy_info": info,
        "new_structure": {
            "accounts": _db_resolver.list_users(),
            "personas": _db_resolver.list_personas(),
        }
    })

@app.route("/api/migration/run", methods=["POST"])
def run_migration():
    """手动触发迁移"""
    from db_migrate import migrate_if_needed
    # 删除标记文件强制重新迁移
    flag_file = DATA_DIR / "_migrated.flag"
    if flag_file.exists():
        flag_file.unlink()
    migrated, msg = migrate_if_needed(BASE_DIR)
    return jsonify({"ok": True, "migrated": migrated, "msg": msg})

SYSTEM_AUDIT_MODULES = [
    {
        "key": "chat",
        "name": "聊天入口",
        "purpose": "接收 QQ 私聊、调用对话流水线并发送回复",
        "files": ["qq_bot.py", "src/plugins/mychat/__init__.py", "src/core/pipeline.py", "src/core/context_builder.py", "src/core/tool_router.py", "src/core/critic_coordinator.py"],
        "tables": ["chat_history", "chat_whitelist"],
    },
    {
        "key": "prompt",
        "name": "人设与回复节奏",
        "purpose": "把人设、关系、时间和回复分次规则写入 system prompt",
        "files": ["src/interaction/prompt.py", "src/core/prompt.py", "personas/Theresa.yaml"],
        "tables": [],
    },
    {
        "key": "memory",
        "name": "记忆账本",
        "purpose": "保存可确认、可覆盖、可检索的长期事实",
        "files": ["src/core/memory_coordinator.py", "src/memory/ledger.py", "src/memory/database.py"],
        "tables": ["memory_ledger", "memory_ledger_fts", "long_term_memory"],
    },
    {
        "key": "growth",
        "name": "成长目标",
        "purpose": "从聊天中沉淀目标、微任务和到期跟进",
        "files": ["src/core/growth_coordinator.py", "src/cognition/growth.py", "src/core/growth.py"],
        "tables": ["growth_goals", "growth_goal_events"],
    },
    {
        "key": "proactive",
        "name": "主动消息",
        "purpose": "调度主动消息、记录发送或跳过原因",
        "files": ["src/interaction/proactive_scheduler.py", "src/interaction/proactive.py"],
        "tables": ["proactive_state", "proactive_events"],
    },
    {
        "key": "safety",
        "name": "安全护栏",
        "purpose": "识别危机等级、边界风险并给主动消息做前置检查",
        "files": ["src/core/safety_coordinator.py", "src/safety/safety_monitor.py", "src/safety/response_protocols.py", "src/safety/risk_schema.py"],
        "tables": ["safety_state", "safety_events"],
    },
    {
        "key": "relationship",
        "name": "关系定制",
        "purpose": "把关系类型、亲疏和自定义规则注入聊天上下文",
        "files": ["src/cognition/relationship.py", "src/cognition/relationship_bridge.py"],
        "tables": ["relationship_state"],
    },
    {
        "key": "account_binding",
        "name": "账号关系绑定",
        "purpose": "把账号、人设和关系状态绑定到同一份上下文",
        "files": ["src/cognition/account_binding.py"],
        "tables": ["account_bindings"],
    },
    {
        "key": "psychology",
        "name": "心理画像",
        "purpose": "记录心理画像、证据、置信度和变化历史",
        "files": ["src/cognition/psychology.py", "src/core/psychology.py"],
        "tables": ["user_psychology", "psychology_history"],
    },
]

SYSTEM_AUDIT_WEBUI_PAGES = [
    {"page": "overview", "name": "系统总览", "target": "runtime", "apis": ["GET /api/stats"], "tables": []},
    {"page": "companion-hub", "name": "陪伴中枢", "target": "db", "apis": ["GET /api/companion-hub/summary"], "tables": ["memory_ledger", "growth_goals", "proactive_events", "relationship_state", "account_bindings"]},
    {"page": "system-audit", "name": "系统自检", "target": "runtime", "apis": ["GET /api/system-audit"], "tables": []},
    {"page": "config", "name": "模型配置", "target": "file", "apis": ["GET /api/config", "POST /api/config"], "tables": []},
    {"page": "persona", "name": "人设控制", "target": "file", "apis": ["GET /api/personas", "GET /api/persona/<name>", "POST /api/persona/<name>"], "tables": []},
    {"page": "scenes", "name": "场景管理", "target": "file", "apis": ["GET /api/scene_groups", "POST /api/scene_group/<name>", "POST /api/scene_group/create"], "tables": []},
    {"page": "tones", "name": "语气管理", "target": "file", "apis": ["GET /api/tone_groups", "POST /api/tone_group/<name>", "POST /api/tone_group/create"], "tables": []},
    {"page": "plugins", "name": "插件控制", "target": "runtime", "apis": ["GET /api/plugins", "POST /api/plugin/toggle", "POST /api/plugins/reload"], "tables": []},
    {"page": "backups", "name": "备份管理", "target": "file", "apis": ["GET /api/backups", "POST /api/backup/generate", "POST /api/backup/restore_all"], "tables": []},
    {"page": "modules", "name": "模块管理", "target": "runtime", "apis": ["GET /api/modules", "POST /api/modules/toggle"], "tables": []},
    {"page": "proactive", "name": "主动消息", "target": "db", "apis": ["GET /api/proactive", "POST /api/proactive", "GET /api/proactive/events"], "tables": ["proactive_state", "proactive_events"]},
    {"page": "growth-goals", "name": "成长目标", "target": "db", "apis": ["GET /api/growth-goals", "POST /api/growth-goals", "POST /api/growth-goals/update", "POST /api/growth-goals/delete"], "tables": ["growth_goals", "growth_goal_events"]},
    {"page": "audio", "name": "音频组", "target": "file", "apis": ["GET /api/audio_groups", "POST /api/audio_group/create", "POST /api/audio_group/<name>/upload"], "tables": []},
    {"page": "relationship", "name": "关系定制", "target": "db", "apis": ["GET /api/relationships", "GET /api/relationship/brief", "POST /api/relationship/save", "POST /api/relationship/switch"], "tables": ["relationship_state", "account_bindings", "growth_goal_events", "memory_ledger", "chat_records", "long_term_memory"]},
    {"page": "whitelist", "name": "白名单", "target": "db", "apis": ["GET /api/whitelist", "POST /api/whitelist/add", "POST /api/whitelist/remove"], "tables": ["chat_whitelist"]},
    {"page": "dimensions", "name": "多维性格", "target": "file", "apis": ["GET /api/dimensions/all", "GET /api/dimensions/<persona_name>", "POST /api/dimensions/<persona_name>"], "tables": []},
    {"page": "persona-psychology", "name": "人格心理画像", "target": "file", "apis": ["GET /api/persona-psychology/all", "GET /api/persona-psychology/<persona_name>", "POST /api/persona-psychology/<persona_name>"], "tables": []},
    {"page": "account-binding", "name": "账号绑定", "target": "db", "apis": ["GET /api/account-binding/list", "GET /api/account-binding/<account_id>/<persona_name>", "POST /api/account-binding/<account_id>/<persona_name>"], "tables": ["account_bindings"]},
    {"page": "mental-health", "name": "心理健康与分析", "target": "db", "apis": ["GET /api/mental-health/users", "GET /api/mental-health/data", "POST /api/mental-health/generate"], "tables": ["user_psychology", "psychology_history"]},
    {"page": "memory-ledger", "name": "记忆账本", "target": "db", "apis": ["GET /api/memory-ledger/items", "POST /api/memory-ledger/consent", "POST /api/memory-ledger/supersede", "POST /api/memory-ledger/delete"], "tables": ["memory_ledger"]},
    {"page": "database", "name": "数据库", "target": "db", "apis": ["GET /api/db/tables", "GET /api/db/table/<name>", "POST /api/db/add_row", "POST /api/db/edit_row", "POST /api/db/delete_row"], "tables": []},
    {"page": "readme", "name": "项目文档", "target": "file", "apis": ["GET /api/readme"], "tables": []},
]

SYSTEM_AUDIT_WEBUI_PAGES.append({
    "page": "chat-import",
    "name": "聊天记录导入",
    "target": "db",
    "apis": [
        "POST /api/chat-record/import_text",
        "POST /api/chat-record/import_file",
        "GET /api/chat-record/stats",
        "GET /api/chat-record/analysis",
        "GET /api/chat-record/items",
        "POST /api/chat-record/coldstart_summary",
    ],
    "tables": ["chat_records", "chat_record_analysis", "memory_ledger", "long_term_memory"],
})

SYSTEM_AUDIT_WEBUI_PAGES.append({
    "page": "eval-console",
    "name": "评测控制台",
    "target": "runtime",
    "apis": [
        "GET /api/eval/scenarios",
        "POST /api/eval/run",
        "GET /api/eval/reports",
        "GET /api/eval/report/<report_id>",
    ],
    "tables": ["chat_records", "memory_ledger", "growth_goals", "user_psychology", "safety_state", "proactive_events"],
})

def _system_audit_route_set():
    routes = set()
    for rule in app.url_map.iter_rules():
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        for method in methods:
            routes.add(f"{method} {rule.rule}")
    return routes

def _system_audit_path(rel_path):
    path = BASE_DIR / rel_path
    return {
        "path": rel_path,
        "exists": path.exists(),
        "kind": "dir" if path.is_dir() else "file",
        "size": path.stat().st_size if path.exists() and path.is_file() else 0,
    }

def _system_audit_db_snapshot():
    import sqlite3
    db_entries = []
    table_counts = {}
    raw_paths = []
    for label, path in get_all_db_paths():
        raw_paths.append((label, Path(path)))
    for extra in [DATA_DIR / "mental_health.db", DATA_DIR / "chatbot.db", DATA_DIR / "chatbot_shared.db"]:
        raw_paths.append((extra.stem, extra))

    seen = set()
    for label, db_path in raw_paths:
        db_path = Path(db_path)
        if db_path in seen or not db_path.exists():
            continue
        seen.add(db_path)
        entry = {"label": str(label), "path": _companion_rel_path(db_path), "ok": True, "tables": {}, "error": ""}
        try:
            conn = _sqlite3.connect(str(db_path))
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
            for (table,) in rows:
                try:
                    count = int(conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0])
                except Exception:
                    count = -1
                entry["tables"][table] = count
                table_counts[table] = table_counts.get(table, 0) + max(count, 0)
            conn.close()
        except Exception as e:
            entry["ok"] = False
            entry["error"] = str(e)
        db_entries.append(entry)
    return db_entries, table_counts

def _system_audit_structure():
    rel_dirs = ["src/core", "src/interaction", "src/cognition", "src/memory", "src/safety", "src/plugins", "personas", "data", "docs", "scripts", "NapCat"]
    result = []
    for rel in rel_dirs:
        path = BASE_DIR / rel
        item = _system_audit_path(rel)
        if path.exists() and path.is_dir():
            item["files"] = len([p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts])
            item["python_files"] = len([p for p in path.rglob("*.py") if "__pycache__" not in p.parts])
        else:
            item["files"] = 0
            item["python_files"] = 0
        result.append(item)
    return result

@app.route("/api/system-audit", methods=["GET"])
def system_audit():
    """只读系统自检：确认项目结构、WebUI 接口和数据库连接状态。"""
    routes = _system_audit_route_set()
    dbs, table_counts = _system_audit_db_snapshot()

    modules = []
    for module in SYSTEM_AUDIT_MODULES:
        files = [_system_audit_path(p) for p in module["files"]]
        missing_files = [f["path"] for f in files if not f["exists"]]
        present_tables = [t for t in module["tables"] if t in table_counts]
        missing_tables = [t for t in module["tables"] if t not in table_counts]
        if missing_files:
            status = "missing_files"
        elif module["tables"] and not present_tables:
            status = "waiting_db"
        elif missing_tables:
            # 页面接口齐全但数据表尚未生成时，统一标记为 waiting_db，避免误判为故障。
            status = "waiting_db"
        else:
            status = "ok"
        modules.append({
            **module,
            "status": status,
            "files": files,
            "present_tables": present_tables,
            "missing_tables": missing_tables,
        })

    pages = []
    for page in SYSTEM_AUDIT_WEBUI_PAGES:
        missing_apis = [api for api in page["apis"] if api not in routes]
        present_tables = [t for t in page["tables"] if t in table_counts]
        missing_tables = [t for t in page["tables"] if t not in table_counts]
        if missing_apis:
            status = "missing_api"
        elif page["tables"] and not present_tables:
            status = "waiting_db"
        elif missing_tables:
            status = "waiting_db"
        else:
            status = "ok"
        pages.append({
            **page,
            "status": status,
            "missing_apis": missing_apis,
            "present_tables": present_tables,
            "missing_tables": missing_tables,
        })

    return jsonify({
        "ok": True,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_dir": str(BASE_DIR),
        "structure": _system_audit_structure(),
        "modules": modules,
        "webui_pages": pages,
        "databases": dbs,
        "table_counts": table_counts,
        "routes_count": len(routes),
        "notes": [
            "系统自检只读，不会修改聊天记录、记忆、目标或配置。",
            "waiting_db 表示代码和接口存在，但当前数据库还没有产生对应表；通常要在聊天触发一次相关能力后出现。",
        ],
    })

EVAL_SCENARIOS = [
    {"key": "base_chat", "name": "基础聊天", "desc": "检查聊天记录是否可读、是否有样本数据"},
    {"key": "memory_accuracy", "name": "记忆准确", "desc": "检查记忆账本是否可读及确认状态分布"},
    {"key": "growth_goal", "name": "成长目标", "desc": "检查成长目标与事件是否已接通"},
    {"key": "psychology", "name": "心理画像", "desc": "检查心理画像与历史是否可读"},
    {"key": "safety", "name": "危机响应", "desc": "检查安全状态数据链路"},
    {"key": "persona_stability", "name": "人设稳定", "desc": "检查漂移报告是否异常"},
    {"key": "proactive", "name": "主动消息", "desc": "检查主动消息事件是否可审计"},
    {"key": "webui_db", "name": "WebUI/DB", "desc": "检查关键 API 路由与数据库联通"},
]

def _eval_collect_rows(table, user_id="", persona="", limit=200):
    rows = []
    for db_path in _scan_user_data_dbs():
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if table not in tables:
                continue
            cols = {r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()}
            clauses = []
            params = []
            if user_id and "user_id" in cols:
                clauses.append("user_id = ?")
                params.append(user_id)
            if persona and "persona" in cols:
                clauses.append("persona = ?")
                params.append(persona)
            if table == "account_bindings":
                if user_id and "account_id" in cols:
                    clauses.append("account_id = ?")
                    params.append(user_id)
                if persona and "persona_name" in cols:
                    clauses.append("persona_name = ?")
                    params.append(persona)
            order_col = next((c for c in ["updated_at", "created_at", "timestamp", "last_analyzed", "switched_at", "id"] if c in cols), "ROWID")
            sql = f"SELECT * FROM [{table}]"
            if clauses:
                sql += " WHERE " + " AND ".join(clauses)
            sql += f" ORDER BY [{order_col}] DESC LIMIT ?"
            params.append(limit)
            for r in conn.execute(sql, params).fetchall():
                item = dict(r)
                item["db_path"] = _rel_db_path(db_path)
                rows.append(item)
                if len(rows) >= limit:
                    return rows
        except Exception:
            pass
        finally:
            try:
                if conn is not None:
                    conn.close()
            except Exception:
                pass
    return rows

def _eval_status_score(status):
    return 100 if status == "pass" else 60 if status == "warn" else 0

def _run_eval_suite(user_id="", persona="", scenario_keys=None):
    if not scenario_keys:
        scenario_keys = [x["key"] for x in EVAL_SCENARIOS]
    scenario_keys = [k for k in scenario_keys if any(s["key"] == k for s in EVAL_SCENARIOS)]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []

    def push(key, status, summary, metrics=None):
        results.append({
            "key": key,
            "status": status,
            "score": _eval_status_score(status),
            "summary": summary,
            "metrics": metrics or {},
        })

    if "base_chat" in scenario_keys:
        rows = _eval_collect_rows("chat_records", user_id=user_id, persona=persona, limit=300)
        push("base_chat", "pass" if len(rows) > 0 else "fail", f"聊天记录样本 {len(rows)} 条", {"records": len(rows)})

    if "memory_accuracy" in scenario_keys:
        rows = _eval_collect_rows("memory_ledger", user_id=user_id, persona=persona, limit=400)
        counts = {}
        for r in rows:
            k = str(r.get("consent_status") or "unknown")
            counts[k] = counts.get(k, 0) + 1
        confirmed = counts.get("confirmed", 0) + counts.get("auto", 0)
        status = "pass" if confirmed > 0 else ("warn" if len(rows) > 0 else "fail")
        push("memory_accuracy", status, f"账本 {len(rows)} 条，已确认/自动 {confirmed} 条", {"total": len(rows), "consent": counts})

    if "growth_goal" in scenario_keys:
        goals = _eval_collect_rows("growth_goals", user_id=user_id, persona=persona, limit=200)
        events = _eval_collect_rows("growth_goal_events", user_id=user_id, persona=persona, limit=300)
        status = "pass" if len(goals) > 0 else ("warn" if len(events) > 0 else "warn")
        push("growth_goal", status, f"目标 {len(goals)} 条，事件 {len(events)} 条", {"goals": len(goals), "events": len(events)})

    if "psychology" in scenario_keys:
        ps = _eval_collect_rows("user_psychology", user_id=user_id, persona=persona, limit=50)
        hs = _eval_collect_rows("psychology_history", user_id=user_id, persona=persona, limit=120)
        status = "pass" if len(ps) > 0 else ("warn" if len(hs) > 0 else "warn")
        push("psychology", status, f"画像 {len(ps)} 条，历史 {len(hs)} 条", {"profile": len(ps), "history": len(hs)})

    if "safety" in scenario_keys:
        sf = _eval_collect_rows("safety_state", user_id=user_id, persona=persona, limit=80)
        status = "pass" if len(sf) > 0 else "warn"
        latest = sf[0] if sf else {}
        push("safety", status, f"安全状态 {len(sf)} 条", {"states": len(sf), "latest_risk": latest.get("risk_level", "")})

    if "persona_stability" in scenario_keys:
        dr = _eval_collect_rows("drift_reports", user_id=user_id, persona=persona, limit=120)
        drifting = 0
        for r in dr:
            try:
                drifting += 1 if int(r.get("is_drifting") or 0) else 0
            except Exception:
                pass
        status = "fail" if drifting > 0 else ("pass" if len(dr) > 0 else "warn")
        push("persona_stability", status, f"漂移报告 {len(dr)} 条，异常 {drifting} 条", {"reports": len(dr), "drifting": drifting})

    if "proactive" in scenario_keys:
        pe = _eval_collect_rows("proactive_events", user_id=user_id, persona=persona, limit=240)
        counts = {}
        for r in pe:
            k = str(r.get("status") or "unknown")
            counts[k] = counts.get(k, 0) + 1
        status = "pass" if len(pe) > 0 else "warn"
        push("proactive", status, f"主动事件 {len(pe)} 条", {"events": len(pe), "status": counts})

    if "webui_db" in scenario_keys:
        routes = _system_audit_route_set()
        need_apis = [
            "GET /api/system-audit",
            "GET /api/companion-hub/summary",
            "GET /api/chat-record/stats",
            "GET /api/relationship/brief",
            "POST /api/chat-record/coldstart_summary",
        ]
        missing = [x for x in need_apis if x not in routes]
        status = "pass" if not missing else "fail"
        push("webui_db", status, "关键 API 路由检查", {"missing_apis": missing, "routes_count": len(routes)})

    pass_count = len([r for r in results if r["status"] == "pass"])
    warn_count = len([r for r in results if r["status"] == "warn"])
    fail_count = len([r for r in results if r["status"] == "fail"])
    score = round(sum(r["score"] for r in results) / max(1, len(results)), 1)
    report = {
        "ok": True,
        "generated_at": now,
        "filters": {"user_id": user_id, "persona": persona},
        "summary": {
            "score": score,
            "pass": pass_count,
            "warn": warn_count,
            "fail": fail_count,
            "total": len(results),
        },
        "results": results,
    }
    return report

def _save_eval_report(report):
    EVAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_id = "eval_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    report["report_id"] = report_id
    report["report_file"] = str((EVAL_REPORTS_DIR / (report_id + ".json")).relative_to(BASE_DIR))
    with open(EVAL_REPORTS_DIR / f"{report_id}.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report

@app.route("/api/eval/scenarios", methods=["GET"])
def eval_scenarios():
    return jsonify({"ok": True, "data": EVAL_SCENARIOS})

@app.route("/api/eval/run", methods=["POST"])
def eval_run():
    data = request.get_json(silent=True) or {}
    user_id = str(data.get("user_id", "")).strip()
    persona = str(data.get("persona", "")).strip()
    scenario_keys = data.get("scenarios", [])
    if scenario_keys and not isinstance(scenario_keys, list):
        scenario_keys = []
    report = _run_eval_suite(user_id=user_id, persona=persona, scenario_keys=scenario_keys)
    saved = _save_eval_report(report)
    return jsonify(saved)

@app.route("/api/eval/reports", methods=["GET"])
def eval_reports():
    EVAL_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for fp in sorted(EVAL_REPORTS_DIR.glob("eval_*.json"), reverse=True):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                raw = json.load(f)
            rows.append({
                "report_id": raw.get("report_id", fp.stem),
                "generated_at": raw.get("generated_at", ""),
                "score": raw.get("summary", {}).get("score", 0),
                "pass": raw.get("summary", {}).get("pass", 0),
                "warn": raw.get("summary", {}).get("warn", 0),
                "fail": raw.get("summary", {}).get("fail", 0),
                "filters": raw.get("filters", {}),
            })
        except Exception:
            continue
    return jsonify({"ok": True, "data": rows[:100]})

@app.route("/api/eval/report/<report_id>", methods=["GET"])
def eval_report_detail(report_id):
    safe_id = str(report_id or "").strip()
    if not safe_id or ".." in safe_id or "/" in safe_id or "\\" in safe_id:
        return jsonify({"ok": False, "msg": "非法 report_id"}), 400
    fp = EVAL_REPORTS_DIR / f"{safe_id}.json"
    if not fp.exists():
        return jsonify({"ok": False, "msg": "报告不存在"}), 404
    try:
        with open(fp, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return jsonify({"ok": True, "data": raw})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

def _companion_scan_user_dbs():
    seen = set()
    candidates = [get_active_db_path()]
    candidates.extend(DATA_DIR.glob("accounts/*/*/user_data.db"))
    candidates.extend(DATA_DIR.glob("chatbot*.db"))
    for db_file in candidates:
        db_path = Path(db_file)
        if not db_path.exists() or db_path in seen:
            continue
        seen.add(db_path)
        yield db_path

def _companion_rel_path(db_path):
    try:
        return str(Path(db_path).relative_to(BASE_DIR))
    except Exception:
        return str(db_path)

def _companion_table_names(conn):
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

def _companion_columns(conn, table):
    return {r[1] for r in conn.execute(f"PRAGMA table_info([{table}])").fetchall()}

def _companion_json(value, default=None):
    if default is None:
        default = {}
    if isinstance(value, (dict, list)):
        return value
    if not value:
        return default
    try:
        return _json.loads(value)
    except Exception:
        return default

def _companion_apply_filters(table, columns, user_id="", persona=""):
    clauses = []
    params = []
    if user_id and "user_id" in columns:
        clauses.append("user_id = ?")
        params.append(user_id)
    if persona and "persona" in columns:
        clauses.append("persona = ?")
        params.append(persona)
    if persona and table == "account_bindings" and "persona_name" in columns:
        clauses.append("persona_name = ?")
        params.append(persona)
    if user_id and table == "account_bindings" and "account_id" in columns:
        clauses.append("account_id = ?")
        params.append(user_id)
    return clauses, params

def _companion_fetch_recent(conn, table, columns, user_id="", persona="", limit=5):
    order_candidates = ["updated_at", "created_at", "last_analyzed", "switched_at", "sent_at", "id"]
    order_col = next((c for c in order_candidates if c in columns), "ROWID")
    clauses, params = _companion_apply_filters(table, columns, user_id, persona)
    sql = f"SELECT * FROM [{table}]"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" ORDER BY [{order_col}] DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params).fetchall()]

def _companion_count_by(conn, table, field, columns, user_id="", persona=""):
    if field not in columns:
        return {}
    clauses, params = _companion_apply_filters(table, columns, user_id, persona)
    sql = f"SELECT [{field}] AS k, COUNT(*) AS c FROM [{table}]"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += f" GROUP BY [{field}]"
    return {str(r["k"] or "unknown"): int(r["c"]) for r in conn.execute(sql, params).fetchall()}

@app.route("/api/companion-hub/summary", methods=["GET"])
def companion_hub_summary():
    """Read-only companion hub summary for WebUI."""
    user_id = request.args.get("user_id", "").strip()
    persona = request.args.get("persona", "").strip()
    limit = min(max(int(request.args.get("limit", 5) or 5), 1), 20)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    config = (load_yaml(CONFIG_PATH) if CONFIG_PATH.exists() else {}) or {}
    if not persona:
        persona = config.get("default_persona", "")

    summary = {
        "ok": True,
        "generated_at": now,
        "filters": {"user_id": user_id, "persona": persona, "limit": limit},
        "ai": {
            "persona": config.get("default_persona", ""),
            "llm_model": config.get("llm", {}).get("model", ""),
            "light_model": config.get("llm", {}).get("light_model", ""),
            "vlm_model": config.get("vlm", {}).get("model", ""),
            "tts_enabled": bool(config.get("tts", {}).get("enabled", False)),
            "tts_model": config.get("tts", {}).get("model", ""),
            "search_enabled": bool(config.get("search", {}).get("enabled", False)),
        },
        "safety": {"counts": {}, "latest": None, "recent": []},
        "memory": {"counts": {}, "recent": []},
        "growth": {"counts": {}, "due": [], "high_pressure": [], "recent": []},
        "proactive": {"counts": {}, "recent": []},
        "psychology": {"latest": None, "history": []},
        "relationship": {"active": None, "bindings": []},
        "dbs": [],
    }

    for db_path in _companion_scan_user_dbs():
        try:
            conn = _sqlite3.connect(str(db_path))
            conn.row_factory = _sqlite3.Row
            tables = _companion_table_names(conn)
            summary["dbs"].append(_companion_rel_path(db_path))

            if "safety_state" in tables:
                cols = _companion_columns(conn, "safety_state")
                for k, v in _companion_count_by(conn, "safety_state", "risk_level", cols, user_id, persona).items():
                    summary["safety"]["counts"][k] = summary["safety"]["counts"].get(k, 0) + v
                for item in _companion_fetch_recent(conn, "safety_state", cols, user_id, persona, limit):
                    item["assessment"] = _companion_json(item.get("assessment_json"), {})
                    item["db_path"] = _companion_rel_path(db_path)
                    summary["safety"]["recent"].append(item)

            if "memory_ledger" in tables:
                cols = _companion_columns(conn, "memory_ledger")
                for k, v in _companion_count_by(conn, "memory_ledger", "consent_status", cols, user_id, persona).items():
                    summary["memory"]["counts"][k] = summary["memory"]["counts"].get(k, 0) + v
                for item in _companion_fetch_recent(conn, "memory_ledger", cols, user_id, persona, limit):
                    item["db_path"] = _companion_rel_path(db_path)
                    summary["memory"]["recent"].append(item)

            if "growth_goals" in tables:
                cols = _companion_columns(conn, "growth_goals")
                for k, v in _companion_count_by(conn, "growth_goals", "status", cols, user_id, persona).items():
                    summary["growth"]["counts"][k] = summary["growth"]["counts"].get(k, 0) + v
                for item in _companion_fetch_recent(conn, "growth_goals", cols, user_id, persona, limit):
                    item["micro_tasks"] = _companion_json(item.get("micro_tasks"), [])
                    item["db_path"] = _companion_rel_path(db_path)
                    summary["growth"]["recent"].append(item)
                    if item.get("status") == "active" and item.get("next_follow_up") and item.get("next_follow_up") <= now:
                        summary["growth"]["due"].append(item)
                    if int(item.get("pressure_level") or 0) >= 4:
                        summary["growth"]["high_pressure"].append(item)

            if "proactive_events" in tables:
                cols = _companion_columns(conn, "proactive_events")
                for k, v in _companion_count_by(conn, "proactive_events", "status", cols, user_id, persona).items():
                    summary["proactive"]["counts"][k] = summary["proactive"]["counts"].get(k, 0) + v
                for item in _companion_fetch_recent(conn, "proactive_events", cols, user_id, persona, limit):
                    item["meta"] = _companion_json(item.get("meta_json"), {})
                    item["db_path"] = _companion_rel_path(db_path)
                    summary["proactive"]["recent"].append(item)

            if "user_psychology" in tables:
                cols = _companion_columns(conn, "user_psychology")
                rows = _companion_fetch_recent(conn, "user_psychology", cols, user_id, persona, 1)
                if rows and not summary["psychology"]["latest"]:
                    rows[0]["db_path"] = _companion_rel_path(db_path)
                    summary["psychology"]["latest"] = rows[0]

            if "psychology_history" in tables:
                cols = _companion_columns(conn, "psychology_history")
                for item in _companion_fetch_recent(conn, "psychology_history", cols, user_id, persona, limit):
                    item["db_path"] = _companion_rel_path(db_path)
                    summary["psychology"]["history"].append(item)

            if "relationship_state" in tables:
                cols = _companion_columns(conn, "relationship_state")
                rows = _companion_fetch_recent(conn, "relationship_state", cols, user_id, persona, 1)
                if rows and not summary["relationship"]["active"]:
                    rows[0]["db_path"] = _companion_rel_path(db_path)
                    summary["relationship"]["active"] = rows[0]

            if "account_bindings" in tables:
                cols = _companion_columns(conn, "account_bindings")
                for item in _companion_fetch_recent(conn, "account_bindings", cols, user_id, persona, limit):
                    item["db_path"] = _companion_rel_path(db_path)
                    summary["relationship"]["bindings"].append(item)

            conn.close()
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            summary.setdefault("warnings", []).append({"db_path": _companion_rel_path(db_path), "error": str(e)})

    summary["safety"]["recent"] = sorted(summary["safety"]["recent"], key=lambda x: x.get("updated_at", ""), reverse=True)[:limit]
    summary["memory"]["recent"] = sorted(summary["memory"]["recent"], key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
    summary["growth"]["recent"] = sorted(summary["growth"]["recent"], key=lambda x: x.get("updated_at", ""), reverse=True)[:limit]
    summary["growth"]["due"] = sorted(summary["growth"]["due"], key=lambda x: x.get("next_follow_up", ""))[:limit]
    summary["growth"]["high_pressure"] = summary["growth"]["high_pressure"][:limit]
    summary["proactive"]["recent"] = sorted(summary["proactive"]["recent"], key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
    summary["psychology"]["history"] = sorted(summary["psychology"]["history"], key=lambda x: x.get("created_at", ""), reverse=True)[:limit]
    if summary["safety"]["recent"]:
        summary["safety"]["latest"] = summary["safety"]["recent"][0]
    return jsonify(summary)

@app.before_request
def _silence_noise():
    """浏览器扩展注入的垃圾请求直接返回204，不进日志"""
    noise = ("hybridaction", "zybTracker")
    if any(n in request.path for n in noise):
        from flask import make_response as _mr
        return _mr("", 204)

@app.route("/")
def index():
    resp = render_template_string(HTML_TEMPLATE)
    resp = app.make_response(resp)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>C.R.O.W.N. // 黑冠 配置终端</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Noto+Sans+SC:wght@300;400;500;700&display=swap');

/* ===== 色值系统 — 极致黑白 ===== */
:root {
  --bg: #111111;
  --bg-deep: #080808;
  --bg-panel: #141414;
  --bg-panel-hover: #1c1c1c;
  --amber: #ffffff;
  --amber-dim: rgba(255,255,255,0.7);
  --amber-glow: rgba(255,255,255,0.2);
  --amber-bg: rgba(255,255,255,0.04);
  --red: #ffffff;
  --red-glow: rgba(255,255,255,0.25);
  --red-bg: rgba(255,255,255,0.04);
  --cyan: #ffffff;
  --cyan-dim: rgba(255,255,255,0.6);
  --cyan-glow: rgba(255,255,255,0.2);
  --cyan-bg: rgba(255,255,255,0.04);
  --info-blue: #cccccc;
  --info-glow: rgba(200,200,200,0.2);
  --text: #e0e0e0;
  --text-dim: #666666;
  --border: #333333;
  --border-hover: #444444;
  --sidebar-w: 240px;
  --sidebar-collapsed: 60px;
}

*{margin:0;padding:0;box-sizing:border-box;}

body{
  background:var(--bg-deep);
  color:var(--text);
  font-family:'Noto Sans SC','Segoe UI',sans-serif;
  font-size:14px;
  font-weight:500;
  min-height:100vh;
  overflow-x:hidden;
  display:flex;
}

/* ===== 噪点纹理（repeating-conic-gradient 10%） ===== */
body::before{
  content:'';position:fixed;inset:0;
  background-image:repeating-conic-gradient(rgba(255,255,255,0.02) 0% 25%,transparent 0% 50%);
  background-size:4px 4px;
  pointer-events:none;z-index:0;
  opacity:0.5;
}

/* ===== 扫描线 — 从上到下 10s 循环 ===== */
#scanLine{
  position:fixed;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent 5%,rgba(255,207,13,0.06) 20%,rgba(255,207,13,0.12) 50%,rgba(255,207,13,0.06) 80%,transparent 95%);
  pointer-events:none;z-index:9999;
  animation:scanMove 10s linear infinite;
}
@keyframes scanMove{from{top:-4px;}to{top:100vh;}}


/* ===== 人设页持续故障风（保留彩色） ===== */
#page-persona::before{
  content:'';position:absolute;inset:0;
  background:repeating-linear-gradient(
    0deg,
    transparent 0px,
    transparent 2px,
    rgba(255,0,100,0.03) 2px,
    rgba(255,0,100,0.03) 4px
  );
  pointer-events:none;z-index:10;
  animation:personaGlitch 1s infinite;
}
#page-persona::after{
  content:'';position:absolute;inset:0;
  background:repeating-linear-gradient(
    90deg,
    transparent 0px,
    transparent 3px,
    rgba(0,255,200,0.02) 3px,
    rgba(0,255,200,0.02) 6px
  );
  pointer-events:none;z-index:10;
  animation:personaGlitch2 1.5s infinite;
}
@keyframes personaGlitch{
  0%,70%,100%{opacity:0.5;transform:translate(0);}
  72%{opacity:1;transform:translate(2px,0);}
  76%{opacity:0.3;transform:translate(-1px,1px);}
  80%{opacity:0.8;transform:translate(0,-1px);}
}
@keyframes personaGlitch2{
  0%,60%,100%{opacity:0.3;}
  65%{opacity:1;clip-path:inset(20% 0 60% 0);}
  70%{opacity:0.5;clip-path:inset(50% 0 20% 0);}
  75%{opacity:0.8;clip-path:inset(10% 0 70% 0);}
}
.persona-card{
  animation:personaCardGlitch 2s infinite;
}
@keyframes personaCardGlitch{
  0%,70%,100%{filter:none;transform:translate(0);}
  72%{filter:hue-rotate(90deg);transform:translate(1px,0);}
  76%{filter:hue-rotate(-90deg);transform:translate(-1px,1px);}
  80%{filter:none;transform:translate(0);}
}

/* ===== 粒子画布 ===== */
#particles{position:fixed;inset:0;pointer-events:none;z-index:0;}

/* ===== 侧边栏 ===== */
.sidebar{
  position:fixed;left:0;top:0;bottom:0;
  width:var(--sidebar-w);
  background:var(--bg-panel);
  border-right:1px solid var(--border);
  display:flex;flex-direction:column;
  z-index:100;
  transition:width .35s cubic-bezier(.4,0,.2,1);
  overflow:hidden;
}
.sidebar.collapsed{width:var(--sidebar-collapsed);}

/* 侧边栏右侧发光线 */
.sidebar::after{
  content:'';position:absolute;right:-1px;top:0;bottom:0;width:1px;
  background:linear-gradient(180deg,transparent,var(--amber),transparent);
  opacity:.3;
}

.sidebar-header{
  padding:20px 16px;
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;gap:12px;
  min-height:72px;
}

.logo-hex{
  width:36px;height:36px;flex-shrink:0;
  position:relative;
  display:flex;align-items:center;justify-content:center;
  animation:diamondRotate 8s linear infinite;
}
@keyframes diamondRotate{
  0%{transform:rotate(0deg);}
  100%{transform:rotate(360deg);}
}
.logo-hex svg{width:36px;height:36px;}
.logo-hex-text{
  font-family:'JetBrains Mono',monospace;
  font-size:13px;fill:var(--amber);
  filter:drop-shadow(0 0 6px var(--amber-glow));
}

.logo-info{overflow:hidden;white-space:nowrap;}
.logo-title{
  font-family:'JetBrains Mono',monospace;
  font-size:15px;color:var(--amber);
  text-shadow:0 0 10px var(--amber-glow);
  letter-spacing:2px;
  position:relative;
}
.logo-sub{font-size:10px;color:var(--text-dim);letter-spacing:1px;margin-top:2px;}

.sidebar-toggle{
  position:absolute;right:8px;top:24px;
  width:24px;height:24px;
  background:var(--bg-panel-hover);border:1px solid var(--border);
  color:var(--text-dim);cursor:pointer;
  display:flex;align-items:center;justify-content:center;
  font-size:12px;border-radius:3px;
  transition:all .2s;
}
.sidebar-toggle:hover{border-color:var(--amber);color:var(--amber);}

.sidebar-nav{flex:1;padding:12px 0;overflow-y:auto;overflow-x:hidden;}

.nav-item{
  display:flex;align-items:center;gap:12px;
  padding:12px 20px;
  cursor:pointer;
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--text-dim);
  letter-spacing:0.5px;
  text-transform:uppercase;
  border-left:3px solid transparent;
  transition:all .25s;
  white-space:nowrap;
  position:relative;
}
/* 等宽字体大写 + "| " 前缀 */
.nav-item .label::before{content:'| ';color:var(--border-hover);font-weight:400;}
.nav-item:hover{color:var(--text);background:var(--amber-bg);}
.nav-item.active{
  color:var(--amber);
  border-left-color:var(--amber);
  background:linear-gradient(90deg,rgba(255,207,13,0.08),transparent);
  text-shadow:0 0 8px var(--amber-glow);
}
.nav-item .icon{width:20px;text-align:center;font-size:15px;flex-shrink:0;}
.nav-item .label{transition:opacity .25s;opacity:1;}
.sidebar.collapsed .nav-item .label{opacity:0;}
.sidebar.collapsed .nav-item{padding:12px 0;justify-content:center;}
.sidebar.collapsed .nav-item.active{border-left-color:transparent;border-bottom:2px solid var(--amber);}

.sidebar-footer{
  padding:12px 16px;
  border-top:1px solid var(--border);
  font-family:'JetBrains Mono',monospace;
  font-size:10px;color:var(--text-dim);
  display:flex;align-items:center;gap:8px;
  min-height:48px;
  letter-spacing:0.5px;
}
.sidebar-footer .status-dot{
  width:7px;height:7px;border-radius:50%;
  background:var(--cyan);
  box-shadow:0 0 6px var(--cyan);
  animation:breathe 2.5s infinite;
  flex-shrink:0;
}
@keyframes breathe{0%,100%{opacity:1;}50%{opacity:.35;}}
.sidebar-footer .footer-text{overflow:hidden;white-space:nowrap;}
.sidebar.collapsed .sidebar-footer .footer-text{display:none;}

/* ===== 主区域 ===== */
.main-wrap{
  margin-left:var(--sidebar-w);
  flex:1;min-height:100vh;
  transition:margin-left .35s cubic-bezier(.4,0,.2,1);
  position:relative;z-index:1;
  display:flex;flex-direction:column;
}
body.sidebar-collapsed .main-wrap{margin-left:var(--sidebar-collapsed);}

/* ===== 顶栏 ===== */
.topbar{
  height:48px;
  background:rgba(10,10,10,0.9);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
  padding:0 28px;
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--text-dim);
  position:sticky;top:0;z-index:50;
  backdrop-filter:blur(12px);
  -webkit-backdrop-filter:blur(12px);
  letter-spacing:0.5px;
}
.topbar-left{display:flex;align-items:center;gap:16px;}
.topbar-left .topbar-title{
  color:var(--amber);
  text-transform:uppercase;
  letter-spacing:2px;
  font-weight:500;
  text-shadow:0 0 8px var(--amber-glow);
}
.topbar-left .topbar-sep{color:var(--border-hover);margin:0 4px;}
.topbar-left .breadcrumb{color:var(--text-dim);letter-spacing:1px;}
.topbar-right{display:flex;align-items:center;gap:16px;}
.topbar-right .sys-info{letter-spacing:1px;}

/* ===== 中央内容 ===== */
.main-content{
  flex:1;padding:28px;
  max-width:1200px;width:100%;
  margin:0 auto;
}

/* ===== 页面切换动画 — RGB 色散闪烁 ===== */
.page{display:none;animation:pageIn .4s cubic-bezier(.4,0,.2,1);}
.page.active{display:block;}
@keyframes pageIn{
  0%{opacity:0;transform:translate3d(0,24px,0);}
  60%{opacity:1;}
  100%{transform:translate3d(0,0,0);}
}
/* 切换时短暂 RGB 色散 */
.page.active{animation:pageIn .4s ease, glitchFlash .15s ease .05s;}
@keyframes glitchFlash{
  0%{text-shadow:-2px 0 #FF3E3E,2px 0 #00B2B2;filter:hue-rotate(10deg);}
  50%{text-shadow:2px 0 #FF3E3E,-2px 0 #00B2B2;filter:hue-rotate(-10deg);}
  100%{text-shadow:none;filter:none;}
}

/* ===== 加载动画 — 圆角方块旋转+位移+缩放 ===== */
.loader-wrap{
  position:fixed;inset:0;display:flex;align-items:center;justify-content:center;
  background:var(--bg-deep);z-index:99999;
  transition:opacity .5s;
}
.loader-wrap.hide{opacity:0;pointer-events:none;}
.loader-diamond{
  width:20px;height:20px;
  border:3px solid var(--amber);
  position:absolute;
  animation:loaderDiamondSpin 2s cubic-bezier(.4,0,.2,1) infinite;
}
.loader-diamond:nth-child(1){animation-delay:0s;transform:translate(-24px,0);}
.loader-diamond:nth-child(2){animation-delay:0.2s;transform:translate(0,-24px);}
.loader-diamond:nth-child(3){animation-delay:0.4s;transform:translate(24px,0);}
.loader-diamond:nth-child(4){animation-delay:0.6s;transform:translate(0,24px);}
@keyframes loaderDiamondSpin{
  0%{transform:rotate(45deg) scale(1);opacity:1;}
  25%{transform:rotate(135deg) scale(0.6);opacity:0.4;}
  50%{transform:rotate(225deg) scale(1);opacity:1;}
  75%{transform:rotate(315deg) scale(0.6);opacity:0.4;}
  100%{transform:rotate(405deg) scale(1);opacity:1;}
}
}

/* ===== 面板（毛玻璃 + 微圆角） ===== */
.glass-panel{
  background:var(--bg-panel);
  border:1px solid var(--border);
  border-radius:2px;
  margin-bottom:20px;
  overflow:hidden;
  transition:border-color .3s,box-shadow .3s,transform .3s;
  position:relative;
}
.glass-panel:hover{
  border-color:var(--border-hover);
  box-shadow:0 0 20px rgba(255,207,13,0.04);
}

/* 斜切角装饰 */
.glass-panel::before{
  content:'';position:absolute;top:0;right:0;
  width:0;height:0;
  border-style:solid;
  border-width:0 16px 16px 0;
  border-color:transparent var(--bg-deep) transparent transparent;
  z-index:2;
}

.panel-header{
  padding:14px 20px;
  background:linear-gradient(90deg,rgba(255,207,13,0.04),transparent);
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
  cursor:pointer;user-select:none;
  transition:background .3s;
}
.panel-header:hover{
  background:linear-gradient(90deg,rgba(255,207,13,0.08),transparent);
}
.panel-title{
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--amber);
  letter-spacing:1.5px;
  text-transform:uppercase;
  display:flex;align-items:center;gap:8px;
}
/* "- " 点横装饰前缀 */
.panel-title::before{content:'- ';color:var(--text-dim);font-weight:400;}
.panel-toggle{
  color:var(--text-dim);font-size:12px;
  transition:transform .3s;font-family:'JetBrains Mono',monospace;
}
.panel-toggle.open{transform:rotate(90deg);}

.panel-body{padding:20px;}
.panel-body.collapsed{display:none;height:0;padding:0 20px;overflow:hidden;}

/* ===== 表单 ===== */
.form-grid{
  display:grid;
  grid-template-columns:180px 1fr;
  gap:8px 16px;
  align-items:start;
}
.form-row{
  display:grid;
  grid-template-columns:180px 1fr;
  gap:8px 16px;
  align-items:center;
  margin-bottom:12px;
}
.form-row label{
  font-family:'JetBrains Mono',monospace;
  font-size:11px;color:var(--cyan);
  letter-spacing:.5px;
  text-transform:uppercase;
  display:flex;align-items:center;gap:6px;
}
.form-label{
  font-family:'JetBrains Mono',monospace;
  font-size:11px;color:var(--cyan);
  padding:10px 0;letter-spacing:.5px;
  text-transform:uppercase;
  display:flex;align-items:center;gap:6px;
}
.form-input{
  background:rgba(0,0,0,0.4);
  border:1px solid var(--border);
  border-radius:2px;
  padding:9px 12px;
  color:var(--text);
  font-family:'JetBrains Mono',monospace;
  font-size:13px;
  width:100%;
  transition:border-color .2s,box-shadow .2s;
}
.form-input:focus{
  outline:none;
  border-color:var(--amber);
  box-shadow:0 0 8px var(--amber-glow);
}
textarea.form-input{min-height:72px;resize:vertical;line-height:1.6;}

/* Tooltip 信息图标 — 信息蓝 */
.info-icon{
  display:inline-flex;align-items:center;justify-content:center;
  width:16px;height:16px;
  border-radius:50%;
  border:1px solid var(--text-dim);
  font-size:10px;color:var(--text-dim);
  cursor:help;position:relative;
  font-family:'JetBrains Mono',monospace;
  flex-shrink:0;
  transition:border-color .2s;
}
.info-icon:hover{border-color:var(--info-blue);color:var(--info-blue);}
.info-icon .tip{
  display:none;
  position:absolute;left:24px;top:50%;transform:translateY(-50%);
  background:var(--bg-panel-hover);
  border:1px solid var(--info-blue);
  color:var(--text);
  font-size:12px;
  padding:8px 12px;
  border-radius:4px;
  white-space:nowrap;
  z-index:200;
  box-shadow:0 4px 20px rgba(0,0,0,.5),0 0 12px var(--info-glow);
  font-family:'Noto Sans SC',sans-serif;
  max-width:320px;white-space:normal;
  pointer-events:none;
}
.info-icon:hover .tip{display:block;}

/* ===== 按钮 — 琥珀黄强调 ===== */
.btn{
  padding:10px 24px;
  border:1px solid var(--amber);
  background:rgba(255,207,13,0.06);
  color:var(--amber);
  font-family:'JetBrains Mono',monospace;
  font-size:12px;
  cursor:pointer;
  transition:all .2s;
  letter-spacing:1px;
  text-transform:uppercase;
  position:relative;overflow:hidden;
  border-radius:2px;
}
.btn:hover{
  background:rgba(255,207,13,0.15);
  box-shadow:0 0 16px var(--amber-glow),inset 0 0 16px rgba(255,207,13,0.04);
  transform:translateY(-1px);
}
.btn:active{transform:translateY(0) scale(.97);}

/* 涟漪效果 — 琥珀色 */
.btn .ripple{
  position:absolute;border-radius:50%;
  background:rgba(255,207,13,0.3);
  transform:scale(0);animation:rippleAnim .5s ease-out;
  pointer-events:none;
}
@keyframes rippleAnim{to{transform:scale(4);opacity:0;}}

/* 按钮点击粒子爆发容器 */
.btn-burst{position:absolute;inset:0;pointer-events:none;overflow:hidden;}

.btn-red{
  border-color:var(--red);color:var(--red);
  background:rgba(255,62,62,0.06);
}
.btn-red:hover{
  background:rgba(255,62,62,0.15);
  box-shadow:0 0 16px var(--red-glow),inset 0 0 16px rgba(255,62,62,0.04);
}

.btn-group{display:flex;gap:12px;justify-content:center;padding:20px 0;flex-wrap:wrap;}

/* ===== 统计卡片 ===== */
.stat-grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(160px,1fr));
  gap:14px;margin-bottom:24px;
}
.stat-card{
  background:var(--bg-panel);
  border:1px solid var(--border);
  border-radius:2px;
  padding:20px 16px;
  text-align:center;
  transition:border-color .3s,box-shadow .3s,transform .3s;
  position:relative;overflow:hidden;
  cursor:default;
}
.stat-card:hover{
  border-color:var(--amber-dim);
  box-shadow:0 0 20px var(--amber-glow);
  transform:translateY(-2px);
}
/* 悬停故障抖动 0.1s */
.stat-card:hover{animation:cardGlitch .1s ease;}
@keyframes cardGlitch{
  0%{transform:translateY(-2px) translate(0,0);}
  25%{transform:translateY(-2px) translate(1px,-1px);}
  50%{transform:translateY(-2px) translate(-1px,1px);}
  75%{transform:translateY(-2px) translate(1px,0);}
  100%{transform:translateY(-2px) translate(0,0);}
}
.stat-card::after{
  content:'';position:absolute;bottom:0;left:0;right:0;height:2px;
  background:linear-gradient(90deg,transparent,var(--amber),transparent);
  opacity:.5;
}
.stat-icon{font-size:22px;margin-bottom:8px;}
.stat-value{
  font-family:'JetBrains Mono',monospace;
  font-size:26px;color:var(--amber);
  text-shadow:0 0 10px var(--amber-glow);
}
.stat-label{font-size:10px;color:var(--text-dim);margin-top:4px;letter-spacing:1px;text-transform:uppercase;}

/* ===== 场景/语气/插件 卡片 ===== */
.card-grid{
  display:grid;
  grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  gap:14px;
}
.card{
  background:rgba(0,0,0,0.3);
  border:1px solid var(--border);
  border-radius:2px;
  padding:16px;
  transition:border-color .3s,box-shadow .3s,transform .3s;
  position:relative;
}
.card:hover{
  border-color:var(--amber-dim);
  box-shadow:0 0 16px var(--amber-glow);
  transform:translateY(-2px);
  animation:cardGlitch .1s ease;
}
.card-title{
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--amber);
  margin-bottom:12px;
  letter-spacing:1px;
  text-transform:uppercase;
  display:flex;align-items:center;gap:6px;
}
.card-title::before{content:'▸';color:var(--amber);font-size:10px;}
.card-field{margin-bottom:8px;}
.card-field-label{
  font-size:10px;color:var(--text-dim);
  margin-bottom:3px;letter-spacing:.5px;
  text-transform:uppercase;
  font-family:'JetBrains Mono',monospace;
  display:flex;align-items:center;gap:4px;
}
.card-field input,.card-field textarea{
  width:100%;
  background:rgba(0,0,0,0.3);
  border:1px solid var(--border);
  border-radius:2px;
  padding:7px 10px;
  color:var(--text);
  font-size:12px;
  font-family:'JetBrains Mono',monospace;
  transition:border-color .2s,box-shadow .2s;
}
.card-field input:focus,.card-field textarea:focus{
  outline:none;border-color:var(--amber);
  box-shadow:0 0 6px var(--amber-glow);
}
.card-field textarea{min-height:50px;resize:vertical;}

/* ===== 插件卡片 ===== */
.plugin-card{
  display:flex;align-items:center;gap:16px;
  padding:14px 18px;
  background:rgba(0,0,0,0.25);
  border:1px solid var(--border);
  border-radius:2px;
  transition:border-color .3s,box-shadow .3s,transform .3s;
}
.plugin-card:hover{
  border-color:var(--amber-dim);
  box-shadow:0 0 16px var(--amber-glow);
  transform:translateY(-1px);
}
.plugin-info{flex:1;}
.plugin-name{
  font-family:'JetBrains Mono',monospace;
  font-size:13px;color:var(--cyan);
  letter-spacing:1px;
}
.plugin-desc{font-size:12px;color:var(--text-dim);margin-top:4px;}
.plugin-path{font-size:11px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;margin-top:2px;}

/* 开关 — 琥珀黄 */
.toggle{
  width:44px;height:24px;
  background:var(--border);
  border-radius:12px;
  cursor:pointer;
  position:relative;
  transition:background .3s;
  flex-shrink:0;
}
.toggle.on{background:var(--amber-dim);}
.toggle::after{
  content:'';position:absolute;
  top:3px;left:3px;
  width:18px;height:18px;
  background:var(--text);
  border-radius:50%;
  transition:transform .3s;
}
.toggle.on::after{transform:translateX(20px);}

/* ===== 备份列表 ===== */
.backup-table{
  width:100%;border-collapse:collapse;
  font-family:'JetBrains Mono',monospace;
  font-size:12px;
}
.backup-table th{
  text-align:left;padding:10px 12px;
  color:var(--amber-dim);
  border-bottom:1px solid var(--border);
  letter-spacing:1px;font-weight:normal;
  text-transform:uppercase;
  font-size:11px;
}
.backup-table td{
  padding:8px 12px;
  border-bottom:1px solid rgba(51,51,51,0.5);
  color:var(--text-dim);
}
.backup-table tr:hover td{color:var(--text);background:rgba(255,207,13,0.02);}

/* ===== 日志 ===== */
.log-box{
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--text-dim);
  max-height:320px;overflow-y:auto;
  padding:16px;
  background:rgba(0,0,0,0.35);
  border-radius:2px;
  line-height:1.8;
}
.log-line{display:flex;gap:8px;}
.log-time{color:var(--amber-dim);min-width:80px;}
.log-msg{color:var(--text-dim);}
.log-msg.ok{color:var(--cyan);}
.log-msg.warn{color:var(--amber);}
.log-msg.err{color:var(--red);}

/* ===== 模态框 ===== */
.modal-overlay{
  display:none;
  position:fixed;inset:0;
  background:rgba(0,0,0,0.75);
  z-index:5000;
  align-items:center;justify-content:center;
  backdrop-filter:blur(6px);
  -webkit-backdrop-filter:blur(6px);
}
.modal-overlay.show{display:flex;}
.modal{
  background:var(--bg-panel-hover);
  border:1px solid var(--border);
  border-radius:2px;
  padding:28px;
  min-width:360px;max-width:480px;
  animation:modalIn .3s ease;
  position:relative;
}
@keyframes modalIn{from{opacity:0;transform:scale(.95);}to{opacity:1;transform:scale(1);}}
.modal-title{
  font-family:'JetBrains Mono',monospace;
  font-size:14px;color:var(--red);
  margin-bottom:16px;letter-spacing:1px;
  text-transform:uppercase;
}
.modal-body{font-size:14px;color:var(--text);line-height:1.7;margin-bottom:24px;}
.modal-actions{display:flex;gap:12px;justify-content:flex-end;}

/* ===== Toast — 从右侧滑入 + 扫描线 ===== */
.toast{
  position:fixed;top:60px;right:-360px;
  padding:12px 20px;
  background:var(--bg-panel);
  border:1px solid var(--amber);
  color:var(--amber);
  font-family:'JetBrains Mono',monospace;
  font-size:12px;
  z-index:9000;
  transition:right .4s cubic-bezier(.4,0,.2,1);
  border-radius:2px;
  box-shadow:0 4px 20px rgba(0,0,0,.5),0 0 8px var(--amber-glow);
  max-width:360px;
  letter-spacing:0.5px;
  overflow:hidden;
  position:fixed;
}
.toast.show{right:28px;}
.toast.error{border-color:var(--red);color:var(--red);}
.toast.warn{border-color:var(--amber);color:var(--amber);}
/* Toast 扫描线 */
.toast::after{
  content:'';position:absolute;left:0;right:0;height:1px;
  background:rgba(255,207,13,0.15);
  animation:toastScan 2s linear infinite;
}
@keyframes toastScan{from{top:0;}to{top:100%;}}

/* ===== 选择框 ===== */
select.form-input{
  appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23666666'/%3E%3C/svg%3E");
  background-repeat:no-repeat;
  background-position:right 12px center;
  padding-right:32px;
}
select.form-input option{background:var(--bg-panel-hover);color:var(--text);}

/* ===== 插件预留卡片 ===== */
.plugin-placeholder{
  border:2px dashed var(--border);
  background:rgba(0,0,0,0.15);
  opacity:.6;
  display:flex;flex-direction:column;
  align-items:center;justify-content:center;
  padding:32px;
  border-radius:2px;
  text-align:center;
  transition:opacity .3s,border-color .3s;
}
.plugin-placeholder:hover{opacity:.8;border-color:var(--amber-dim);}
.plugin-placeholder .pp-icon{font-size:32px;margin-bottom:12px;opacity:.5;}
.plugin-placeholder .pp-title{
  font-family:'JetBrains Mono',monospace;
  font-size:13px;color:var(--text-dim);
  letter-spacing:1px;
  text-transform:uppercase;
}
.plugin-placeholder .pp-sub{font-size:12px;color:var(--text-dim);margin-top:6px;}

/* ===== 底部状态栏 ===== */
.bottom-bar{
  position:fixed;bottom:0;left:var(--sidebar-w);right:0;
  height:28px;
  background:var(--bg-panel);
  border-top:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
  padding:0 20px;
  font-family:'JetBrains Mono',monospace;
  font-size:10px;color:var(--text-dim);
  z-index:90;
  transition:left .35s cubic-bezier(.4,0,.2,1);
  letter-spacing:.5px;
  text-transform:uppercase;
}
body.sidebar-collapsed .bottom-bar{left:var(--sidebar-collapsed);}
.bottom-bar .bar-left{display:flex;align-items:center;gap:16px;}
.bottom-bar .bar-right{display:flex;align-items:center;gap:16px;}
.bottom-bar .bar-sep{color:var(--border);}

/* ===== 响应式 ===== */
@media(max-width:900px){
  .sidebar{width:var(--sidebar-collapsed);}
  .sidebar .nav-item .label{opacity:0;}
  .sidebar .nav-item{padding:12px 0;justify-content:center;}
  .sidebar .sidebar-footer .footer-text{display:none;}
  .main-wrap{margin-left:var(--sidebar-collapsed);}
  .form-grid{grid-template-columns:1fr;}
  .form-row{grid-template-columns:1fr;}
  .stat-grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr));}
  .card-grid{grid-template-columns:1fr;}
  .bottom-bar{left:var(--sidebar-collapsed);}
}

/* ===== 滚动条 ===== */
::-webkit-scrollbar{width:5px;height:5px;}
::-webkit-scrollbar-track{background:transparent;}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px;}
::-webkit-scrollbar-thumb:hover{background:var(--amber-dim);}

/* ===== 标题故障抖动 — RGB色散 + clip-path ===== */
.glitch-title{
  position:relative;
  display:inline-block;
}
.glitch-title::before,
.glitch-title::after{
  content:attr(data-text);
  position:absolute;left:0;top:0;
  overflow:hidden;
  pointer-events:none;
}
.glitch-title::before{
  color:var(--red);
  clip-path:inset(0 0 65% 0);
  animation:glitchTop 3s infinite linear alternate-reverse;
}
.glitch-title::after{
  color:var(--cyan);
  clip-path:inset(65% 0 0 0);
  animation:glitchBottom 2.5s infinite linear alternate-reverse;
}
@keyframes glitchTop{
  0%,90%{transform:translate(0);}
  92%{transform:translate(-2px,-1px);}
  94%{transform:translate(2px,1px);}
  96%{transform:translate(-1px,0);}
  98%{transform:translate(1px,1px);}
  100%{transform:translate(0);}
}
@keyframes glitchBottom{
  0%,88%{transform:translate(0);}
  90%{transform:translate(2px,1px);}
  93%{transform:translate(-2px,-1px);}
  96%{transform:translate(1px,0);}
  100%{transform:translate(0);}
}

/* ===== 打字光标 ===== */
.typing::after{
  content:'█';
  animation:blink .8s infinite;
  color:var(--amber);
}
@keyframes blink{0%,100%{opacity:1;}50%{opacity:0;}}

/* ===== 装饰性坐标标注 ===== */
.coord-label{
  position:fixed;
  font-family:'JetBrains Mono',monospace;
  font-size:9px;color:rgba(255,207,13,0.06);
  letter-spacing:1px;pointer-events:none;z-index:0;
  user-select:none;
  text-transform:uppercase;
}

/* ===== 右上角角标 ===== */
.topbar-badge{
  width:32px;height:32px;
  display:flex;align-items:center;justify-content:center;
  font-size:16px;
  background:rgba(255,255,255,0.06);
  border:1px solid var(--border);
  border-radius:4px;
  cursor:pointer;
  color:var(--text-dim);
  transition:all .25s;
  position:relative;
  user-select:none;
}
.topbar-badge:hover{
  background:rgba(255,255,255,0.12);
  border-color:var(--amber-dim);
  color:var(--amber);
  box-shadow:0 0 10px var(--amber-glow);
}

/* 背景自定义模态 */
.bg-modal{
  display:none;
  position:fixed;inset:0;
  background:rgba(0,0,0,0.8);
  z-index:6000;
  align-items:center;justify-content:center;
  backdrop-filter:blur(8px);
}
.bg-modal.show{display:flex;}
.bg-modal-box{
  background:var(--bg-panel-hover);
  border:1px solid var(--border);
  border-radius:2px;
  padding:24px;
  width:420px;max-height:80vh;overflow-y:auto;
  animation:modalIn .3s ease;
}
.bg-modal-box h3{
  font-family:'JetBrains Mono',monospace;
  font-size:13px;color:var(--amber);
  letter-spacing:1px;margin-bottom:16px;
  text-transform:uppercase;
  display:flex;align-items:center;justify-content:space-between;
}
.bg-modal-box .close-btn{
  background:none;border:none;color:var(--text-dim);cursor:pointer;
  font-size:16px;padding:4px;
}
.bg-modal-box .close-btn:hover{color:var(--amber);}
.bg-option-group{
  margin-bottom:14px;
}
.bg-option-group label{
  display:block;font-size:11px;color:var(--text-dim);
  font-family:'JetBrains Mono',monospace;
  letter-spacing:.5px;margin-bottom:6px;
  text-transform:uppercase;
}
.bg-option-group input,.bg-option-group select{
  width:100%;
  background:rgba(0,0,0,0.4);
  border:1px solid var(--border);
  border-radius:2px;
  padding:7px 10px;
  color:var(--text);
  font-size:12px;
  font-family:'JetBrains Mono',monospace;
}
.bg-option-group input:focus{
  outline:none;border-color:var(--amber);
  box-shadow:0 0 6px var(--amber-glow);
}
.bg-option-group input[type="color"]{
  height:36px;padding:2px;cursor:pointer;
}
.bg-option-group input[type="range"]{
  -webkit-appearance:none;height:4px;
  background:var(--border);border-radius:2px;outline:none;
}
.bg-option-group input[type="range"]::-webkit-slider-thumb{
  -webkit-appearance:none;width:14px;height:14px;
  background:var(--amber);border-radius:50%;cursor:pointer;
}

/* 音乐面板 */
.music-panel{
  display:none;
  position:absolute;top:42px;right:0;
  background:var(--bg-panel-hover);
  border:1px solid var(--border);
  border-radius:2px;
  padding:14px 16px;
  width:280px;
  z-index:7000;
  box-shadow:0 8px 24px rgba(0,0,0,0.5);
  animation:modalIn .2s ease;
}
.music-panel.show{display:block;}
.music-panel-title{
  font-family:'JetBrains Mono',monospace;
  font-size:11px;color:var(--amber);
  letter-spacing:1px;margin-bottom:10px;
  text-transform:uppercase;
}
.music-panel input[type="text"]{
  width:100%;
  background:rgba(0,0,0,0.4);
  border:1px solid var(--border);
  border-radius:2px;
  padding:6px 8px;
  color:var(--text);
  font-size:11px;
  font-family:'JetBrains Mono',monospace;
  margin-bottom:8px;
}
.music-panel input[type="text"]:focus{
  outline:none;border-color:var(--amber);
}
.music-controls{
  display:flex;align-items:center;gap:8px;margin-bottom:8px;
}
.music-controls button{
  padding:5px 12px;
  background:rgba(255,255,255,0.06);
  border:1px solid var(--border);
  border-radius:2px;
  color:var(--text-dim);
  font-size:11px;cursor:pointer;
  font-family:'JetBrains Mono',monospace;
  transition:all .2s;
}
.music-controls button:hover{
  border-color:var(--amber);color:var(--amber);
}
.music-vol{
  display:flex;align-items:center;gap:8px;
}
.music-vol span{
  font-size:10px;color:var(--text-dim);
  font-family:'JetBrains Mono',monospace;
}
.music-vol input[type="range"]{
  flex:1;
  -webkit-appearance:none;height:3px;
  background:var(--border);border-radius:2px;outline:none;
}
.music-vol input[type="range"]::-webkit-slider-thumb{
  -webkit-appearance:none;width:10px;height:10px;
  background:var(--amber);border-radius:50%;cursor:pointer;
}

/* ===== 文件路径标签 ===== */
.file-tag{
  font-family:'JetBrains Mono',monospace;
  font-size:10px;
  color:var(--text-dim);
  letter-spacing:.5px;
  cursor:pointer;
  padding:2px 8px;
  border:1px solid transparent;
  border-radius:2px;
  transition:all .2s;
  opacity:.6;
}
.file-tag:hover{
  opacity:1;
  color:var(--amber-dim);
  border-color:var(--border);
  background:rgba(255,255,255,0.04);
}

/* 文件查看模态 */
.file-modal{
  display:none;
  position:fixed;inset:0;
  background:rgba(0,0,0,0.82);
  z-index:6000;
  align-items:center;justify-content:center;
  backdrop-filter:blur(8px);
}
.file-modal.show{display:flex;}
.file-modal-box{
  background:var(--bg-panel-hover);
  border:1px solid var(--border);
  border-radius:2px;
  padding:20px;
  width:700px;max-width:90vw;max-height:80vh;
  display:flex;flex-direction:column;
  animation:modalIn .3s ease;
}
.file-modal-header{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:12px;
}
.file-modal-header h3{
  font-family:'JetBrains Mono',monospace;
  font-size:12px;color:var(--amber);
  letter-spacing:1px;
  text-transform:uppercase;
}
.file-modal-header .close-btn{
  background:none;border:none;color:var(--text-dim);cursor:pointer;
  font-size:16px;
}
.file-modal-header .close-btn:hover{color:var(--amber);}
.file-modal-pre{
  flex:1;overflow:auto;
  background:rgba(0,0,0,0.4);
  border:1px solid var(--border);
  border-radius:2px;
  padding:14px;
  font-family:'JetBrains Mono',monospace;
  font-size:12px;
  color:var(--text-dim);
  line-height:1.7;
  white-space:pre-wrap;
  word-break:break-all;
  max-height:60vh;
}

/* ===== 模块解释弹窗 ===== */
.module-info-toast{
  position:fixed;top:60px;left:50%;transform:translateX(-50%);
  background:var(--bg-panel-hover);
  border:1px solid var(--amber);
  border-radius:2px;
  padding:14px 20px;
  width:400px;max-width:90vw;
  z-index:8000;
  box-shadow:0 4px 20px rgba(0,0,0,0.5),0 0 12px var(--amber-glow);
  animation:modalIn .3s ease;
  font-family:'JetBrains Mono',monospace;
}
.module-info-toast .mi-title{
  font-size:12px;color:var(--amber);
  letter-spacing:1px;margin-bottom:6px;
  text-transform:uppercase;
}
.module-info-toast .mi-body{
  font-size:12px;color:var(--text-dim);
  line-height:1.6;
}
.module-info-toast .mi-close{
  position:absolute;top:8px;right:10px;
  background:none;border:none;color:var(--text-dim);
  cursor:pointer;font-size:14px;
}
.module-info-toast .mi-close:hover{color:var(--amber);}
.module-info-toast .mi-timer{
  position:absolute;bottom:0;left:0;height:2px;
  background:var(--amber);
  transition:width 5s linear;
}

/* ===== Token / README 页面 ===== */
.token-section{
  display:grid;grid-template-columns:1fr 1fr;gap:16px;
}
.token-card{
  background:var(--bg-panel);
  border:1px solid var(--border);
  border-radius:2px;
  padding:18px;
}
.token-card-title{
  font-family:'JetBrains Mono',monospace;
  font-size:11px;color:var(--amber);
  letter-spacing:1px;margin-bottom:12px;
  text-transform:uppercase;
}
.token-card .stat-value{
  font-size:20px;margin-bottom:4px;
}
.readme-content{
  background:var(--bg-panel);
  border:1px solid var(--border);
  border-radius:2px;
  padding:28px;
  font-size:14px;
  line-height:1.8;
  color:var(--text);
}
.readme-content h1,.readme-content h2,.readme-content h3,.readme-content h4{
  font-family:'JetBrains Mono',monospace;
  color:var(--amber);
  margin:20px 0 10px;
  letter-spacing:1px;
}
.readme-content h1{font-size:22px;border-bottom:1px solid var(--border);padding-bottom:10px;}
.readme-content h2{font-size:18px;}
.readme-content h3{font-size:15px;}
.readme-content p{margin:8px 0;}
.readme-content code{
  font-family:'JetBrains Mono',monospace;
  background:rgba(0,0,0,0.4);
  padding:2px 6px;border-radius:2px;
  font-size:12px;color:var(--amber-dim);
}
.readme-content pre{
  background:rgba(0,0,0,0.5);
  border:1px solid var(--border);
  border-radius:2px;
  padding:14px;overflow-x:auto;
  margin:12px 0;
}
.readme-content pre code{
  background:none;padding:0;font-size:12px;color:var(--text-dim);
}
.readme-content ul,.readme-content ol{
  padding-left:24px;margin:8px 0;
}
.readme-content li{margin:4px 0;}
.readme-content a{
  color:var(--cyan);text-decoration:none;
  border-bottom:1px solid rgba(255,255,255,0.2);
}
.readme-content a:hover{border-bottom-color:var(--cyan);}
.readme-content table{
  width:100%;border-collapse:collapse;margin:12px 0;
  font-size:13px;
}
.readme-content th,.readme-content td{
  padding:8px 12px;border:1px solid var(--border);
  text-align:left;
}
.readme-content th{
  background:rgba(255,207,13,0.04);
  font-family:'JetBrains Mono',monospace;
  font-size:11px;color:var(--amber-dim);
  letter-spacing:1px;text-transform:uppercase;
}
.readme-content blockquote{
  border-left:3px solid var(--amber);
  padding-left:14px;margin:10px 0;
  color:var(--text-dim);
}
.readme-content strong{color:var(--amber-dim);}

/* 响应式补充 */
@media(max-width:900px){
  .token-section{grid-template-columns:1fr;}
  .bg-modal-box,.file-modal-box{width:95vw;}
  .module-info-toast{width:90vw;}
  .music-panel{width:240px;right:-40px;}
}

/* ===== 顶部按钮 ===== */
.topbar-btn{
  background:transparent;border:1px solid var(--border);
  color:var(--text-dim);font-family:'JetBrains Mono',monospace;
  font-size:10px;padding:4px 10px;cursor:pointer;
  letter-spacing:1px;transition:all .2s;
  text-transform:uppercase;
}
.topbar-btn:hover{
  border-color:var(--amber);color:var(--amber);
  box-shadow:0 0 8px rgba(255,255,255,0.1);
}
.btn-danger{
  background:rgba(255,62,62,0.1);border:1px solid var(--red);
  color:var(--red);font-family:'JetBrains Mono',monospace;
  font-size:12px;padding:10px 20px;cursor:pointer;
  letter-spacing:1px;transition:all .2s;
}
.btn-danger:hover{
  background:rgba(255,62,62,0.2);
  box-shadow:0 0 12px rgba(255,62,62,0.3);
}
/* ===== 确认弹窗 ===== */
.confirm-overlay{
  position:fixed;inset:0;background:rgba(0,0,0,0.7);
  backdrop-filter:blur(4px);z-index:99999;
  display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transition:opacity .3s;
}
.confirm-overlay.show{opacity:1;pointer-events:auto;}
.confirm-box{
  background:var(--bg-panel);border:2px solid var(--red);
  padding:24px;max-width:420px;width:90%;
  box-shadow:0 0 40px rgba(255,62,62,0.2);
}
.confirm-title{
  font-family:'JetBrains Mono',monospace;font-size:16px;
  color:var(--red);margin-bottom:12px;letter-spacing:1px;
}
.confirm-text{font-size:13px;color:var(--text);line-height:1.6;margin-bottom:20px;}
.confirm-actions{display:flex;gap:12px;justify-content:flex-end;}
.confirm-actions button{
  padding:8px 20px;font-family:'JetBrains Mono',monospace;
  font-size:12px;cursor:pointer;letter-spacing:1px;
  border:1px solid;transition:all .2s;
}
.confirm-cancel{background:transparent;border-color:var(--border);color:var(--text-dim);}
.confirm-cancel:hover{border-color:var(--text);color:var(--text);}
.confirm-ok{background:rgba(255,62,62,0.15);border-color:var(--red);color:var(--red);}
.confirm-ok:hover{background:rgba(255,62,62,0.3);}


/* ===== 数据库表选择 ===== */
#dbTableList .btn{transition:all .2s;}
#dbTableList .btn:hover{transform:translateY(-1px);}
.db-row-delete{color:var(--red);cursor:pointer;font-size:11px;}
.db-row-delete:hover{text-decoration:underline;}


/* ===== UBAI 水印 ===== */
.ubai-watermark{
  position:fixed;bottom:8px;right:8px;
  font-family:'JetBrains Mono',monospace;
  font-size:10px;color:rgba(255,255,255,0.08);
  letter-spacing:2px;z-index:1;pointer-events:none;
}

</style>
</head>
<body>

<!-- 加载动画 -->
<div class="loader-wrap" id="loader">
  <div class="loader-diamond"></div><div class="loader-diamond"></div><div class="loader-diamond"></div><div class="loader-diamond"></div>
</div>

<!-- 扫描线 -->
<div id="scanLine"></div>

<canvas id="particles"></canvas>

<!-- 装饰性坐标标注 -->
<div class="coord-label" style="top:12%;right:3%;">LAT 31.23° N</div>
<div class="coord-label" style="top:28%;right:5%;">LNG 121.47° E</div>
<div class="coord-label" style="bottom:18%;left:3%;">SYS.BUILD v3.0.0</div>
<div class="coord-label" style="top:45%;left:2%;">NODE-07 ONLINE</div>
<div class="coord-label" style="bottom:32%;right:2%;">FREQ 2.4GHz</div>
<div class="coord-label" style="top:65%;right:4%;">SECTOR-Δ</div>
<div class="coord-label" style="top:8%;left:5%;">C.R.O.W.N://BLACK.CROWN</div>
<div class="coord-label" style="bottom:8%;right:6%;">ORIPATH.MONITOR</div>

<!-- 侧边栏 -->
<nav class="sidebar" id="sidebar">
  <div class="sidebar-header">
    <div class="logo-hex">
      <svg viewBox="0 0 40 40"><polygon points="20,2 38,20 20,38 2,20" fill="none" stroke="#ffffff" stroke-width="2"/><text class="logo-hex-text" x="20" y="24" text-anchor="middle">C</text></svg>
    </div>
    <div class="logo-info">
      <div class="logo-title glitch-title" data-text="C.R.O.W.N.">C.R.O.W.N.</div>
      <div class="logo-sub">黑冠 — BLACK CROWN 战术配置系统</div>
    </div>
    <button class="sidebar-toggle" onclick="toggleSidebar()" title="收起/展开">◀</button>
  </div>

  <div class="sidebar-nav" id="sidebarNav">
    <div class="nav-item active" data-page="overview" onclick="switchPage('overview')">
      <span class="icon">📊</span><span class="label">系统总览</span>
    </div>
    <div class="nav-item" data-page="companion-hub" onclick="switchPage('companion-hub')">
      <span class="icon">◎</span><span class="label">陪伴中枢</span>
    </div>
    <div class="nav-item" data-page="system-audit" data-complex="1" onclick="switchPage('system-audit')">
      <span class="icon">◆</span><span class="label">系统自检</span>
    </div>
    <div class="nav-item" data-page="eval-console" data-complex="1" onclick="switchPage('eval-console')">
      <span class="icon">E</span><span class="label">评测控制台</span>
    </div>
    <div class="nav-item" data-page="config" onclick="switchPage('config')">
      <span class="icon">⚙️</span><span class="label">模型配置</span>
    </div>
    <div class="nav-item" data-page="persona" onclick="switchPage('persona')">
      <span class="icon">👤</span><span class="label">人设控制</span>
    </div>
    <div class="nav-item" data-page="scenes" onclick="switchPage('scenes')">
      <span class="icon">🎭</span><span class="label">场景管理</span>
    </div>
    <div class="nav-item" data-page="tones" onclick="switchPage('tones')">
      <span class="icon">🎵</span><span class="label">语气管理</span>
    </div>
    <div class="nav-item" data-page="plugins" onclick="switchPage('plugins')">
      <span class="icon">🔌</span><span class="label">插件控制</span>
    </div>
    <div class="nav-item" data-page="backups" onclick="switchPage('backups')">
      <span class="icon">💾</span><span class="label">备份管理</span>
    </div>
    <div class="nav-item" data-page="modules" onclick="switchPage('modules')">
      <span class="icon">🧩</span><span class="label">模块管理</span>
    </div>
    <div class="nav-item" data-page="proactive" onclick="switchPage('proactive')">
      <span class="icon">💬</span><span class="label">主动消息</span>
    </div>
    <div class="nav-item" data-page="growth-goals" onclick="switchPage('growth-goals')">
      <span class="icon">🎯</span><span class="label">成长目标</span>
    </div>
    <div class="nav-item" data-page="audio" onclick="switchPage('audio')">
      <span class="icon">🎤</span><span class="label">音频组</span>
    </div>
    <div class="nav-item" data-page="relationship" onclick="switchPage('relationship')">
      <span class="icon">💕</span><span class="label">关系定制</span>
    </div>
    <div class="nav-item" data-page="whitelist" onclick="switchPage('whitelist')">
      <span class="icon">👥</span><span class="label">白名单</span>
    </div>
    <!-- 高级设置分组 -->
    <div id="advancedNavTitle" style="padding:16px 20px 6px;font-size:10px;color:var(--text-dim);letter-spacing:2px;font-family:'JetBrains Mono',monospace;text-transform:uppercase;border-top:1px solid var(--border);margin-top:8px;">
      ◆ 高级设置
    </div>
    <div id="advancedNavGroup">
    <div class="nav-item" data-page="dimensions" data-complex="1" onclick="switchPage('dimensions')">
      <span class="icon">📐</span><span class="label">多维性格</span>
    </div>
    <div class="nav-item" data-page="persona-psychology" data-complex="1" onclick="switchPage('persona-psychology')">
      <span class="icon">🧠</span><span class="label">人格心理画像</span>
    </div>
    <div class="nav-item" data-page="account-binding" data-complex="1" onclick="switchPage('account-binding')">
      <span class="icon">🔗</span><span class="label">账号绑定</span>
    </div>
    <div class="nav-item" data-page="mental-health" data-complex="1" onclick="switchPage('mental-health')">
      <span class="icon">💊</span><span class="label">心理健康与分析</span>
    </div>
    <div class="nav-item" data-page="memory-ledger" data-complex="1" onclick="switchPage('memory-ledger')">
      <span class="icon">🧾</span><span class="label">记忆账本</span>
    </div>
    <div class="nav-item" data-page="chat-import" data-complex="1" onclick="switchPage('chat-import')">
      <span class="icon">馃Ю</span><span class="label">鑱婂ぉ璁板綍瀵煎叆</span>
    </div>
    <div class="nav-item" data-page="database" data-complex="1" onclick="switchPage('database')">
      <span class="icon">🗄️</span><span class="label">数据库</span>
    </div>
    <div class="nav-item" data-page="readme" onclick="switchPage('readme')">
      <span class="icon">📖</span><span class="label">项目文档</span>
    </div>
    </div>
  </div>

  <div class="sidebar-footer">
    <div class="status-dot"></div>
    <span class="footer-text">SYSTEM ONLINE</span>
  </div>
</nav>

<!-- 主区域 -->
<div class="main-wrap" id="mainWrap">
  <div class="topbar">
    <div class="topbar-left">
      <span class="topbar-title">C.R.O.W.N. // 黑冠</span>
      <span class="topbar-sep">│</span>
      <span class="breadcrumb" id="breadcrumb">- 系统总览</span>
    </div>
    <div class="topbar-right">
      <div class="topbar-badge" onclick="openBgModal()" title="自定义背景">▣</div>
      <div class="topbar-badge" style="position:relative;" onclick="toggleMusicPanel()" title="背景音乐">
        ♪
        <div class="music-panel" id="musicPanel" onclick="event.stopPropagation()">
          <div class="music-panel-title">背景音乐</div>
          <input type="text" id="musicUrl" placeholder="音乐 URL" onchange="saveMusicSettings()">
          <div class="music-controls">
            <button onclick="toggleMusic()" id="musicPlayBtn">播放</button>
            <button onclick="stopMusic()">停止</button>
          </div>
          <div class="music-vol">
            <span>音量</span>
            <input type="range" id="musicVol" min="0" max="1" step="0.05" value="0.5" oninput="setMusicVol(this.value)">
          </div>
        </div>
      </div>
      <span class="sys-info" id="clockDisplay">--:--:--</span>
    </div>
  </div>

  <div class="main-content">

    <!-- ===== 系统总览 ===== -->
    <div class="page active" id="page-overview">
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">?? 当前活跃人设</div>
          <span class="panel-toggle open">??</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;align-items:center;gap:16px;flex-wrap:wrap;">
            <select id="overviewPersonaSelect" class="form-input" style="width:240px;"></select>
            <button class="btn" onclick="switchActivePersona()">[ 切换人设 ]</button>
            <span style="font-size:12px;color:var(--text-dim);" id="overviewPersonaStatus"></span>
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:8px;">切换后需重启机器人生效。此切换是真实切换聊天人格，不是映射。</div>
        </div>
      </div>

      <div class="stat-grid" id="statsGrid"></div>

      <!-- AI 状态面板 -->
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">AI 运行状态</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div id="aiStatusPanel" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;"></div>
        </div>
      </div>

      <!-- 人设数据库信息 -->
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">人设数据库</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div id="personaDBInfo" style="font-family:'JetBrains Mono',monospace;font-size:12px;"></div>
          <div style="margin-top:12px;display:flex;align-items:center;gap:12px;">
            <span style="font-size:13px;">心理画像共享：</span>
            <div class="toggle" id="psychSharedToggle" onclick="togglePsychShared()"></div>
            <span style="font-size:11px;color:var(--text-dim);">开启=所有人设共享心理画像 / 关闭=每个人设独立</span>
          </div>
        </div>
      </div>

      <!-- 危险操作区 -->
      <div class="glass-panel" style="border-color:rgba(255,62,62,0.3);">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title" style="color:var(--red);">⚠ 危险操作</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;gap:12px;flex-wrap:wrap;">
            <button class="btn btn-danger" onclick="clearAllDB()">清空全部数据库</button>
            <button class="btn btn-danger" onclick="restartBot()">重启文明（重启聊天ai）</button>
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:8px;">
            清空数据库将删除所有聊天记录、用户画像、记忆、情绪状态、语音文件、表情包缓存。此操作不可恢复。
          </div>
        </div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">PATH 状态检测</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div id="pathStatus" style="font-family:'JetBrains Mono',monospace;font-size:13px;margin-bottom:14px;"></div>
          <button class="btn" onclick="registerPath()">[ 一键注册 PATH ]</button>
        </div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">系统日志</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div class="log-box" id="systemLog"></div>
        </div>
      </div>

      <div class="btn-group">
        <button class="btn btn-red" onclick="confirmResetConfig()">[ 一键清空所有配置 ]</button>
      </div>
    </div>

    <!-- ===== 陪伴中枢 ===== -->
    <div class="page" id="page-companion-hub">
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">◎ 陪伴中枢</div>
          <span class="panel-toggle open">▾</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
            <input id="hubUserInput" class="form-input" style="width:220px;" placeholder="用户ID，可留空">
            <input id="hubPersonaInput" class="form-input" style="width:180px;" placeholder="人设，可留空">
            <select id="hubLimitInput" class="form-input" style="width:110px;">
              <option value="5">最近 5 条</option>
              <option value="10">最近 10 条</option>
              <option value="20">最近 20 条</option>
            </select>
            <button class="btn" onclick="loadCompanionHub()">刷新中枢</button>
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:8px;">只读总览：用于查看她当前可参考的记忆、目标、安全、关系和主动消息判断，不会直接修改聊天数据。</div>
        </div>
      </div>
      <div class="stat-grid" id="hubStatsGrid"></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;">
        <div class="glass-panel"><div class="panel-header"><div class="panel-title">当前对象</div><button class="btn" onclick="hubJump('relationship')">关系页</button></div><div class="panel-body" id="hubContextBox"></div></div>
        <div class="glass-panel"><div class="panel-header"><div class="panel-title">风险与安全</div><button class="btn" onclick="hubJump('database')">数据页</button></div><div class="panel-body" id="hubSafetyBox"></div></div>
        <div class="glass-panel"><div class="panel-header"><div class="panel-title">记忆账本</div><button class="btn" onclick="hubJump('memory-ledger')">详情页</button></div><div class="panel-body" id="hubMemoryBox"></div></div>
        <div class="glass-panel"><div class="panel-header"><div class="panel-title">成长目标</div><button class="btn" onclick="hubJump('growth-goals')">详情页</button></div><div class="panel-body" id="hubGrowthBox"></div></div>
        <div class="glass-panel"><div class="panel-header"><div class="panel-title">主动消息判断</div><button class="btn" onclick="hubJump('proactive')">事件页</button></div><div class="panel-body" id="hubProactiveBox"></div></div>
        <div class="glass-panel"><div class="panel-header"><div class="panel-title">AI 与心理画像</div><button class="btn" onclick="hubJump('mental-health')">分析页</button></div><div class="panel-body" id="hubAiPsychBox"></div></div>
      </div>
    </div>

    <!-- ===== 系统自检 ===== -->
    <div class="page" id="page-system-audit">
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">◆ 系统自检</div>
          <span class="panel-toggle open">▾</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
            <button class="btn" onclick="loadSystemAudit()">刷新自检</button>
            <button class="btn" onclick="auditJump('database')">数据库页</button>
            <button class="btn" onclick="auditJump('companion-hub')">陪伴中枢</button>
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:8px;">只读自检：检查项目结构、模块文件、WebUI 接口和数据库表是否已经接上，不会修改聊天或数据库内容。</div>
        </div>
      </div>
      <div class="stat-grid" id="auditStatsGrid"></div>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px;">
        <div class="glass-panel">
          <div class="panel-header"><div class="panel-title">项目结构</div></div>
          <div class="panel-body" id="auditStructureBox"></div>
        </div>
        <div class="glass-panel">
          <div class="panel-header"><div class="panel-title">聊天与数据库模块</div></div>
          <div class="panel-body" id="auditModulesBox"></div>
        </div>
      </div>
      <div class="glass-panel" style="margin-top:16px;">
        <div class="panel-header"><div class="panel-title">WebUI 页面联通性</div></div>
        <div class="panel-body" id="auditPagesBox"></div>
      </div>
      <div class="glass-panel" style="margin-top:16px;">
        <div class="panel-header"><div class="panel-title">数据库与表</div></div>
        <div class="panel-body" id="auditDatabaseBox"></div>
      </div>
    </div>

    <!-- ===== 模型配置 ===== -->
    <div class="page" id="page-eval-console">
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header"><div class="panel-title">评测运行</div></div>
        <div class="panel-body">
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
            <input id="evalUserId" class="form-input" style="width:180px;" placeholder="用户ID（可选）">
            <input id="evalPersona" class="form-input" style="width:160px;" placeholder="人设（可选）">
            <button class="btn" onclick="runEvalSuite()">运行评测</button>
            <button class="btn" onclick="loadEvalReports()">刷新历史</button>
          </div>
          <div style="margin-top:8px;font-size:11px;color:var(--text-dim);">
            评测控制台为只读评估：用于判断当前链路是否接通，不会直接改写聊天记录和配置。
          </div>
          <div id="evalScenarioBox" style="margin-top:10px;color:var(--text-dim);font-size:12px;">场景加载中...</div>
        </div>
      </div>
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header"><div class="panel-title">本次结果</div></div>
        <div class="panel-body">
          <div id="evalSummaryBox" style="margin-bottom:10px;color:var(--text-dim);">暂无数据</div>
          <div id="evalResultsBox"></div>
        </div>
      </div>
      <div class="glass-panel">
        <div class="panel-header"><div class="panel-title">历史报告</div></div>
        <div class="panel-body">
          <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
            <select id="evalHistoryStatus" class="form-input" style="width:120px;" onchange="loadEvalReports()">
              <option value="">全部状态</option>
              <option value="pass">仅通过</option>
              <option value="warn">仅警告</option>
              <option value="fail">仅失败</option>
            </select>
            <input id="evalHistoryKeyword" class="form-input" style="width:180px;" placeholder="筛选关键词（report_id）" oninput="loadEvalReports()">
          </div>
          <div id="evalReportsBox">暂无历史</div>
        </div>
      </div>
    </div>

    <div class="page" id="page-config">

      <!-- 主对话模型 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">💬 主对话模型 (LLM) <span class="file-tag" onclick="event.stopPropagation();viewFile('config.yaml')">config.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div class="form-row"><label>平台预设</label><select id="llmPlatform" class="form-input" onchange="applyPlatform('llm',this.value)"><option value="">自定义</option><option value="mimo">小米 MiMo</option><option value="qwen">通义千问</option><option value="wenxin">文心一言</option><option value="zhipu">智谱 GLM</option><option value="kimi">月之暗面 Kimi</option><option value="deepseek">DeepSeek</option><option value="baichuan">百川</option><option value="minimax">MiniMax</option><option value="openai">OpenAI</option><option value="claude">Anthropic Claude</option><option value="gemini">Google Gemini</option><option value="mistral">Mistral</option><option value="groq">Groq</option></select></div>
          <div id="configLlm"></div>
        </div>
      </div>

      <!-- 轻量模型 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">⚡ 轻量模型 (后台任务) <span class="file-tag" onclick="event.stopPropagation();viewFile('config.yaml')">config.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div class="form-row"><label>平台预设</label><select id="lightPlatform" class="form-input" onchange="applyPlatform('light',this.value)"><option value="">自定义</option><option value="mimo">小米 MiMo</option><option value="qwen">通义千问</option><option value="deepseek">DeepSeek</option><option value="openai">OpenAI</option><option value="groq">Groq</option></select></div>
          <div id="configLight"></div>
        </div>
      </div>

      <!-- VLM 图像模型 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">👁️ VLM 图像识别模型 <span class="file-tag" onclick="event.stopPropagation();viewFile('config.yaml')">config.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div class="form-row"><label>平台预设</label><select id="vlmPlatform" class="form-input" onchange="applyPlatform('vlm',this.value)"><option value="">自定义</option><option value="mimo">小米 MiMo</option><option value="qwen">通义千问 (Qwen-VL)</option><option value="openai">OpenAI (GPT-4V)</option><option value="gemini">Google Gemini</option></select></div>
          <div id="configVlm"></div>
        </div>
      </div>

      <!-- TTS 语音 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">🎤 TTS 语音配置 <span class="file-tag" onclick="event.stopPropagation();viewFile('config.yaml')">config.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div class="form-row"><label>平台预设</label><select id="ttsPlatform" class="form-input" onchange="applyPlatform('tts',this.value)"><option value="">自定义</option><option value="mimo">小米 MiMo</option><option value="openai">OpenAI (TTS)</option></select></div>
          <div id="configTts"></div>
        </div>
      </div>

      <!-- 搜索 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">🔍 联网搜索配置 <span class="file-tag" onclick="event.stopPropagation();viewFile('config.yaml')">config.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="configSearch"></div>
      </div>

      <div class="btn-group">
        <button class="btn" onclick="saveConfig()">[ 保存配置 ]</button>
      </div>
    </div>

    <!-- ===== 人设控制 ===== -->
    <div class="page" id="page-persona">
      <div style="margin-bottom:18px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
        <select id="personaSelect" class="form-input" style="width:240px;" onchange="loadPersona()"></select>
        <button class="btn" onclick="createNewPersona()">+ 新增人设</button>
        <button class="btn btn-danger" onclick="deleteCurrentPersona()">删除人设</button>
        <span style="font-size:12px;color:var(--text-dim);" id="personaBindingStatus"></span>
      </div>

      <div class="glass-panel" style="margin-bottom:16px;border:2px dashed var(--border);" id="importDropZone">
        <div class="panel-body" style="text-align:center;padding:24px;">
          <div style="font-size:14px;color:var(--text-dim);margin-bottom:8px;">?? 拖入压缩包自动导入人设、场景组、语气组、音频组</div>
          <div style="font-size:11px;color:var(--text-dim);">支持 zip / rar / 7z 格式，人设文件必须包含 name 和 identity 字段</div>
          <input type="file" id="importZipInput" accept=".zip,.rar,.7z" style="display:none;" onchange="handleImportZip(this.files)">
          <button class="btn" style="margin-top:12px;" onclick="document.getElementById('importZipInput').click()">[ 或点击选择文件 ]</button>
        </div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">身份信息 <span class="file-tag persona-file-tag" onclick="event.stopPropagation();viewFile(personaFileTag())">personas/Theresa.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="personaIdentity"></div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">说话风格 <span class="file-tag persona-file-tag" onclick="event.stopPropagation();viewFile(personaFileTag())">personas/Theresa.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="personaStyle"></div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">行为准则 <span class="file-tag persona-file-tag" onclick="event.stopPropagation();viewFile(personaFileTag())">personas/Theresa.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="personaBehavior"></div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">知识范围 <span class="file-tag persona-file-tag" onclick="event.stopPropagation();viewFile(personaFileTag())">personas/Theresa.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="personaKnowledge"></div>
      </div>

      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">示例对话 <span class="file-tag persona-file-tag" onclick="event.stopPropagation();viewFile(personaFileTag())">personas/Theresa.yaml</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="personaExamples"></div>
      </div>

      <!-- 人设绑定 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">人设绑定</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div style="font-size:12px;color:var(--text-dim);margin-bottom:12px;">设置当前人设绑定的场景组、语气组和音频组</div>
          <div style="display:flex;gap:16px;flex-wrap:wrap;">
            <div>
              <div style="font-size:12px;margin-bottom:4px;">绑定场景组</div>
              <select id="bindSceneGroup" class="form-input" style="width:180px;" onchange="savePersonaBindings()"></select>
            </div>
            <div>
              <div style="font-size:12px;margin-bottom:4px;">绑定语气组</div>
              <select id="bindToneGroup" class="form-input" style="width:180px;" onchange="savePersonaBindings()"></select>
            </div>
            <div>
              <div style="font-size:12px;margin-bottom:4px;">绑定音频组</div>
              <select id="bindAudioGroup" class="form-input" style="width:180px;" onchange="savePersonaBindings()"></select>
            </div>
          </div>
        </div>
      </div>

      <div class="btn-group">
        <button class="btn" onclick="savePersona()">[ 保存人设 ]</button>
        <button class="btn btn-red" onclick="confirmResetPersona()">[ 一键恢复默认人格 ]</button>
      </div>

      <!-- 插件接口预留 data-plugin="persona-generator" -->
      <div class="glass-panel" data-plugin="persona-generator" style="margin-top:8px;">
        <div class="panel-header">
          <div class="panel-title">插件接口</div>
          <span class="panel-toggle">▸</span>
        </div>
        <div class="panel-body">
          <div class="plugin-placeholder">
            <div class="pp-icon">🧬</div>
            <div class="pp-title">人设生成器 — 即将开放</div>
            <div class="pp-sub">AI 驱动的人格生成与调优工具</div>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 场景管理 ===== -->
    <div class="page" id="page-scenes">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:12px;color:var(--text-dim);">场景组：</span>
        <select id="sceneGroupSelect" class="form-input" style="width:auto;min-width:150px;" onchange="switchSceneGroup(this.value)"></select>
        <button class="btn" onclick="createSceneGroup()">新建场景组</button>
        <button class="btn btn-danger" onclick="deleteCurrentSceneGroup()">删除场景组</button>
        <button class="btn" onclick="addSceneToGroup()">添加场景</button>
        <button class="btn" onclick="loadScenes()">刷新</button>
        <button class="btn" onclick="openFolder('data/scene_groups')">📁 打开文件夹</button>
      </div>
      <div class="card-grid" id="scenesGrid"></div>
      <div style="text-align:center;padding:16px;">
        <button class="btn" onclick="saveScenes()">保存场景组</button>
      </div>
    </div>

    <!-- ===== 语气管理 ===== -->
    <div class="page" id="page-tones">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:12px;color:var(--text-dim);">语气组：</span>
        <select id="toneGroupSelect" class="form-input" style="width:auto;min-width:150px;" onchange="switchToneGroup(this.value)"></select>
        <button class="btn" onclick="createToneGroup()">新建语气组</button>
        <button class="btn btn-danger" onclick="deleteCurrentToneGroup()">删除语气组</button>
        <button class="btn" onclick="addToneToGroup()">添加语气</button>
        <button class="btn" onclick="loadTones()">刷新</button>
        <button class="btn" onclick="openFolder('data/tone_groups')">📁 打开文件夹</button>
      </div>
      <div class="card-grid" id="tonesGrid"></div>
      <div style="text-align:center;padding:16px;">
        <button class="btn" onclick="saveTones()">保存语气组</button>
      </div>
    </div>

    <!-- ===== 插件控制 ===== -->
    <div class="page" id="page-plugins">
      <div id="pluginDropZone" style="border:2px dashed var(--border);border-radius:8px;padding:20px;text-align:center;margin-bottom:16px;transition:all 0.3s;cursor:pointer;" ondragover="event.preventDefault();this.style.borderColor='var(--amber)';this.style.background='var(--amber-bg)';" ondragleave="this.style.borderColor='var(--border)';this.style.background='';" ondrop="handlePluginDrop(event)" onclick="document.getElementById('pluginFileInput').click()">
        <div style="font-size:24px;margin-bottom:8px;">📦</div>
        <div style="font-size:13px;color:var(--text-dim);">拖入插件压缩包（.zip）到此处，或点击选择文件</div>
        <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">插件将自动解压到 src/plugins/custom/ 目录</div>
        <input type="file" id="pluginFileInput" accept=".zip" style="display:none;" onchange="handlePluginFileSelect(this)">
      </div>
      <div style="display:flex;gap:12px;margin-bottom:16px;">
        <button class="btn" onclick="loadPlugins()">刷新插件列表</button>
      </div>
      <div style="display:flex;flex-direction:column;gap:12px;" id="pluginsList"></div>
      <div id="pluginsEmpty" style="text-align:center;padding:40px;color:var(--text-dim);">
        <div style="font-size:32px;margin-bottom:12px;">🔌</div>
        <div style="font-family:'JetBrains Mono',monospace;letter-spacing:1px;">暂未发现插件</div>
        <div style="font-size:12px;margin-top:8px;">将插件放入 src/plugins/builtin/ 或 src/plugins/custom/ 目录</div>
      </div>
    </div>

    <!-- ===== 备份管理 ===== -->
    <div class="page" id="page-backups">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
        <button class="btn" onclick="generateBackup()">创建备份</button>
        <button class="btn" onclick="openFolder('data/backups')">📁 打开文件夹</button>
        <button class="btn" onclick="importBackupPrompt()">导入配置</button>
        <button class="btn btn-danger" onclick="clearAllBackups()" style="margin-left:auto;">🗑 清除所有备份</button>
      </div>
      <div style="font-size:11px;color:var(--text-dim);margin-bottom:12px;">本地备份上限 50 条，超出自动删除最早备份。当前备份数：<span id="backupCount">-</span></div>
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">备份文件列表</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <table class="backup-table" id="backupTable">
            <thead><tr><th>文件名</th><th>大小</th><th>创建时间</th><th>操作</th></tr></thead>
            <tbody id="backupBody"></tbody>
          </table>
          <div id="backupEmpty" style="text-align:center;padding:24px;color:var(--text-dim);display:none;">
            暂无备份文件
          </div>
        </div>
      </div>
      <input type="file" id="importFileInput" style="display:none;" accept=".yaml,.yml" onchange="handleImportFile(this)">
    </div>

    

    <!-- ===== 模块管理 ===== -->
    <div class="page" id="page-modules">
      <div style="display:flex;gap:12px;margin-bottom:16px;">
        <button class="btn" onclick="loadModules()">刷新</button>
      </div>
      <div id="modulesGrid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px;"></div>
    </div>

    <!-- ===== 主动消息 ===== -->
    <div class="page" id="page-proactive">
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">主动消息配置</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body" id="proactiveForm"></div>
      </div>
      <div style="text-align:center;padding:16px;">
        <button class="btn" onclick="saveProactive()">保存配置</button>
      </div>
      <div style="display:flex;gap:10px;margin:8px 0 12px;flex-wrap:wrap;align-items:center;">
        <input id="proactiveEventUser" class="form-input" style="width:180px;" placeholder="用户ID筛选">
        <select id="proactiveEventStatus" class="form-input" style="width:130px;">
          <option value="">全部状态</option>
          <option value="planned">已计划</option>
          <option value="sent">已发送</option>
          <option value="skipped">已跳过</option>
          <option value="failed">失败</option>
        </select>
        <button class="btn" onclick="loadProactiveEvents()">刷新事件</button>
      </div>
      <div class="glass-panel">
        <div class="panel-header"><div class="panel-title">主动消息调度事件</div></div>
        <div class="panel-body" style="overflow-x:auto;">
          <table class="backup-table">
            <thead><tr><th>状态</th><th>触发类型</th><th>原因</th><th>时间</th><th>用户</th></tr></thead>
            <tbody id="proactiveEventBody"></tbody>
          </table>
          <div id="proactiveEventEmpty" style="text-align:center;padding:24px;color:var(--text-dim);display:none;">暂无主动消息事件</div>
        </div>
      </div>
    </div>

    <!-- ===== 成长目标 ===== -->
    <div class="page" id="page-growth-goals">
      <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <input id="goalUserFilter" class="form-input" style="width:160px;" placeholder="用户ID，如 qq_123">
        <input id="goalPersonaInput" class="form-input" style="width:140px;" placeholder="人设，如 Theresa">
        <input id="goalQuery" class="form-input" style="width:220px;" placeholder="搜索目标">
        <select id="goalStatusFilter" class="form-input" style="width:120px;">
          <option value="">全部状态</option>
          <option value="active">进行中</option>
          <option value="paused">暂停</option>
          <option value="completed">完成</option>
          <option value="archived">归档</option>
        </select>
        <button class="btn" onclick="loadGrowthGoals()">刷新</button>
        <button class="btn btn-primary" onclick="showGoalCreate()">+ 新建目标</button>
      </div>
      <div class="glass-panel">
        <div class="panel-header">
          <div class="panel-title">成长目标</div>
          <span id="goalCount" style="font-size:11px;color:var(--text-dim);">0 条</span>
        </div>
        <div class="panel-body" style="overflow-x:auto;">
          <table class="backup-table">
            <thead><tr><th>状态</th><th>类型</th><th>目标</th><th>微任务</th><th>跟进</th><th>压力</th><th>操作</th></tr></thead>
            <tbody id="goalBody"></tbody>
          </table>
          <div id="goalEmpty" style="text-align:center;padding:24px;color:var(--text-dim);display:none;">暂无成长目标</div>
        </div>
      </div>
    </div>

    <!-- ===== 音频组 ===== -->
    <div class="page" id="page-audio">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:12px;color:var(--text-dim);">音频组：</span>
        <select id="audioGroupSelect" class="form-input" style="width:auto;min-width:150px;" onchange="loadAudioFiles(this.value)"></select>
        <button class="btn" onclick="createAudioGroup()">新建音频组</button>
        <button class="btn" onclick="openFolder('data/audio_groups')">📁 打开文件夹</button>
      </div>

      <!-- 上传区域 -->
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">导入干声样本</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;gap:12px;align-items:center;flex-wrap:wrap;">
            <input type="file" id="audioUploadInput" accept=".wav,.mp3,.ogg,.flac,.m4a,.aac" style="display:none;" onchange="uploadAudioFile(this)">
            <button class="btn" onclick="document.getElementById('audioUploadInput').click()">选择音频文件</button>
            <span style="font-size:11px;color:var(--text-dim);">支持 wav/mp3/ogg/flac/m4a/aac</span>
          </div>
          <div style="margin-top:12px;font-size:11px;color:var(--text-dim);">
            提示：导入干声样本后，点击"设为TTS参考"即可将该音频组作为语音合成的音色参考。
          </div>
          <!-- 干声合成插件接口 -->
          <div data-plugin="voice-clone-extractor" style="margin-top:16px;padding:12px;border:1px dashed var(--border);opacity:0.5;">
            <div style="font-size:12px;color:var(--text-dim);">🔮 干声合成 / 人声提取 — 即将开放</div>
            <div style="font-size:10px;color:var(--text-dim);margin-top:4px;">未来接入 AI 干声分离、音色提取、声音克隆等能力</div>
          </div>
        </div>
      </div>

      <!-- 文件列表 -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title" id="audioFileTitle">音频文件</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div id="audioFileList"></div>
          <div id="audioFileEmpty" style="text-align:center;padding:24px;color:var(--text-dim);display:none;">
            暂无音频文件
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 关系定制 ===== -->
    <div class="page" id="page-relationship">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <button class="btn" onclick="loadRelationships()">刷新</button>
        <button class="btn" onclick="showAddRelationship()">+ 新增关系类型</button>
        <button class="btn" onclick="autoGenerateWhitelistBindings()">自动生成白名单配置</button>
        <span style="font-size:12px;color:var(--text-dim);">每个人设对每个账号只能激活一种关系</span>
      </div>

      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">关系简史（只读）</div>
          <span class="panel-toggle open">▼</span>
        </div>
        <div class="panel-body">
          <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:10px;">
            <input id="relBriefUserInput" class="form-input" style="width:180px;" placeholder="用户ID，如 qq_12345">
            <input id="relBriefPersonaInput" class="form-input" style="width:160px;" placeholder="人设（可选）">
            <input id="relBriefLimitInput" class="form-input" style="width:90px;" type="number" min="5" max="100" value="20">
            <button class="btn" onclick="loadRelationshipBrief()">刷新简史</button>
          </div>
          <div id="relBriefSummary" style="margin-bottom:10px;color:var(--text-dim);font-size:12px;">暂无数据</div>
          <div id="relBriefTimeline" style="display:flex;flex-direction:column;gap:6px;"></div>
        </div>
      </div>

      <!-- 用户当前关系状态 -->
      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">👥 用户关系状态（排他切换）</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div id="relUserList" style="color:var(--text-dim);">加载中...</div>
        </div>
      </div>

      <!-- 关系类型列表（只读展示） -->
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">💕 关系类型配置</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <div id="relTypeList" style="color:var(--text-dim);">加载中...</div>
        </div>
      </div>

      <!-- 编辑弹窗 -->
      <div id="relEditOverlay" class="confirm-overlay" style="display:none;" onclick="if(event.target===this)this.style.display='none'">
        <div class="confirm-box" style="max-width:700px;max-height:85vh;overflow-y:auto;">
          <div class="confirm-title" id="relEditTitle">新增关系类型</div>
          <div id="relEditForm" style="text-align:left;font-size:13px;"></div>
          <div class="confirm-actions">
            <button class="btn" onclick="document.getElementById('relEditOverlay').style.display='none'">取消</button>
            <button class="btn btn-primary" onclick="saveRelationshipType()">保存</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 多维性格 ===== -->
    <div class="page" id="page-dimensions">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:12px;color:var(--text-dim);">当前人设：</span>
        <select id="dimPersonaSelect" class="form-input" style="width:200px;" onchange="loadDimensionsData()"></select>
        <button class="btn" onclick="analyzeDimensions()">🧬 从人设自动分析</button>
        <button class="btn" onclick="saveDimensions()">💾 保存</button>
        <button class="btn btn-red" onclick="restoreDimensionsBaseline()">↩️ 恢复默认性格</button>
      </div>
      <div style="display:flex;gap:24px;flex-wrap:wrap;">
        <!-- 雷达图 -->
        <div class="glass-panel" style="flex:1;min-width:400px;">
          <div class="panel-header"><div class="panel-title">性格雷达图</div></div>
          <div class="panel-body" style="display:flex;justify-content:center;padding:20px;">
            <canvas id="dimensionsRadar" width="500" height="500"></canvas>
          </div>
        </div>
        <!-- 维度列表 -->
        <div class="glass-panel" style="flex:1;min-width:350px;">
          <div class="panel-header"><div class="panel-title">维度详情</div></div>
          <div class="panel-body" id="dimensionsList"></div>
        </div>
      </div>
      <!-- 历史回退 -->
      <div class="glass-panel" style="margin-top:16px;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">历史回退（0-8小时）</div>
          <span class="panel-toggle">▸</span>
        </div>
        <div class="panel-body collapsed">
          <div style="display:flex;gap:12px;margin-bottom:12px;align-items:center;">
            <select id="dimHistorySelect" class="form-input" style="width:400px;" onchange="previewHistoryDimensions()"></select>
            <button class="btn" onclick="rollbackDimensions()">回退到选中时间</button>
          </div>
          <div id="dimHistoryPreview" style="font-size:12px;color:var(--text-dim);"></div>
          <canvas id="historyRadar" width="400" height="400" style="max-width:400px;margin-top:12px;"></canvas>
        </div>
      </div>
    </div>

    <!-- ===== 人格心理画像 ===== -->
    <div class="page" id="page-persona-psychology">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:12px;color:var(--text-dim);">当前人设：</span>
        <select id="psyPersonaSelect" class="form-input" style="width:200px;" onchange="loadPersonaPsychologyData()"></select>
        <button class="btn" onclick="createPsychologyBaseline()">🧬 生成基线画像</button>
        <button class="btn" onclick="savePersonaPsychology()">💾 保存</button>
        <button class="btn btn-red" onclick="restorePsychologyBaseline()">↩️ 恢复基线心理状态</button>
      </div>
      <div class="glass-panel">
        <div class="panel-header"><div class="panel-title">心理画像维度</div></div>
        <div class="panel-body" id="psyDimensionsList"></div>
      </div>
    </div>

    <!-- ===== 账号配置绑定 ===== -->
    <div class="page" id="page-account-binding">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <button class="btn" onclick="loadAccountBindings()">刷新</button>
        <button class="btn" onclick="showAddAccountBinding()">+ 新增绑定</button>
      </div>
      <div class="glass-panel">
        <div class="panel-header"><div class="panel-title">账号绑定列表</div></div>
        <div class="panel-body" id="accountBindingList"></div>
      </div>
      <!-- 编辑弹窗 -->
      <div id="bindingEditOverlay" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:1000;display:none;align-items:center;justify-content:center;">
        <div style="background:var(--bg-panel);border:1px solid var(--border);border-radius:8px;padding:24px;width:500px;max-height:80vh;overflow-y:auto;">
          <h3 style="margin-bottom:16px;">编辑账号绑定</h3>
          <div id="bindingEditForm"></div>
          <div style="display:flex;gap:12px;margin-top:16px;justify-content:flex-end;">
            <button class="btn" onclick="document.getElementById('bindingEditOverlay').style.display='none'">取消</button>
            <button class="btn btn-primary" onclick="saveAccountBinding()">保存</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ===== 心理健康与分析 ===== -->
    <div class="page" id="page-mental-health">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:12px;color:var(--text-dim);">用户：</span>
        <select id="mhUserSelect" class="form-input" style="width:200px;" onchange="loadMentalHealthData()"></select>
        <span style="font-size:12px;color:var(--text-dim);">人设：</span>
        <select id="mhPersonaSelect" class="form-input" style="width:150px;" onchange="loadMentalHealthData()"></select>
        <button class="btn btn-primary" onclick="generateMentalHealth()">🤖 AI 生成分析</button>
        <button class="btn" onclick="loadMentalHealthData()">刷新</button>
        <button class="btn btn-danger" onclick="deleteMentalHealthData()">删除数据</button>
        <button class="btn" onclick="openMentalHealthDb()">📁 打开本地数据库</button>
      </div>
      <div id="mhContent" style="color:var(--text-dim);padding:20px;">选择用户和人设后点击"AI 生成分析"或等待自动加载</div>
    </div>

    <!-- ===== 统一记忆账本 ===== -->
    <div class="page" id="page-memory-ledger">
      <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <input id="ledgerUserFilter" class="form-input" style="width:160px;" placeholder="用户ID">
        <input id="ledgerPersonaFilter" class="form-input" style="width:140px;" placeholder="人设">
        <input id="ledgerQuery" class="form-input" style="width:240px;" placeholder="搜索内容/证据">
        <select id="ledgerTypeFilter" class="form-input" style="width:130px;">
          <option value="">全部类型</option>
          <option value="fact">事实</option>
          <option value="event">事件</option>
          <option value="preference">偏好</option>
          <option value="goal">目标</option>
          <option value="risk">风险</option>
          <option value="relationship">关系</option>
          <option value="opinion">观点</option>
          <option value="procedure">流程</option>
        </select>
        <select id="ledgerStatusFilter" class="form-input" style="width:130px;">
          <option value="">全部状态</option>
          <option value="pending">待确认</option>
          <option value="confirmed">已确认</option>
          <option value="auto">自动允许</option>
          <option value="rejected">已拒绝/旧版</option>
        </select>
        <button class="btn" onclick="loadMemoryLedger()">刷新</button>
      </div>
      <div class="glass-panel">
        <div class="panel-header">
          <div class="panel-title">统一记忆账本</div>
          <span id="ledgerCount" style="font-size:11px;color:var(--text-dim);">0 条</span>
        </div>
        <div class="panel-body" style="overflow-x:auto;">
          <table class="backup-table">
            <thead>
              <tr><th>状态</th><th>类型</th><th>内容</th><th>证据</th><th>置信度</th><th>版本</th><th>时间</th><th>操作</th></tr>
            </thead>
            <tbody id="ledgerBody"></tbody>
          </table>
          <div id="ledgerEmpty" style="text-align:center;padding:24px;color:var(--text-dim);display:none;">暂无记忆账本数据</div>
        </div>
      </div>
    </div>

    <!-- ===== 数据库 ===== -->
    <div class="page" id="page-chat-import">
      <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <input id="chatImportUserId" class="form-input" style="width:200px;" placeholder="用户ID">
        <input id="chatImportPersona" class="form-input" style="width:180px;" placeholder="人设(可留空)">
        <button class="btn" onclick="refreshChatImportDashboard()">刷新统计</button>
        <button class="btn" onclick="generateChatColdstartSummary()">生成冷启动摘要</button>
      </div>

      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header"><div class="panel-title">粘贴聊天记录</div></div>
        <div class="panel-body">
          <textarea id="chatImportText" class="form-input" style="min-height:150px;width:100%;resize:vertical;" placeholder="支持 TXT / HTML 粘贴。普通回车分行内容也会被逐条解析。"></textarea>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:10px;">
            <input id="chatImportSourceName" class="form-input" style="width:200px;" placeholder="来源标识(默认 manual_text)">
            <button class="btn" onclick="submitChatImportText()">导入文本</button>
          </div>
        </div>
      </div>

      <div class="glass-panel" style="margin-bottom:16px;">
        <div class="panel-header"><div class="panel-title">上传聊天记录文件</div></div>
        <div class="panel-body">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <input type="file" id="chatImportFile" class="form-input" accept=".zip,.html,.htm,.txt,.mht" style="width:320px;">
            <button class="btn" onclick="submitChatImportFile()">上传并导入</button>
          </div>
          <div style="font-size:11px;color:var(--text-dim);margin-top:8px;">支持 zip / html / txt / mht，导入后会写入 chat_records 与 chat_record_analysis。</div>
        </div>
      </div>

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px;">
        <div class="glass-panel">
          <div class="panel-header"><div class="panel-title">导入统计</div></div>
          <div class="panel-body" id="chatImportStatsBox">暂无数据</div>
        </div>
        <div class="glass-panel">
          <div class="panel-header"><div class="panel-title">最近分析</div></div>
          <div class="panel-body" id="chatImportAnalysisBox">暂无数据</div>
        </div>
      </div>

      <div class="glass-panel" style="margin-top:16px;">
        <div class="panel-header"><div class="panel-title">最近导入消息</div></div>
        <div class="panel-body" id="chatImportItemsBox">暂无数据</div>
      </div>

      <div class="glass-panel" style="margin-top:16px;">
        <div class="panel-header"><div class="panel-title">冷启动摘要结果</div></div>
        <div class="panel-body" id="chatImportColdstartBox">暂无数据</div>
      </div>
    </div>

    <div class="page" id="page-database">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;align-items:center;">
        <button class="btn" onclick="loadDBTables()">刷新表列表</button>
        <button class="btn" onclick="openFolder('data')">📁 打开数据目录</button>
        <span style="font-size:12px;color:var(--text-dim);margin-left:8px;">用户账号：</span>
        <select id="dbUserSelect" class="form-input" style="width:auto;min-width:180px;" onchange="onDBUserChange(this.value)">
          <option value="">-- 全部数据 --</option>
        </select>
        <span id="dbUserInfo" style="font-size:11px;color:var(--text-dim);"></span>
      </div>
      <div id="dbTableList" style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px;"></div>
      <div class="glass-panel" id="dbDataPanel" style="display:none;">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title" id="dbTableName">表数据</div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div style="padding:8px 16px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;border-bottom:1px solid var(--border);">
          <button class="btn" style="padding:4px 12px;font-size:11px;" onclick="showAddRowForm()">+ 新增数据</button>
          <button class="btn" style="padding:4px 12px;font-size:11px;" onclick="loadDBTable(_currentTable)">刷新当前表</button>
          <span id="dbAutoRefreshStatus" style="font-size:11px;color:var(--text-dim);margin-left:auto;">自动刷新: 关闭</span>
          <select id="dbAutoRefreshSelect" class="form-input" style="width:auto;padding:3px 8px;font-size:11px;" onchange="setDBAutoRefresh(this.value)">
            <option value="0">自动刷新: 关闭</option>
            <option value="3">3秒</option>
            <option value="5">5秒</option>
            <option value="10">10秒</option>
          </select>
        </div>
        <div class="panel-body" style="overflow-x:auto;">
          <table class="backup-table" id="dbDataTable">
            <thead id="dbDataHead"></thead>
            <tbody id="dbDataBody"></tbody>
          </table>
          <div id="dbDataEmpty" style="text-align:center;padding:24px;color:var(--text-dim);display:none;">暂无数据</div>
        </div>
      </div>
    </div>

    <!-- ===== 项目文档 ===== -->
    <div class="page" id="page-readme">
      <div class="readme-content" id="readmeContent" style="text-align:center;padding:40px;color:var(--text-dim);">
        加载中...
      </div>
    </div>

    <!-- ===== 白名单管理 ===== -->
    <div class="page" id="page-whitelist">
      <div style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap;">
        <button class="btn" onclick="loadWhitelist()">刷新</button>
        <button class="btn" onclick="showAddWhitelist()">+ 手动添加</button>
      </div>
      <div class="glass-panel">
        <div class="panel-header" onclick="togglePanel(this)">
          <div class="panel-title">用户白名单 <span class="file-tag" onclick="event.stopPropagation();viewFile('data/' + (window._activeDbName || 'chatbot.db'))">chat_whitelist</span></div>
          <span class="panel-toggle open">▸</span>
        </div>
        <div class="panel-body">
          <p style="font-size:12px;color:var(--text-dim);margin-bottom:12px;">只有在白名单中且启用的用户才能与AI聊天。第一个聊天的用户会自动添加。</p>
          <div id="whitelistContent">点击“刷新”加载...</div>
        </div>
      </div>
    </div>

  </div>
</div>

<!-- 底部状态栏 -->
<div class="bottom-bar">
  <div class="bar-left">
    <span>C.R.O.W.N://BLACK.CROWN</span>
    <span class="bar-sep">│</span>
    <span id="barStatus">INITIALIZING</span>
    <span class="bar-sep">│</span>
    <span id="barMem">MEM --</span>
  </div>
  <div class="bar-right">
    <span id="barCoord">X:0000 Y:0000</span>
    <span class="bar-sep">│</span>
    <span id="barClock">--:--:--</span>
    <span class="bar-sep">│</span>
    <span>v3.0.0-rc</span>
  </div>
</div>

<!-- 模态框 -->
<div class="modal-overlay" id="modalOverlay">
  <div class="modal">
    <div class="modal-title" id="modalTitle">确认操作</div>
    <div class="modal-body" id="modalBody"></div>
    <div class="modal-actions">
      <button class="btn" onclick="closeModal()">取消</button>
      <button class="btn btn-red" id="modalConfirm" onclick="">确认</button>
    </div>
  </div>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<!-- 背景自定义模态 -->
<div class="bg-modal" id="bgModal">
  <div class="bg-modal-box">
    <h3>自定义背景 <button class="close-btn" onclick="closeBgModal()">✕</button></h3>
    <div class="bg-option-group">
      <label>背景类型</label>
      <select id="bgType" onchange="onBgTypeChange()" style="width:100%;background:rgba(0,0,0,0.4);border:1px solid var(--border);border-radius:2px;padding:7px 10px;color:var(--text);font-size:12px;font-family:'JetBrains Mono',monospace;">
        <option value="none">默认</option>
        <option value="color">纯色背景</option>
        <option value="image">图片背景</option>
        <option value="gif">动图/GIF</option>
        <option value="video">视频背景</option>
      </select>
    </div>
    <div class="bg-option-group" id="bgColorGroup" style="display:none;">
      <label>颜色</label>
      <input type="color" id="bgColor" value="#111111">
    </div>
    <div class="bg-option-group" id="bgUrlGroup" style="display:none;">
      <label>URL 地址</label>
      <input type="text" id="bgUrl" placeholder="输入图片/视频 URL">
    </div>
    <div class="bg-option-group">
      <label>透明度</label>
      <input type="range" id="bgOpacity" min="0" max="1" step="0.05" value="1">
    </div>
    <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;">
      <button class="btn" onclick="applyBg()" style="padding:8px 16px;font-size:11px;">应用</button>
      <button class="btn btn-red" onclick="resetBg()" style="padding:8px 16px;font-size:11px;">重置</button>
    </div>
  </div>
</div>

<!-- 文件查看模态 -->
<div class="file-modal" id="fileModal">
  <div class="file-modal-box">
    <div class="file-modal-header">
      <h3 id="fileModalTitle">文件查看</h3>
      <button class="close-btn" onclick="closeFileModal()">✕</button>
    </div>
    <div class="file-modal-pre" id="fileModalContent">加载中...</div>
  </div>
</div>

<!-- 模块解释弹窗 -->
<div class="module-info-toast" id="moduleInfoToast" style="display:none;">
  <button class="mi-close" onclick="closeModuleInfo()">✕</button>
  <div class="mi-title" id="moduleInfoTitle"></div>
  <div class="mi-body" id="moduleInfoBody"></div>
  <div class="mi-timer" id="moduleInfoTimer"></div>
</div>

<script>
// ===== 加载动画 =====
// 不等待外部资源，800ms 后直接隐藏
setTimeout(function(){
  var loader=document.getElementById('loader');
  if(loader){
    loader.classList.add('hide');
    setTimeout(function(){loader.style.display='none';},600);
  }
},800);

// ===== 粒子系统 — Canvas 80-120 粒子 + 连线 + 扫描粒子 =====
(function(){
  const c=document.getElementById('particles'),ctx=c.getContext('2d');
  let w,h,pts=[];
  const PARTICLE_COUNT=100;
  const MAX_LINK_DIST=120;
  const LINK_ALPHA=0.15;

  // 性能降级检测
  let isLowPerf=false;
  try{
    if(navigator.hardwareConcurrency&&navigator.hardwareConcurrency<=2)isLowPerf=true;
    if(navigator.deviceMemory&&navigator.deviceMemory<=2)isLowPerf=true;
  }catch(e){}
  const actualCount=isLowPerf?Math.floor(PARTICLE_COUNT*0.4):PARTICLE_COUNT;

  function resize(){w=c.width=window.innerWidth;h=c.height=window.innerHeight;}
  window.addEventListener('resize',resize);resize();

  // 初始化粒子
  for(let i=0;i<actualCount;i++){
    pts.push({
      x:Math.random()*w,y:Math.random()*h,
      vx:(Math.random()-.5)*.3,vy:(Math.random()-.5)*.3,
      r:Math.random()*1.5+.5,
      o:Math.random()*.25+.05,
      baseO:0
    });
    pts[i].baseO=pts[i].o;
  }

  // 扫描粒子 Y 位置
  let scanY=0;
  const SCAN_SPEED=0.8;

  function draw(){
    ctx.clearRect(0,0,w,h);

    // 更新扫描线位置
    scanY+=SCAN_SPEED;
    if(scanY>h)scanY=0;

    // 绘制粒子
    pts.forEach(p=>{
      p.x+=p.vx;p.y+=p.vy;
      if(p.x<0)p.x=w;if(p.x>w)p.x=0;
      if(p.y<0)p.y=h;if(p.y>h)p.y=0;

      // 扫描线附近粒子亮度增强
      const distToScan=Math.abs(p.y-scanY);
      const scanBoost=distToScan<60?(1-distToScan/60)*0.3:0;
      const alpha=Math.min(1,p.baseO+scanBoost);

      ctx.beginPath();ctx.arc(p.x,p.y,p.r,0,Math.PI*2);
      ctx.fillStyle='rgba(200,200,200,'+alpha+')';ctx.fill();
    });

    // 粒子连线
    if(!isLowPerf){
      for(let i=0;i<pts.length;i++){
        for(let j=i+1;j<pts.length;j++){
          const dx=pts[i].x-pts[j].x,dy=pts[i].y-pts[j].y;
          const d=Math.sqrt(dx*dx+dy*dy);
          if(d<MAX_LINK_DIST){
            const alpha=LINK_ALPHA*(1-d/MAX_LINK_DIST);
            ctx.beginPath();ctx.moveTo(pts[i].x,pts[i].y);ctx.lineTo(pts[j].x,pts[j].y);
            ctx.strokeStyle='rgba(200,200,200,'+alpha+')';ctx.lineWidth=0.5;ctx.stroke();
          }
        }
      }
    }

    // 扫描线粒子（水平发光线）
    const grad=ctx.createLinearGradient(0,scanY-1,0,scanY+1);
    grad.addColorStop(0,'transparent');
    grad.addColorStop(0.5,'rgba(255,207,13,0.08)');
    grad.addColorStop(1,'transparent');
    ctx.fillStyle=grad;
    ctx.fillRect(0,scanY-20,w,40);

    requestAnimationFrame(draw);
  }
  draw();

  // 暴露数据流粒子方法（页面切换时调用）
  window.spawnDataParticles=function(dir){
    const count=15;
    for(let i=0;i<count;i++){
      const startX=dir==='left'?0:w;
      const startY=Math.random()*h;
      pts.push({
        x:startX,y:startY,
        vx:dir==='left'?(2+Math.random()*3):-(2+Math.random()*3),
        vy:(Math.random()-.5)*2,
        r:1.5+Math.random(),
        o:0.6,
        baseO:0.6,
        life:60
      });
    }
    // 清理临时粒子
    setTimeout(function(){
      pts=pts.filter(p=>!p.life||p.life>0);
    },2000);
  };

  // 按钮粒子爆发
  window.spawnButtonBurst=function(x,y){
    const count=10;
    for(let i=0;i<count;i++){
      const angle=Math.PI*2*i/count+Math.random()*.3;
      const speed=1.5+Math.random()*2;
      pts.push({
        x:x,y:y,
        vx:Math.cos(angle)*speed,
        vy:Math.sin(angle)*speed,
        r:1+Math.random(),
        o:0.7,
        baseO:0.7,
        life:40
      });
    }
    setTimeout(function(){
      pts=pts.filter(p=>!p.life||p.life>0);
    },1500);
  };

  // 衰减临时粒子
  setInterval(function(){
    pts.forEach(p=>{
      if(p.life!==undefined){
        p.life--;
        p.o=Math.max(0,p.baseO*(p.life/40));
        p.vx*=0.97;p.vy*=0.97;
      }
    });
  },50);
})();

// ===== 时钟 =====
function updateClock(){
  const now=new Date();
  const h=String(now.getHours()).padStart(2,'0');
  const m=String(now.getMinutes()).padStart(2,'0');
  const s=String(now.getSeconds()).padStart(2,'0');
  const ts=h+':'+m+':'+s;
  document.getElementById('clockDisplay').textContent=ts;
  document.getElementById('barClock').textContent=ts;
}
setInterval(updateClock,1000);updateClock();

// ===== 底部坐标装饰 =====
(function(){
  function updateCoord(){
    const x=Math.floor(Math.random()*9999).toString().padStart(4,'0');
    const y=Math.floor(Math.random()*9999).toString().padStart(4,'0');
    document.getElementById('barCoord').textContent='X:'+x+' Y:'+y;
  }
  setInterval(updateCoord,3000);updateCoord();
})();

// ===== 底部状态栏 =====
function updateBarStatus(){
  document.getElementById('barStatus').textContent='ONLINE';
  if(performance&&performance.memory){
    const mb=Math.round(performance.memory.usedJSHeapSize/1048576);
    document.getElementById('barMem').textContent='MEM '+mb+'MB';
  }
}
setInterval(updateBarStatus,5000);updateBarStatus();

// ===== 全局状态 =====
let currentPage='overview';
let configData={},personaData={},scenesData={},tonesData={},currentPersona='';
const pageNames={overview:'系统总览','companion-hub':'陪伴中枢','system-audit':'系统自检','eval-console':'评测控制台',config:'模型配置',persona:'人设控制',scenes:'场景管理',tones:'语气管理',plugins:'插件控制',backups:'备份管理',modules:'模块管理',proactive:'主动消息','growth-goals':'成长目标',audio:'音频组',relationship:'关系定制',whitelist:'白名单',dimensions:'多维性格','persona-psychology':'人格心理画像','account-binding':'账号绑定','mental-health':'心理健康与分析','memory-ledger':'记忆账本','chat-import':'聊天记录导入',database:'数据库',readme:'项目文档'};
const pageIndex={overview:0,'companion-hub':1,'system-audit':2,'eval-console':3,config:4,persona:5,scenes:6,tones:7,plugins:8,backups:9,modules:10,proactive:11,'growth-goals':12,audio:13,relationship:14,whitelist:15,dimensions:16,'persona-psychology':17,'account-binding':18,'mental-health':19,'memory-ledger':20,'chat-import':21,database:22,readme:23};

// ===== 侧边栏 =====
function normalizeWebUIText(){
  const navIconMap={
    overview:'📊','companion-hub':'◎','system-audit':'◍','eval-console':'E',
    config:'⚙️',persona:'👁',scenes:'🎁',tones:'🎍',plugins:'📝',backups:'🔑',
    modules:'💣',proactive:'📰','growth-goals':'🎆',audio:'🎧',relationship:'📄',
    whitelist:'👃',dimensions:'📻','persona-psychology':'🧠','account-binding':'🔆',
    'mental-health':'🪪','memory-ledger':'📒','chat-import':'🧾',database:'🗄️',readme:'📉'
  };
  document.querySelectorAll('.nav-item[data-page]').forEach(function(item){
    const page=item.dataset.page||'';
    const label=item.querySelector('.label');
    const icon=item.querySelector('.icon');
    if(label && pageNames[page]) label.textContent=pageNames[page];
    if(icon && navIconMap[page]) icon.textContent=navIconMap[page];
  });
  const adv=document.getElementById('advancedNavTitle');
  if(adv) adv.textContent='⟡ 高级配置';
  const breadcrumb=document.getElementById('breadcrumb');
  if(breadcrumb) breadcrumb.textContent='- 系统总览';
  const logoSub=document.querySelector('.logo-sub');
  if(logoSub) logoSub.textContent='黑冠 · BLACK CROWN 战术配置系统';
  const topTitle=document.querySelector('.topbar-title');
  if(topTitle) topTitle.textContent='C.R.O.W.N. // 黑冠';
}

const ADVANCED_PAGE_KEYS=new Set(['system-audit','eval-console','dimensions','persona-psychology','account-binding','mental-health','memory-ledger','chat-import','database']);

function classifyAdvancedNav(){
  const nav=document.getElementById('sidebarNav');
  const title=document.getElementById('advancedNavTitle');
  const group=document.getElementById('advancedNavGroup');
  if(!nav||!title||!group)return;
  const advancedItems=Array.from(nav.querySelectorAll('.nav-item[data-page]')).filter(function(item){
    const page=item.dataset.page||'';
    return item.dataset.complex==='1'||ADVANCED_PAGE_KEYS.has(page);
  });
  advancedItems.sort(function(a,b){
    return (pageIndex[a.dataset.page]??999)-(pageIndex[b.dataset.page]??999);
  });
  advancedItems.forEach(function(item){
    if(item.parentElement!==group)group.appendChild(item);
  });
  const hasItems=group.querySelectorAll('.nav-item[data-page]').length>0;
  title.style.display=hasItems?'block':'none';
  group.style.display=hasItems?'block':'none';
}

function toggleSidebar(){
  const sb=document.getElementById('sidebar');
  sb.classList.toggle('collapsed');
  document.body.classList.toggle('sidebar-collapsed');
}

// ===== 页面切换 =====
function switchPage(page){
  // 数据流粒子效果
  const prevIdx=pageIndex[currentPage]||0;
  const nextIdx=pageIndex[page]||0;
  if(typeof spawnDataParticles==='function'){
    spawnDataParticles(nextIdx>prevIdx?'left':'right');
  }

  document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.page===page));
  document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
  document.getElementById('page-'+page).classList.add('active');

  document.getElementById('breadcrumb').textContent='- '+pageNames[page];
  currentPage=page;
  if(page==='overview') loadStats();
  if(page==='companion-hub') loadCompanionHub();
  if(page==='system-audit') loadSystemAudit();
  if(page==='eval-console') loadEvalConsole();
  if(page==='backups') loadBackups();
  if(page==='plugins') loadPlugins();
  if(page==='scenes'){loadSceneGroups();loadScenes();}
  if(page==='tones'){loadToneGroups();loadTones();}
  if(page==='persona'){
    // 修改为顺序等待加载，避免出现下拉框无选项的问题
    (async function(){
      await loadSceneGroups();
      await loadToneGroups();
      await loadAudioGroups();
      await loadPersonaList();
    })();
  }
    if(page==='readme') loadReadme();
    if(page==='database') loadDBTables();
    if(page==='modules') loadModules();
    if(page==='audio') loadAudioGroups();
    if(page==='growth-goals') loadGrowthGoalsPage();
    if(page==='relationship') loadRelationships();
    if(page==='proactive') loadProactive();
    if(page==='whitelist') loadWhitelist();
  if(page==='dimensions') loadDimensionsPage();
  if(page==='persona-psychology') loadPersonaPsychologyPage();
  if(page==='account-binding') loadAccountBindingPage();
  if(page==='mental-health') loadMentalHealthPage();
  if(page==='memory-ledger') loadMemoryLedgerPage();
  if(page==='chat-import') loadChatImportPage();
  try{showModuleInfo(page);}catch(e){}
}

// ===== 面板折叠 =====
function togglePanel(header){
  const body=header.nextElementSibling;
  const toggle=header.querySelector('.panel-toggle');
  body.classList.toggle('collapsed');
  toggle.classList.toggle('open');
}

// ===== Toast =====
function toast(msg,isError,isWarn){
  const t=document.getElementById('toast');
  t.textContent=msg;
  t.className='toast show'+(isError?' error':(isWarn?' warn':''));
  clearTimeout(t._timer);
  t._timer=setTimeout(()=>t.className='toast',3500);
}

// ===== 模态框 =====
function showModal(title,body,onConfirm){
  document.getElementById('modalTitle').textContent=title;
  document.getElementById('modalBody').innerHTML=body;
  document.getElementById('modalConfirm').onclick=onConfirm;
  document.getElementById('modalOverlay').classList.add('show');
}
function closeModal(){document.getElementById('modalOverlay').classList.remove('show');}

// ===== 按钮涟漪 + 粒子爆发 =====
document.addEventListener('click',function(e){
  const btn=e.target.closest('.btn');
  if(!btn)return;
  // 涟漪
  const r=document.createElement('span');r.className='ripple';
  const rect=btn.getBoundingClientRect();
  r.style.left=(e.clientX-rect.left)+'px';r.style.top=(e.clientY-rect.top)+'px';
  r.style.width=r.style.height=Math.max(rect.width,rect.height)+'px';
  btn.appendChild(r);setTimeout(()=>r.remove(),500);
  // 粒子爆发
  if(typeof spawnButtonBurst==='function'){
    spawnButtonBurst(e.clientX,e.clientY);
  }
});

// ===== Tooltip 字段配置 =====
const CONFIG_TOOLTIPS={
  'llm.api_base':'API 服务端点地址，支持 OpenAI 兼容格式',
  'llm.api_key':'API 认证密钥，请妥善保管',
  'llm.model':'主对话模型名称',
      'llm.temperature':'温度参数，越高越随机 (0.0-2.0)',
  'llm.timeout':'请求超时时间（秒）',
  'tts.enabled':'是否启用语音合成',
  'tts.api_base':'TTS API 端点地址',
  'tts.api_key':'TTS API 认证密钥',
  'tts.model':'TTS 模型名称',
  'tts.reference_audio':'参考音频文件路径（用于声音克隆）',
  'search.api_key':'Tavily 搜索 API 密钥',
  'search.max_results':'单次搜索返回的最大结果数',
};

const PERSONA_TOOLTIPS={
  name:'人设的显示名称',
  color:'人设主题色（十六进制色值）',
  description:'角色的基本身份描述',
  personality:'性格特征概述',
  background:'角色背景故事',
  tone:'整体语气基调',
  verbal_tics:'口头禅列表（用顿号分隔）',
  vocabulary_level:'用词难度等级',
  emoji_usage:'表情使用频率',
  sentence_length:'句子长度偏好',
  core_principles:'说话核心原则',
  rules:'行为规则（每行一条）',
  greeting:'默认打招呼语',
  scope:'知识覆盖范围',
  opinions:'观点列表（格式：话题：立场）',
};

function infoIcon(key,map){
  const tip=(map||CONFIG_TOOLTIPS)[key]||'';
  if(!tip)return '';
  return '<span class="info-icon" title="">i<span class="tip">'+tip+'</span></span>';
}

// ===== 表单渲染 =====
function renderField(label,key,value,type,tooltipMap){
  const tip=infoIcon(key,tooltipMap);
  if(type==='textarea'){
    return '<div class="form-grid"><div class="form-label">'+label+tip+'</div><div><textarea class="form-input" data-key="'+key+'">'+(value||'')+'</textarea></div></div>';
  }
  return '<div class="form-grid"><div class="form-label">'+label+tip+'</div><div><input class="form-input" data-key="'+key+'" value="'+(value!=null?value:'')+'"/></div></div>';
}

function renderFields(containerId,fields,data,prefix,tooltipMap){
  const el=document.getElementById(containerId);
  el.innerHTML=fields.map(f=>{
    const val=f.get?f.get(data):data[f.key];
    return renderField(f.label,prefix+'.'+f.key,val,f.type,tooltipMap);
  }).join('');
}

// ===== Config =====
// ===== 平台预设配置 =====
const PLATFORM_PRESETS={
  mimo:{api_base:'https://token-plan-cn.xiaomimimo.com/v1',model:'mimo-v2.5-pro',light_model:'mimo-v2.5',vlm_model:'mimo-v2.5-vl',tts_model:'mimo-v2.5-tts-voiceclone'},
  qwen:{api_base:'https://dashscope.aliyuncs.com/compatible-mode/v1',model:'qwen-plus',light_model:'qwen-turbo',vlm_model:'qwen-vl-plus'},
  wenxin:{api_base:'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop',model:'ernie-4.0-8k',light_model:'ernie-speed-128k'},
  zhipu:{api_base:'https://open.bigmodel.cn/api/paas/v4',model:'glm-4-plus',light_model:'glm-4-flash',vlm_model:'glm-4v-plus'},
  kimi:{api_base:'https://api.moonshot.cn/v1',model:'moonshot-v1-128k',light_model:'moonshot-v1-8k'},
  deepseek:{api_base:'https://api.deepseek.com/v1',model:'deepseek-chat',light_model:'deepseek-chat'},
  baichuan:{api_base:'https://api.baichuan-ai.com/v1',model:'Baichuan4',light_model:'Baichuan3-Turbo'},
  minimax:{api_base:'https://api.minimax.chat/v1',model:'abab6.5-chat',light_model:'abab5.5-chat'},
  openai:{api_base:'https://api.openai.com/v1',model:'gpt-4o',light_model:'gpt-4o-mini',vlm_model:'gpt-4o'},
  claude:{api_base:'https://api.anthropic.com/v1',model:'claude-sonnet-4-20250514',light_model:'claude-haiku-4-20250414'},
  gemini:{api_base:'https://generativelanguage.googleapis.com/v1beta',model:'gemini-2.0-flash',light_model:'gemini-2.0-flash-lite',vlm_model:'gemini-2.0-flash'},
  mistral:{api_base:'https://api.mistral.ai/v1',model:'mistral-large-latest',light_model:'mistral-small-latest'},
  groq:{api_base:'https://api.groq.com/openai/v1',model:'llama-3.3-70b-versatile',light_model:'llama-3.1-8b-instant'},
};

function applyPlatform(section,val){
  const p=PLATFORM_PRESETS[val];
  if(!p)return;
  const set=(k,v)=>{const el=document.querySelector('[data-key="'+k+'"]');if(el)el.value=v||'';};
  if(section==='llm'){set('config.llm.api_base',p.api_base);set('config.llm.model',p.model);}
  if(section==='light'){set('config.llm.light_model',p.light_model||p.model);}
  if(section==='vlm'){set('config.vlm.api_base',p.api_base);set('config.vlm.model',p.vlm_model||p.model);}
  if(section==='tts'){set('config.tts.api_base',p.api_base);set('config.tts.model',p.tts_model||'');}
  toast('已应用 '+val+' 平台预设');
}

function detectPlatform(apiBase,model,section){
  if(!apiBase)return;
  for(const[key,p] of Object.entries(PLATFORM_PRESETS)){
    if(apiBase===p.api_base){
      if(section==='llm'&&model===p.model)return key;
      if(section==='light'&&(model===p.light_model||model===p.model))return key;
      if(section==='vlm'&&model===(p.vlm_model||p.model))return key;
      if(section==='tts'&&model===p.tts_model)return key;
    }
  }
  return'';
}

async function loadConfig(){
  const res=await fetch('/api/config');
  configData=await res.json();

  renderFields('configLlm',[
    {label:'API Base',key:'api_base'},
    {label:'API Key',key:'api_key'},
    {label:'主模型',key:'model'},
    {label:'最大Token',key:'max_tokens'},
    {label:'Temperature',key:'temperature'},
    {label:'超时(秒)',key:'timeout'},
  ],configData.llm||{},'config.llm',CONFIG_TOOLTIPS);

  renderFields('configLight',[
    {label:'轻量模型',key:'light_model'},
  ],configData.llm||{},'config.llm',CONFIG_TOOLTIPS);

  renderFields('configVlm',[
    {label:'API Base',key:'api_base'},
    {label:'API Key',key:'api_key'},
    {label:'VLM模型',key:'model'},
    {label:'最大Token',key:'max_tokens'},
    {label:'Temperature',key:'temperature'},
    {label:'超时(秒)',key:'timeout'},
  ],configData.vlm||{},'config.vlm',CONFIG_TOOLTIPS);

  renderFields('configTts',[
    {label:'启用 TTS',key:'enabled'},
    {label:'API Base',key:'api_base'},
    {label:'API Key',key:'api_key'},
    {label:'TTS模型',key:'model'},
    {label:'参考音频',key:'reference_audio'},
  ],configData.tts||{},'config.tts',CONFIG_TOOLTIPS);

  renderFields('configSearch',[
    {label:'API Key',key:'api_key'},
    {label:'最大结果数',key:'max_results'},
  ],configData.search||{},'config.search',CONFIG_TOOLTIPS);

  // 自动检测并设置平台预设下拉框
  const llmCfg=configData.llm||{};
  const vlmCfg=configData.vlm||{};
  const ttsCfg=configData.tts||{};
  document.getElementById('llmPlatform').value=detectPlatform(llmCfg.api_base,llmCfg.model,'llm');
  document.getElementById('lightPlatform').value=detectPlatform(llmCfg.api_base,llmCfg.light_model,'light');
  document.getElementById('vlmPlatform').value=detectPlatform(vlmCfg.api_base,vlmCfg.model,'vlm');
  document.getElementById('ttsPlatform').value=detectPlatform(ttsCfg.api_base,ttsCfg.model,'tts');
}

function collectFields(prefix){
  const result={};
  document.querySelectorAll('[data-key^="'+prefix+'."]').forEach(el=>{
    const key=el.dataset.key.replace(prefix+'.','');
    let val=el.value;
    if(val==='true')val=true;
    else if(val==='false')val=false;
    else if(/^\d+$/.test(val))val=parseInt(val);
    else if(/^\d+\.\d+$/.test(val))val=parseFloat(val);
    result[key]=val;
  });
  return result;
}

async function saveConfig(){
  const llm=collectFields('config.llm');
  const vlm=collectFields('config.vlm');
  const tts=collectFields('config.tts');
  const search=collectFields('config.search');
  configData.llm={...(configData.llm||{}),...llm};
  configData.vlm={...(configData.vlm||{}),...vlm};
  configData.tts={...(configData.tts||{}),...tts};
  configData.search={...(configData.search||{}),...search};
  configData.default_persona=configData.default_persona||'Theresa';
  
  const payload = {
    llm: configData.llm,
    vlm: configData.vlm,
    tts: configData.tts,
    search: configData.search,
    default_persona: configData.default_persona
  };
  
  const res=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  const data=await res.json();
  toast(data.msg,!data.ok);
}

// ===== Persona =====// ===== Persona =====
async function loadPersonaList(){
  const res=await fetch('/api/personas');
  const list=await res.json();
  const sel=document.getElementById('personaSelect');
  sel.innerHTML=list.map(n=>'<option value="'+n+'">'+n+'</option>').join('');
  if(list.length){currentPersona=list[0];loadPersona();}
  // 同步主页人设下拉框
  const overviewSel=document.getElementById('overviewPersonaSelect');
  if(overviewSel){
    overviewSel.innerHTML=list.map(n=>'<option value="'+n+'">'+n+'</option>').join('');
    // 读取当前默认人设
    try{
      const cfgRes=await fetch('/api/config');
      const cfg=await cfgRes.json();
      const dp=cfg.default_persona||'Theresa';
      if(list.includes(dp))overviewSel.value=dp;
      document.getElementById('overviewPersonaStatus').textContent='当前: '+dp;
    }catch(e){}
  }
}

async function switchActivePersona(){
  const sel=document.getElementById('overviewPersonaSelect');
  const name=sel.value;
  if(!name){toast('请选择人设',true);return;}
  const res=await fetch('/api/persona/switch_active',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  const data=await res.json();
  toast(data.msg,!data.ok);
  if(data.ok){
    document.getElementById('overviewPersonaStatus').textContent='当前: '+name;
  }
}

// ===== 拖拽导入压缩包 =====
(function(){
  const dz=document.getElementById('importDropZone');
  if(!dz)return;
  dz.addEventListener('dragover',function(e){e.preventDefault();e.stopPropagation();dz.style.borderColor='var(--accent)';dz.style.background='rgba(100,180,255,0.05)';});
  dz.addEventListener('dragleave',function(e){e.preventDefault();e.stopPropagation();dz.style.borderColor='var(--border)';dz.style.background='';});
  dz.addEventListener('drop',function(e){
    e.preventDefault();e.stopPropagation();
    dz.style.borderColor='var(--border)';dz.style.background='';
    const files=e.dataTransfer.files;
    if(files.length)handleImportZip(files);
  });
})();

async function handleImportZip(files){
  const file=files[0];
  if(!file)return;
  const ext=file.name.split('.').pop().toLowerCase();
  if(!['zip','rar','7z'].includes(ext)){toast('仅支持 zip/rar/7z 格式',true);return;}
  toast('正在导入...');
  const fd=new FormData();
  fd.append('file',file);
  try{
    const res=await fetch('/api/persona/import_zip',{method:'POST',body:fd});
    const data=await res.json();
    toast(data.msg,!data.ok);
    if(data.ok){
      // 刷新人设列表
      await loadPersonaList();
      await loadSceneGroups();
      await loadToneGroups();
      await loadAudioGroups();
    }
  }catch(e){
    toast('导入失败: '+e.message,true);
  }
}

async function createNewPersona(){
  const name=prompt('输入新人设名称（英文，用于文件名）：');
  if(!name||!name.trim())return;
  const cleanName=name.trim().replace(/[^a-zA-Z0-9_-]/g,'_');
  if(!cleanName){toast('名称无效',true);return;}
  const res=await fetch('/api/persona/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:cleanName})});
  const data=await res.json();
  if(data.ok){
    toast('人设 '+cleanName+' 已创建');
    await loadPersonaList();
    document.getElementById('personaSelect').value=cleanName;
    loadPersona();
  }else{
    toast(data.msg||'创建失败',true);
  }
}

async function deleteCurrentPersona(){
  if(!currentPersona){toast('请先选择人设',true);return;}
  showConfirm('删除人设','确定要删除人设 '+currentPersona+' 吗？此操作不可恢复！',async function(){
    var res=await fetch('/api/persona/'+currentPersona+'/delete_file',{method:'POST'});
    var data=await res.json();
    toast(data.msg,!data.ok);
    if(data.ok) await loadPersonaList();
  });
}

function deleteScene(id){
  var group=document.getElementById('sceneGroupSelect').value;
  if(!group){toast('请先选择场景组',true);return;}
  showConfirm('删除场景','确定要删除场景 '+id+' 吗？',async function(){
    var res=await fetch('/api/scene_group/'+encodeURIComponent(group)+'/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await res.json();
    toast(data.msg,!data.ok);
    if(data.ok) loadScenes();
  });
}

function deleteTone(id){
  var group=document.getElementById('toneGroupSelect').value;
  if(!group){toast('请先选择语气组',true);return;}
  showConfirm('删除语气','确定要删除语气 '+id+' 吗？',async function(){
    var res=await fetch('/api/tone_group/'+encodeURIComponent(group)+'/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});
    var data=await res.json();
    toast(data.msg,!data.ok);
    if(data.ok) loadTones();
  });
}

function deleteCurrentSceneGroup(){
  var group=document.getElementById('sceneGroupSelect').value;
  if(!group){toast('请先选择场景组',true);return;}
  if(group==='default'){toast('不能删除默认场景组',true);return;}
  showConfirm('删除场景组','确定要删除整个场景组 '+group+' 吗？此操作不可恢复！',async function(){
    var res=await fetch('/api/scene_group/'+encodeURIComponent(group)+'/delete_group',{method:'POST'});
    var data=await res.json();
    toast(data.msg,!data.ok);
    if(data.ok) loadSceneGroups();
  });
}

function deleteCurrentToneGroup(){
  var group=document.getElementById('toneGroupSelect').value;
  if(!group){toast('请先选择语气组',true);return;}
  if(group==='default'){toast('不能删除默认语气组',true);return;}
  showConfirm('删除语气组','确定要删除整个语气组 '+group+' 吗？此操作不可恢复！',async function(){
    var res=await fetch('/api/tone_group/'+encodeURIComponent(group)+'/delete_group',{method:'POST'});
    var data=await res.json();
    toast(data.msg,!data.ok);
    if(data.ok) loadToneGroups();
  });
}

async function loadPersona(){
  currentPersona=document.getElementById('personaSelect').value;
  const res=await fetch('/api/persona/'+currentPersona);
  personaData=await res.json();

  const id=personaData.identity||{};
  renderFields('personaIdentity',[
    {label:'名称',key:'name',get:()=>personaData.name},
    {label:'主题色',key:'color',get:()=>personaData.color},
    {label:'身份描述',key:'description',get:()=>id.description,type:'textarea'},
    {label:'性格特征',key:'personality',get:()=>id.personality,type:'textarea'},
    {label:'背景故事',key:'background',get:()=>id.background,type:'textarea'},
  ],{},'persona',PERSONA_TOOLTIPS);

  const ss=personaData.speaking_style||{};
  renderFields('personaStyle',[
    {label:'语气基调',key:'tone',get:()=>ss.tone},
    {label:'口头禅',key:'verbal_tics',get:()=>(ss.verbal_tics||[]).join('、')},
    {label:'用词等级',key:'vocabulary_level',get:()=>ss.vocabulary_level},
    {label:'表情使用',key:'emoji_usage',get:()=>ss.emoji_usage},
    {label:'句子长度',key:'sentence_length',get:()=>ss.sentence_length},
    {label:'核心原则',key:'core_principles',get:()=>ss.core_principles,type:'textarea'},
  ],{},'persona.style',PERSONA_TOOLTIPS);

  const beh=personaData.behavior||{};
  renderFields('personaBehavior',[
    {label:'行为规则',key:'rules',get:()=>(beh.rules||[]).join('\n'),type:'textarea'},
    {label:'打招呼语',key:'greeting',get:()=>beh.greeting},
  ],{},'persona.behavior',PERSONA_TOOLTIPS);

  const know=personaData.knowledge||{};
  const opinions=(know.opinions||[]).map(o=>o.topic+'：'+o.stance).join('\n');
  renderFields('personaKnowledge',[
    {label:'知识范围',key:'scope',get:()=>know.scope,type:'textarea'},
    {label:'观点列表',key:'opinions',get:()=>opinions,type:'textarea'},
  ],{},'persona.knowledge',PERSONA_TOOLTIPS);

  const exs=(personaData.examples||[]).map(e=>'用户：'+e.user+'\n'+(personaData.name||'AI')+'：'+e.assistant).join('\n---\n');
  document.getElementById('personaExamples').innerHTML=
    '<div class="form-grid"><div class="form-label">对话示例</div><div><textarea class="form-input" data-key="persona.examples" style="min-height:200px">'+exs+'</textarea></div></div>';
  updatePersonaFileTags();
  loadPersonaBindings();
}

async function savePersona(){
  personaData.name=document.querySelector('[data-key="persona.name"]').value;
  personaData.color=document.querySelector('[data-key="persona.color"]').value;
  personaData.identity=personaData.identity||{};
  personaData.identity.description=document.querySelector('[data-key="persona.description"]').value;
  personaData.identity.personality=document.querySelector('[data-key="persona.personality"]').value;
  personaData.identity.background=document.querySelector('[data-key="persona.background"]').value;

  personaData.speaking_style=personaData.speaking_style||{};
  personaData.speaking_style.tone=document.querySelector('[data-key="persona.style.tone"]').value;
  personaData.speaking_style.verbal_tics=document.querySelector('[data-key="persona.style.verbal_tics"]').value.split('、').map(s=>s.trim()).filter(Boolean);
  personaData.speaking_style.vocabulary_level=document.querySelector('[data-key="persona.style.vocabulary_level"]').value;
  personaData.speaking_style.emoji_usage=document.querySelector('[data-key="persona.style.emoji_usage"]').value;
  personaData.speaking_style.sentence_length=document.querySelector('[data-key="persona.style.sentence_length"]').value;
  personaData.speaking_style.core_principles=document.querySelector('[data-key="persona.style.core_principles"]').value;

  personaData.behavior=personaData.behavior||{};
  personaData.behavior.rules=document.querySelector('[data-key="persona.behavior.rules"]').value.split('\n').map(s=>s.trim()).filter(Boolean);
  personaData.behavior.greeting=document.querySelector('[data-key="persona.behavior.greeting"]').value;

  personaData.knowledge=personaData.knowledge||{};
  personaData.knowledge.scope=document.querySelector('[data-key="persona.knowledge.scope"]').value;
  const opLines=document.querySelector('[data-key="persona.knowledge.opinions"]').value.split('\n').filter(Boolean);
  personaData.knowledge.opinions=opLines.map(l=>{
    const [topic,...rest]=l.split('：');
    return {topic:topic?.trim(),stance:rest.join('：').trim()};
  });

  const exText=document.querySelector('[data-key="persona.examples"]').value;
  personaData.examples=exText.split('---').map(block=>{
    const lines=block.trim().split('\n');
    const user=lines.find(l=>l.startsWith('用户：'))?.replace('用户：','')||'';
    const assistant=lines.filter(l=>l.startsWith((personaData.name||'AI')+'：')).map(l=>l.replace((personaData.name||'AI')+'：','')).join('\n');
    return {user,assistant};
  }).filter(e=>e.user);

  const res=await fetch('/api/persona/'+currentPersona,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(personaData)});
  const data=await res.json();
  toast(data.msg,!data.ok);
  
  // 连带保存底部绑定
  savePersonaBindings();
}

// ===== Scenes =====
async function loadScenes(){
  const res=await fetch('/api/scenes');
  scenesData=await res.json();
  const grid=document.getElementById('scenesGrid');
  const scenes=scenesData.scenes||{};
  grid.innerHTML=Object.entries(scenes).map(([id,s])=>`
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div class="card-title">${s.name||id}</div>
        <button class="btn btn-danger" style="font-size:11px;padding:2px 8px;" onclick="deleteScene('${id}')">删除</button>
      </div>
      <div class="card-field"><div class="card-field-label">ID</div><input value="${id}" disabled style="opacity:.4"/></div>
      <div class="card-field"><div class="card-field-label">名称</div><input value="${s.name||''}" data-scene="${id}.name"/></div>
      <div class="card-field"><div class="card-field-label">描述</div><input value="${s.description||''}" data-scene="${id}.description"/></div>
      <div class="card-field"><div class="card-field-label">触发提示</div><input value="${s.trigger_hint||''}" data-scene="${id}.trigger_hint"/></div>
      <div class="card-field"><div class="card-field-label">语气</div><input value="${s.tone||''}" data-scene="${id}.tone"/></div>
      <div class="card-field"><div class="card-field-label">额外提示</div><textarea data-scene="${id}.extra_hint">${s.extra_hint||''}</textarea></div>
    </div>
  `).join('');
}

async function saveScenes(){
  document.querySelectorAll('[data-scene]').forEach(el=>{
    const [id,field]=el.dataset.scene.split('.');
    if(!scenesData.scenes[id])scenesData.scenes[id]={};
    scenesData.scenes[id][field]=el.value;
  });
  const res=await fetch('/api/scenes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(scenesData)});
  const data=await res.json();
  toast(data.msg,!data.ok);
}

// ===== Tones =====
async function loadTones(){
  const res=await fetch('/api/tones');
  tonesData=await res.json();
  const grid=document.getElementById('tonesGrid');
  const tones=tonesData.tones||{};
  grid.innerHTML=Object.entries(tones).map(([id,t])=>`
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div class="card-title">${t.name||id}</div>
        <button class="btn btn-danger" style="font-size:11px;padding:2px 8px;" onclick="deleteTone('${id}')">删除</button>
      </div>
      <div class="card-field"><div class="card-field-label">ID</div><input value="${id}" disabled style="opacity:.4"/></div>
      <div class="card-field"><div class="card-field-label">名称</div><input value="${t.name||''}" data-tone="${id}.name"/></div>
      <div class="card-field"><div class="card-field-label">描述</div><input value="${t.description||''}" data-tone="${id}.description"/></div>
      <div class="card-field"><div class="card-field-label">风格</div><textarea data-tone="${id}.style">${t.style||''}</textarea></div>
      <div class="card-field"><div class="card-field-label">口头禅</div><input value="${(t.verbal_tics||[]).join('、')}" data-tone="${id}.verbal_tics"/></div>
      <div class="card-field"><div class="card-field-label">句式</div><input value="${t.sentence_pattern||''}" data-tone="${id}.sentence_pattern"/></div>
    </div>
  `).join('');
}

async function saveTones(){
  document.querySelectorAll('[data-tone]').forEach(el=>{
    const [id,field]=el.dataset.tone.split('.');
    if(!tonesData.tones[id])tonesData.tones[id]={};
    if(field==='verbal_tics'){
      tonesData.tones[id][field]=el.value.split('、').map(s=>s.trim()).filter(Boolean);
    }else{
      tonesData.tones[id][field]=el.value;
    }
  });
  const res=await fetch('/api/tones',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(tonesData)});
  const data=await res.json();
  toast(data.msg,!data.ok);
}

// ===== Stats =====
async function loadStats(){
  const res=await fetch('/api/stats');
  const s=await res.json();
  document.getElementById('statsGrid').innerHTML=`
    <div class="stat-card"><div class="stat-icon">🗄️</div><div class="stat-value">${(s.db_size/1024).toFixed(0)}KB</div><div class="stat-label">数据库 ${s.active_db?'('+s.active_db+')':''}</div></div>
    <div class="stat-card"><div class="stat-icon">🎤</div><div class="stat-value">${s.voice_count}</div><div class="stat-label">语音数</div></div>
    <div class="stat-card"><div class="stat-icon">😀</div><div class="stat-value">${s.sticker_count}</div><div class="stat-label">表情包</div></div>
    <div class="stat-card"><div class="stat-icon">👤</div><div class="stat-value">${s.persona_count}</div><div class="stat-label">人设数</div></div>
    <div class="stat-card"><div class="stat-icon">🎭</div><div class="stat-value">${s.scenes_count}</div><div class="stat-label">场景数</div></div>
    <div class="stat-card"><div class="stat-icon">🎵</div><div class="stat-value">${s.tones_count}</div><div class="stat-label">语气数</div></div>
    <div class="stat-card"><div class="stat-icon">💾</div><div class="stat-value">${s.backup_count}</div><div class="stat-label">备份数</div></div>
  `;

  // PATH 状态
  try{
    const pRes=await fetch('/api/path/status');
    const pData=await pRes.json();
    document.getElementById('pathStatus').innerHTML=pData.in_path
      ?'<span style="color:var(--cyan)">✓ PATH 已注册</span> — '+pData.project_dir
      :'<span style="color:var(--amber)">✗ 未注册到 PATH</span> — '+pData.project_dir;
  }catch(e){}

  // 系统日志
  const logEl=document.getElementById('systemLog');
  const now=new Date();
  const ts=now.toTimeString().slice(0,8);
  logEl.innerHTML=[
    {t:ts,m:'C.R.O.W.N. 终端初始化完成',c:'ok'},
    {t:ts,m:'加载配置文件...',c:''},
    {t:ts,m:'人设: '+currentPersona,c:''},
    {t:ts,m:'模型: '+(configData.llm?.model||'N/A'),c:''},
    {t:ts,m:'轻量模型: '+(configData.llm?.light_model||'N/A'),c:''},
    {t:ts,m:'TTS: '+(configData.tts?.enabled?'已启用':'已禁用'),c:configData.tts?.enabled?'ok':'warn'},
    {t:ts,m:'场景: '+s.scenes_count+' 已加载',c:''},
    {t:ts,m:'语气: '+s.tones_count+' 已加载',c:''},
    {t:ts,m:'所有系统正常运行',c:'ok'},
  ].map(l=>'<div class="log-line"><span class="log-time">['+l.t+']</span><span class="log-msg '+l.c+'">&gt; '+l.m+'</span></div>').join('');
  logEl.scrollTop=logEl.scrollHeight;
}

// ===== PATH =====
async function registerPath(){
  const res=await fetch('/api/path/register',{method:'POST'});
  const data=await res.json();
  toast(data.msg,!data.ok);
  loadStats();
}

// ===== Plugins =====
function handlePluginDrop(e){
  e.preventDefault();
  document.getElementById('pluginDropZone').style.borderColor='var(--border)';
  document.getElementById('pluginDropZone').style.background='';
  const files=e.dataTransfer.files;
  if(files.length&&files[0].name.endsWith('.zip'))uploadPlugin(files[0]);
  else toast('请拖入 .zip 格式的插件压缩包',true);
}
function handlePluginFileSelect(input){
  if(input.files.length)uploadPlugin(input.files[0]);
  input.value='';
}
async function uploadPlugin(file){
  const formData=new FormData();
  formData.append('file',file);
  toast('正在上传插件...');
  try{
    const res=await fetch('/api/plugin/upload',{method:'POST',body:formData});
    const data=await res.json();
    if(data.ok){toast(data.msg);loadPlugins();}
    else toast(data.msg||'上传失败',true);
  }catch(e){toast('上传失败: '+e.message,true);}
}

async function loadPlugins(){
try{
  const res=await fetch('/api/plugins');
  const plugins=await res.json();
  const list=document.getElementById('pluginsList');
  const empty=document.getElementById('pluginsEmpty');
  if(plugins.length===0){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=plugins.map(p=>`
    <div class="plugin-card">
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <span style="font-family:'JetBrains Mono',monospace;font-size:13px;color:var(--cyan);letter-spacing:1px;">${p.name}</span>
          <span style="font-size:10px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;">v${p.version}</span>
          <span style="font-size:10px;padding:2px 6px;border-radius:2px;background:${p.location==='builtin'?'rgba(0,178,178,0.12)':'rgba(255,207,13,0.12)'};color:${p.location==='builtin'?'var(--cyan)':'var(--amber)'};font-family:'JetBrains Mono',monospace;text-transform:uppercase;">${p.location==='builtin'?'内置':'自定义'}</span>
        </div>
        <div style="font-size:12px;color:var(--text-dim);margin-bottom:4px;">${p.description||'暂无描述'}</div>
        <div style="display:flex;gap:12px;font-size:10px;color:var(--text-dim);font-family:'JetBrains Mono',monospace;text-transform:uppercase;">
          <span>作者: ${p.author||'未知'}</span>
          <span>优先级: ${p.priority}</span>
          <span>触发: ${p.triggers.length?p.triggers.join(', '):'无'}</span>
          <span>前缀: ${p.require_prefix?'需要':'不需要'}</span>
        </div>
        <div style="font-size:10px;color:var(--text-dim);margin-top:2px;opacity:0.5;font-family:'JetBrains Mono',monospace;">${p.path}</div>
      </div>
      <div class="toggle ${p.enabled?'on':''}" onclick="togglePlugin(this,'${p.name}')" title="${p.enabled?'点击禁用':'点击启用'}"></div>
    </div>
  `).join('');
}catch(e){console.error('loadPlugins error:',e);}
}

async function togglePlugin(el,name){
  const enabled=!el.classList.contains('on');
  el.classList.toggle('on');
  const res=await fetch('/api/plugin/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,enabled})});
  const data=await res.json();
  toast(data.msg);
}



// ===== 确认操作 =====
function confirmResetPersona(){
  showModal('⚠ 恢复默认人格','<p>此操作将覆盖 <strong>'+(currentPersona||'Theresa')+'.yaml</strong> 为默认内容。</p><p style="margin-top:8px;color:var(--amber);">当前自定义内容将丢失（备份会自动创建）。</p>',async()=>{
    const res=await fetch('/api/persona/reset',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:currentPersona||'Theresa'})});
    const data=await res.json();
    closeModal();
    toast(data.msg,!data.ok);
    loadPersonaList();
  });
}

function confirmResetConfig(){
  showModal('⚠ 清空所有配置','<p>此操作将重置以下文件为默认值：</p><ul style="margin:8px 0;padding-left:20px;"><li>config.yaml</li><li>scenes.yaml</li><li>tones.yaml</li></ul><p style="color:var(--amber);">备份会自动创建，但当前自定义内容将被覆盖。</p>',async()=>{
    const res=await fetch('/api/config/reset',{method:'POST'});
    const data=await res.json();
    closeModal();
    toast(data.msg,!data.ok);
    loadConfig();loadScenes();loadTones();
  });
}

// ===== 初始化 =====
(async function(){
  normalizeWebUIText();
  classifyAdvancedNav();
  await loadConfig();
  await Promise.all([loadPersonaList(),loadScenes(),loadTones(),loadStats()]);
  // 标题打字机效果
  document.querySelectorAll('.logo-title').forEach(el=>{
    const full=el.textContent;el.textContent='';
    let i=0;
    const timer=setInterval(()=>{
      el.textContent=full.slice(0,++i);
      if(i>=full.length)clearInterval(timer);
    },80);
  });
})();

// ===== 自动关闭：心跳检测 =====
let _hbInterval = setInterval(()=>{
  fetch('/api/heartbeat',{method:'POST'}).catch(()=>{});
}, 5000);
window.addEventListener('beforeunload',()=>{
  clearInterval(_hbInterval);
  navigator.sendBeacon('/api/heartbeat');
});

// ===== 背景自定义 =====
function openBgModal(){
  var m=document.getElementById('bgModal');
  m.classList.add('show');
  loadBgSettings();
}
function closeBgModal(){document.getElementById('bgModal').classList.remove('show');}

function onBgTypeChange(){
  var t=document.getElementById('bgType').value;
  document.getElementById('bgColorGroup').style.display=(t==='color')?'block':'none';
  document.getElementById('bgUrlGroup').style.display=(t==='image'||t==='gif'||t==='video')?'block':'none';
}

function loadBgSettings(){
  try{
    var s=JSON.parse(localStorage.getItem('crown_bg')||'{}');
    if(s.type) document.getElementById('bgType').value=s.type;
    if(s.color) document.getElementById('bgColor').value=s.color;
    if(s.url) document.getElementById('bgUrl').value=s.url;
    if(s.opacity!=null) document.getElementById('bgOpacity').value=s.opacity;
    onBgTypeChange();
    if(s.type&&s.type!=='none') applyBgFromSettings(s);
  }catch(e){}
}

function applyBg(){
  var s={
    type:document.getElementById('bgType').value,
    color:document.getElementById('bgColor').value,
    url:document.getElementById('bgUrl').value,
    opacity:document.getElementById('bgOpacity').value
  };
  localStorage.setItem('crown_bg',JSON.stringify(s));
  applyBgFromSettings(s);
  toast('背景已应用');
  closeBgModal();
}

function applyBgFromSettings(s){
  var wrap=document.getElementById('mainWrap');
  var existing=document.getElementById('crownBgLayer');
  if(existing) existing.remove();
  if(!s.type||s.type==='none') return;
  var opacity=parseFloat(s.opacity)||1;
  if(s.type==='color'){
    document.body.style.background=s.color;
  } else if(s.type==='image'||s.type==='gif'){
    var div=document.createElement('div');
    div.id='crownBgLayer';
    div.style.cssText='position:fixed;inset:0;z-index:0;background-size:cover;background-position:center;background-repeat:no-repeat;opacity:'+opacity+';';
    div.style.backgroundImage='url("'+s.url+'")';
    document.body.prepend(div);
  } else if(s.type==='video'){
    var v=document.createElement('video');
    v.id='crownBgLayer';
    v.style.cssText='position:fixed;inset:0;z-index:0;object-fit:cover;width:100%;height:100%;opacity:'+opacity+';';
    v.src=s.url;v.autoplay=true;v.loop=true;v.muted=true;v.playsInline=true;
    document.body.prepend(v);
  }
}

function resetBg(){
  localStorage.removeItem('crown_bg');
  var existing=document.getElementById('crownBgLayer');
  if(existing) existing.remove();
  document.body.style.background='';
  document.getElementById('bgType').value='none';
  onBgTypeChange();
  toast('背景已重置');
}

// ===== 背景音乐 =====
var bgAudio=null;
function toggleMusicPanel(){
  var p=document.getElementById('musicPanel');
  p.classList.toggle('show');
  event.stopPropagation();
  loadMusicSettings();
}
document.addEventListener('click',function(e){
  var p=document.getElementById('musicPanel');
  if(p.classList.contains('show')&&!p.contains(e.target)&&!e.target.closest('.topbar-badge')){
    p.classList.remove('show');
  }
});

function loadMusicSettings(){
  try{
    var s=JSON.parse(localStorage.getItem('crown_music')||'{}');
    if(s.url) document.getElementById('musicUrl').value=s.url;
    if(s.vol!=null) document.getElementById('musicVol').value=s.vol;
  }catch(e){}
}

function saveMusicSettings(){
  var s={
    url:document.getElementById('musicUrl').value,
    vol:document.getElementById('musicVol').value
  };
  localStorage.setItem('crown_music',JSON.stringify(s));
}

function toggleMusic(){
  var url=document.getElementById('musicUrl').value;
  if(!url){toast('请先输入音乐URL',false,true);return;}
  if(!bgAudio){
    bgAudio=new Audio(url);
    bgAudio.loop=true;
    bgAudio.volume=parseFloat(document.getElementById('musicVol').value);
  }
  if(bgAudio.paused){
    bgAudio.play();
    document.getElementById('musicPlayBtn').textContent='暂停';
  } else {
    bgAudio.pause();
    document.getElementById('musicPlayBtn').textContent='播放';
  }
  saveMusicSettings();
}

function stopMusic(){
  if(bgAudio){bgAudio.pause();bgAudio.currentTime=0;}
  document.getElementById('musicPlayBtn').textContent='播放';
}

function setMusicVol(v){
  if(bgAudio) bgAudio.volume=parseFloat(v);
  saveMusicSettings();
}

// ===== 文件查看 =====
function viewFile(filepath){
  document.getElementById('fileModalTitle').textContent=filepath;
  document.getElementById('fileModalContent').textContent='加载中...';
  document.getElementById('fileModal').classList.add('show');
  fetch('/api/file/'+filepath).then(r=>r.json()).then(data=>{
    if(data.ok){
      document.getElementById('fileModalContent').textContent=data.content;
    } else {
      document.getElementById('fileModalContent').textContent='错误: '+(data.msg||'加载失败');
    }
  }).catch(e=>{
    document.getElementById('fileModalContent').textContent='请求失败: '+e;
  });
}
function closeFileModal(){document.getElementById('fileModal').classList.remove('show');}

// ===== 模块解释弹窗 =====
var MODULE_INFO={
  overview:{title:'系统总览',body:'查看机器人运行状态、统计数据、路径配置。这里是你了解系统全局状态的起点。'},
  config:{title:'模型配置',body:'管理 LLM/TTS/搜索的 API 配置参数。修改后记得保存，重启机器人后生效。'},
  persona:{title:'人设控制',body:'编辑角色人设、说话风格、行为准则。人设决定了机器人如何与用户互动。'},
  scenes:{title:'场景管理',body:'配置不同对话场景的触发条件和语气。场景让机器人在不同情境下有不同的表现。'},
  tones:{title:'语气管理',body:'定义各种语气的说话方式和常用词。语气是场景的具体表达方式。'},
  plugins:{title:'插件控制',body:'管理机器人的外接插件开关。启用/禁用插件后需要重启机器人生效。'},
  backups:{title:'备份管理',body:'查看和管理配置文件的历史备份。每次保存配置都会自动创建备份。'},
    audio:{title:'音频组',body:'管理 TTS 音频样本。可导入干声、创建音频组、绑定到人设。'},
    modules:{title:'模块管理',body:'开关各个功能模块。关闭后该模块在重启后不再生效。基础聊天模块不可关闭。'},
    proactive:{title:'主动消息',body:'配置主动消息的间隔时间、碎碎念配额、深夜静默等参数。'},
    database:{title:'数据库',body:'查看和管理机器人所有数据库表。可以浏览、删除各表数据。'},
    readme:{title:'项目文档',body:'查看项目的 README.md 文档。包含项目说明、使用方法和技术细节。'}
};
function showModuleInfo(page){
  if(!MODULE_INFO[page]) return;
  try{
    var seen=JSON.parse(localStorage.getItem('crown_module_seen')||'{}');
    if(seen[page]) return;
    seen[page]=true;
    localStorage.setItem('crown_module_seen',JSON.stringify(seen));
  }catch(e){return;}
  var info=MODULE_INFO[page];
  var toast=document.getElementById('moduleInfoToast');
  document.getElementById('moduleInfoTitle').textContent=info.title;
  document.getElementById('moduleInfoBody').textContent=info.body;
  toast.style.display='block';
  var timer=document.getElementById('moduleInfoTimer');
  timer.style.width='100%';
  requestAnimationFrame(function(){timer.style.width='0%';});
  clearTimeout(toast._miTimer);
  toast._miTimer=setTimeout(function(){closeModuleInfo();},5000);
}
function closeModuleInfo(){
  document.getElementById('moduleInfoToast').style.display='none';
}

// ===== 人设文件路径标签 =====
function personaFileTag(){
  return 'personas/'+(currentPersona||'Theresa')+'.yaml';
}
// 更新人设文件标签文本
function updatePersonaFileTags(){
  var tags=document.querySelectorAll('.persona-file-tag');
  tags.forEach(function(t){t.textContent=personaFileTag();});
}


function renderMarkdown(md){
  var html=md;
  // 代码块
  html=html.replace(/```(\w*)\n([\s\S]*?)```/g,function(m,lang,code){
    return '<pre><code>'+escapeHtml(code)+'</code></pre>';
  });
  // 行内代码
  html=html.replace(/`([^`]+)`/g,'<code>$1</code>');
  // 标题
  html=html.replace(/^#### (.+)$/gm,'<h4>$1</h4>');
  html=html.replace(/^### (.+)$/gm,'<h3>$1</h3>');
  html=html.replace(/^## (.+)$/gm,'<h2>$1</h2>');
  html=html.replace(/^# (.+)$/gm,'<h1>$1</h1>');
  // 加粗和斜体
  html=html.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');
  html=html.replace(/\*(.+?)\*/g,'<em>$1</em>');
  // 链接
  html=html.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
  // 引用
  html=html.replace(/^> (.+)$/gm,'<blockquote>$1</blockquote>');
  // 无序列表
  html=html.replace(/^[\-\*] (.+)$/gm,'<li>$1</li>');
  html=html.replace(/(<li>.*<\/li>\n?)+/g,'<ul>$&</ul>');
  // 有序列表
  html=html.replace(/^\d+\. (.+)$/gm,'<li>$1</li>');
  // 水平线
  html=html.replace(/^---+$/gm,'<hr style="border:none;border-top:1px solid var(--border);margin:16px 0;">');
  // 段落（双换行）
  html=html.replace(/\n\n/g,'</p><p>');
  html='<p>'+html+'</p>';
  // 单换行
  html=html.replace(/\n/g,'<br>');
  // 清理空段落
  html=html.replace(/<p>\s*<\/p>/g,'');
  html=html.replace(/<p>\s*(<h[1-4]>)/g,'$1');
  html=html.replace(/(<\/h[1-4]>)\s*<\/p>/g,'$1');
  html=html.replace(/<p>\s*(<pre>)/g,'$1');
  html=html.replace(/(<\/pre>)\s*<\/p>/g,'$1');
  html=html.replace(/<p>\s*(<ul>)/g,'$1');
  html=html.replace(/(<\/ul>)\s*<\/p>/g,'$1');
  html=html.replace(/<p>\s*(<blockquote>)/g,'$1');
  html=html.replace(/(<\/blockquote>)\s*<\/p>/g,'$1');
  html=html.replace(/<p>\s*(<hr)/g,'$1');
  return html;
}

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}


function hubSafe(v,fallback='-'){
  if(v===undefined||v===null||v==='')return fallback;
  return escapeHtml(String(v));
}
function hubCount(obj,key){
  return obj&&obj[key]?obj[key]:0;
}
function hubCountLine(obj){
  const keys=Object.keys(obj||{});
  if(!keys.length)return '<span style="color:var(--text-dim);">暂无统计</span>';
  return keys.map(k=>'<span class="file-tag" style="margin-right:6px;">'+hubSafe(k)+': '+hubSafe(obj[k])+'</span>').join('');
}
function hubList(rows,render,emptyText='暂无记录'){
  rows=rows||[];
  if(!rows.length)return '<div style="color:var(--text-dim);font-size:12px;">'+emptyText+'</div>';
  return rows.map(render).join('');
}
function hubJump(page){
  if(document.getElementById('page-'+page))switchPage(page);
  else toast('当前版本没有这个详情页',false,true);
}
async function loadCompanionHub(){
  const user=document.getElementById('hubUserInput')?.value.trim()||'';
  const persona=document.getElementById('hubPersonaInput')?.value.trim()||'';
  const limit=document.getElementById('hubLimitInput')?.value||'5';
  const params=new URLSearchParams({limit});
  if(user)params.set('user_id',user);
  if(persona)params.set('persona',persona);
  const boxes=['hubContextBox','hubSafetyBox','hubMemoryBox','hubGrowthBox','hubProactiveBox','hubAiPsychBox'];
  boxes.forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML='<span style="color:var(--text-dim);">读取中...</span>';});
  try{
    const res=await fetch('/api/companion-hub/summary?'+params.toString());
    const data=await res.json();
    if(!data.ok)throw new Error(data.msg||'读取失败');
    const safety=data.safety||{},memory=data.memory||{},growth=data.growth||{},proactive=data.proactive||{};
    document.getElementById('hubStatsGrid').innerHTML=`
      <div class="stat-card"><div class="stat-icon">◎</div><div class="stat-value">${hubSafe((data.dbs||[]).length)}</div><div class="stat-label">数据源</div></div>
      <div class="stat-card"><div class="stat-icon">!</div><div class="stat-value">${hubSafe(Object.values(safety.counts||{}).reduce((a,b)=>a+b,0))}</div><div class="stat-label">安全状态</div></div>
      <div class="stat-card"><div class="stat-icon">M</div><div class="stat-value">${hubSafe(hubCount(memory.counts,'confirmed'))}</div><div class="stat-label">已确认记忆</div></div>
      <div class="stat-card"><div class="stat-icon">G</div><div class="stat-value">${hubSafe(hubCount(growth.counts,'active'))}</div><div class="stat-label">活跃目标</div></div>
      <div class="stat-card"><div class="stat-icon">P</div><div class="stat-value">${hubSafe(hubCount(proactive.counts,'sent'))}</div><div class="stat-label">已发送主动消息</div></div>
      <div class="stat-card"><div class="stat-icon">S</div><div class="stat-value">${hubSafe(hubCount(proactive.counts,'skipped'))}</div><div class="stat-label">跳过记录</div></div>`;
    const activeRel=data.relationship?.active||{};
    document.getElementById('hubContextBox').innerHTML=`
      <div class="log-line"><span class="log-msg">用户：${hubSafe(data.filters?.user_id,'未筛选')}</span></div>
      <div class="log-line"><span class="log-msg">人设：${hubSafe(data.filters?.persona,'默认')}</span></div>
      <div class="log-line"><span class="log-msg">当前关系：${hubSafe(activeRel.type_id,'暂无')}</span></div>
      <div class="log-line"><span class="log-msg">账号绑定：${hubSafe((data.relationship?.bindings||[]).length)} 条</span></div>
      <div style="margin-top:8px;font-size:11px;color:var(--text-dim);">生成时间：${hubSafe(data.generated_at)}</div>`;
    const latest=safety.latest||{};
    const assess=latest.assessment||{};
    document.getElementById('hubSafetyBox').innerHTML=`
      <div style="margin-bottom:8px;">${hubCountLine(safety.counts)}</div>
      <div class="log-line"><span class="log-msg">最近等级：${hubSafe(latest.risk_level,'暂无')}</span></div>
      <div class="log-line"><span class="log-msg">边界风险：${hubSafe(assess.boundary_risk||assess.boundary||assess.risk,'暂无')}</span></div>
      <div class="log-line"><span class="log-msg">更新时间：${hubSafe(latest.updated_at,'暂无')}</span></div>`;
    document.getElementById('hubMemoryBox').innerHTML=`
      <div style="margin-bottom:8px;">${hubCountLine(memory.counts)}</div>
      ${hubList(memory.recent,function(m){return '<div class="log-line"><span class="log-time">['+hubSafe(m.consent_status)+']</span><span class="log-msg">'+hubSafe(m.content).slice(0,120)+'</span></div>';})}`;
    document.getElementById('hubGrowthBox').innerHTML=`
      <div style="margin-bottom:8px;">${hubCountLine(growth.counts)}</div>
      <div class="log-line"><span class="log-msg">到期跟进：${hubSafe((growth.due||[]).length)} 个</span></div>
      <div class="log-line"><span class="log-msg">高压力目标：${hubSafe((growth.high_pressure||[]).length)} 个</span></div>
      ${hubList(growth.recent,function(g){return '<div class="log-line"><span class="log-time">['+hubSafe(g.status)+']</span><span class="log-msg">'+hubSafe(g.title)+' / 下次：'+hubSafe(g.next_follow_up,'未设置')+'</span></div>';})}`;
    document.getElementById('hubProactiveBox').innerHTML=`
      <div style="margin-bottom:8px;">${hubCountLine(proactive.counts)}</div>
      ${hubList(proactive.recent,function(e){return '<div class="log-line"><span class="log-time">['+hubSafe(e.status)+']</span><span class="log-msg">'+hubSafe(e.trigger_type)+'：'+hubSafe(e.reason||e.extra_context,'无原因记录')+'</span></div>';})}`;
    const ai=data.ai||{},psy=data.psychology?.latest||{};
    document.getElementById('hubAiPsychBox').innerHTML=`
      <div class="log-line"><span class="log-msg">LLM：${hubSafe(ai.llm_model,'未配置')}</span></div>
      <div class="log-line"><span class="log-msg">轻量模型：${hubSafe(ai.light_model,'未配置')}</span></div>
      <div class="log-line"><span class="log-msg">TTS：${ai.tts_enabled?'启用':'未启用'} ${hubSafe(ai.tts_model,'')}</span></div>
      <div class="log-line"><span class="log-msg">VLM：${hubSafe(ai.vlm_model,'未配置')}</span></div>
      <div class="log-line"><span class="log-msg">心理画像：${hubSafe(psy.user_type||psy.mental_state,'暂无')}</span></div>
      <div class="log-line"><span class="log-msg">画像更新时间：${hubSafe(psy.last_analyzed||psy.updated_at,'暂无')}</span></div>`;
  }catch(e){
    boxes.forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML='<span style="color:var(--red);">读取失败：'+hubSafe(e.message)+'</span>';});
    document.getElementById('hubStatsGrid').innerHTML='';
  }
}

function auditStatusText(status){
  const map={ok:'可用',partial:'部分可用',waiting_db:'等待数据',missing_api:'接口缺失',missing_files:'文件缺失'};
  return map[status]||status||'-';
}
function auditStatusColor(status){
  if(status==='ok')return 'var(--green)';
  if(status==='partial'||status==='waiting_db')return 'var(--amber)';
  return 'var(--red)';
}
function auditChips(items,color){
  items=items||[];
  if(!items.length)return '<span style="color:var(--text-dim);">无</span>';
  return items.map(x=>'<span class="file-tag" style="margin-right:6px;color:'+(color||'var(--cyan)')+'">'+hubSafe(x)+'</span>').join('');
}
function auditJump(page){
  if(document.getElementById('page-'+page))switchPage(page);
}
async function loadSystemAudit(){
  ['auditStructureBox','auditModulesBox','auditPagesBox','auditDatabaseBox'].forEach(id=>{
    const el=document.getElementById(id);
    if(el)el.innerHTML='<span style="color:var(--text-dim);">自检中...</span>';
  });
  try{
    const res=await fetch('/api/system-audit');
    const data=await res.json();
    if(!data.ok)throw new Error(data.msg||'自检失败');
    const modules=data.modules||[];
    const pages=data.webui_pages||[];
    const dbs=data.databases||[];
    const okModules=modules.filter(m=>m.status==='ok').length;
    const okPages=pages.filter(p=>p.status==='ok').length;
    const dbTables=Object.keys(data.table_counts||{}).length;
    document.getElementById('auditStatsGrid').innerHTML=`
      <div class="stat-card"><div class="stat-icon">◆</div><div class="stat-value">${hubSafe(okModules)+'/'+hubSafe(modules.length)}</div><div class="stat-label">模块可用</div></div>
      <div class="stat-card"><div class="stat-icon">W</div><div class="stat-value">${hubSafe(okPages)+'/'+hubSafe(pages.length)}</div><div class="stat-label">页面接通</div></div>
      <div class="stat-card"><div class="stat-icon">D</div><div class="stat-value">${hubSafe(dbs.length)}</div><div class="stat-label">数据库文件</div></div>
      <div class="stat-card"><div class="stat-icon">T</div><div class="stat-value">${hubSafe(dbTables)}</div><div class="stat-label">已发现表</div></div>
      <div class="stat-card"><div class="stat-icon">R</div><div class="stat-value">${hubSafe(data.routes_count)}</div><div class="stat-label">接口路由</div></div>
      <div class="stat-card"><div class="stat-icon">C</div><div class="stat-value">${hubSafe(data.generated_at?.slice(11)||'-')}</div><div class="stat-label">检查时间</div></div>`;

    document.getElementById('auditStructureBox').innerHTML=(data.structure||[]).map(s=>`
      <div class="log-line">
        <span class="log-time">[${s.exists?'OK':'MISS'}]</span>
        <span class="log-msg">${hubSafe(s.path)} · 文件 ${hubSafe(s.files)} · Python ${hubSafe(s.python_files)}</span>
      </div>`).join('');

    document.getElementById('auditModulesBox').innerHTML=modules.map(m=>`
      <div class="card" style="margin-bottom:10px;">
        <div class="card-title">${hubSafe(m.name)} <span style="margin-left:auto;color:${auditStatusColor(m.status)}">${auditStatusText(m.status)}</span></div>
        <div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">${hubSafe(m.purpose)}</div>
        <div style="font-size:11px;margin-bottom:6px;">文件：${auditChips((m.files||[]).filter(f=>f.exists).map(f=>f.path))}</div>
        ${(m.files||[]).filter(f=>!f.exists).length?'<div style="font-size:11px;margin-bottom:6px;">缺失文件：'+auditChips((m.files||[]).filter(f=>!f.exists).map(f=>f.path),'var(--red)')+'</div>':''}
        <div style="font-size:11px;">已接表：${auditChips(m.present_tables)}</div>
        ${m.missing_tables&&m.missing_tables.length?'<div style="font-size:11px;margin-top:6px;">待生成表：'+auditChips(m.missing_tables,'var(--amber)')+'</div>':''}
      </div>`).join('');

    const pageRows=pages.map(p=>`
      <tr>
        <td>${hubSafe(p.name)}</td>
        <td>${hubSafe(p.target)}</td>
        <td><span style="color:${auditStatusColor(p.status)};font-weight:600;">${auditStatusText(p.status)}</span></td>
        <td>${auditChips(p.apis)}</td>
        <td>${auditChips(p.present_tables)}${p.missing_tables&&p.missing_tables.length?'<div style="margin-top:5px;color:var(--amber);">待生成：'+hubSafe(p.missing_tables.join(', '))+'</div>':''}</td>
      </tr>`).join('');
    document.getElementById('auditPagesBox').innerHTML=`
      <table class="backup-table"><thead><tr><th>页面</th><th>作用对象</th><th>状态</th><th>接口</th><th>数据库表</th></tr></thead><tbody>${pageRows}</tbody></table>`;

    const dbRows=dbs.map(db=>{
      const tableNames=Object.keys(db.tables||{});
      return `<tr><td>${hubSafe(db.label)}</td><td>${hubSafe(db.path)}</td><td>${db.ok?'可读':'失败'}</td><td>${hubSafe(tableNames.length)}</td><td>${auditChips(tableNames.slice(0,12))}${tableNames.length>12?' <span style="color:var(--text-dim);">等 '+hubSafe(tableNames.length)+' 张</span>':''}</td></tr>`;
    }).join('');
    document.getElementById('auditDatabaseBox').innerHTML=`
      <table class="backup-table"><thead><tr><th>标签</th><th>路径</th><th>状态</th><th>表数</th><th>主要表</th></tr></thead><tbody>${dbRows||'<tr><td colspan="5" style="color:var(--text-dim);">暂无数据库文件</td></tr>'}</tbody></table>
      <div style="font-size:11px;color:var(--text-dim);margin-top:10px;">${hubSafe((data.notes||[]).join(' '))}</div>`;
  }catch(e){
    document.getElementById('auditStatsGrid').innerHTML='';
    ['auditStructureBox','auditModulesBox','auditPagesBox','auditDatabaseBox'].forEach(id=>{
      const el=document.getElementById(id);
      if(el)el.innerHTML='<span style="color:var(--red);">自检失败：'+hubSafe(e.message)+'</span>';
    });
  }
}

// ===== AI 状态栏 =====
async function loadEvalConsole(){
  await loadEvalScenarios();
  await loadEvalReports();
}

async function loadEvalScenarios(){
  const box=document.getElementById('evalScenarioBox');
  if(!box)return;
  box.innerHTML='场景加载中...';
  try{
    const res=await fetch('/api/eval/scenarios');
    const data=await res.json();
    const rows=data.data||[];
    if(!rows.length){
      box.innerHTML='<span style="color:var(--text-dim);">暂无场景</span>';
      return;
    }
    box.innerHTML=rows.map(function(s){
      return '<label style="display:inline-flex;align-items:center;gap:6px;margin-right:12px;margin-bottom:6px;font-size:12px;">'+
        '<input type="checkbox" class="eval-scenario-check" value="'+hubSafe(s.key)+'" checked> '+
        '<span>'+hubSafe(s.name)+'</span>'+
        '</label>';
    }).join('');
  }catch(e){
    box.innerHTML='<span style="color:var(--red);">场景加载失败</span>';
  }
}

function _evalSelectedScenarios(){
  return Array.from(document.querySelectorAll('.eval-scenario-check:checked')).map(function(el){return el.value;});
}

function renderEvalReport(report){
  const summaryBox=document.getElementById('evalSummaryBox');
  const resultsBox=document.getElementById('evalResultsBox');
  if(!summaryBox||!resultsBox)return;
  const s=(report&&report.summary)||{};
  summaryBox.innerHTML=
    '<div style="display:flex;gap:12px;flex-wrap:wrap;">'+
      '<span class="file-tag">分数 '+hubSafe(s.score,0)+'</span>'+
      '<span class="file-tag">通过 '+hubSafe(s.pass,0)+'</span>'+
      '<span class="file-tag">警告 '+hubSafe(s.warn,0)+'</span>'+
      '<span class="file-tag">失败 '+hubSafe(s.fail,0)+'</span>'+
      '<span style="font-size:11px;color:var(--text-dim);">生成时间 '+hubSafe(report.generated_at,'-')+'</span>'+
    '</div>';
  const rows=report.results||[];
  if(!rows.length){
    resultsBox.innerHTML='<div style="color:var(--text-dim);font-size:12px;">暂无结果</div>';
    return;
  }
  resultsBox.innerHTML='<table class="backup-table"><thead><tr><th>场景</th><th>状态</th><th>分数</th><th>说明</th></tr></thead><tbody>'+
    rows.map(function(r){
      const color=r.status==='pass'?'var(--green)':(r.status==='warn'?'var(--amber)':'var(--red)');
      return '<tr><td>'+hubSafe(r.key)+'</td><td style="color:'+color+';font-weight:600;">'+hubSafe(r.status)+'</td><td>'+hubSafe(r.score)+'</td><td>'+hubSafe(r.summary)+'</td></tr>';
    }).join('')+
    '</tbody></table>';
}

async function runEvalSuite(){
  const user=(document.getElementById('evalUserId')?.value||'').trim();
  const persona=(document.getElementById('evalPersona')?.value||'').trim();
  const scenarios=_evalSelectedScenarios();
  toast('评测运行中...');
  try{
    const res=await fetch('/api/eval/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:user,persona:persona,scenarios:scenarios})});
    const data=await res.json();
    if(!data.ok) throw new Error(data.msg||'运行失败');
    renderEvalReport(data);
    await loadEvalReports();
    toast('评测已完成');
  }catch(e){
    toast('评测失败: '+e.message,true);
  }
}

async function loadEvalReports(){
  const box=document.getElementById('evalReportsBox');
  if(!box)return;
  box.innerHTML='<span style="color:var(--text-dim);">读取中...</span>';
  try{
    const res=await fetch('/api/eval/reports');
    const data=await res.json();
    let rows=data.data||[];
    const statusFilter=(document.getElementById('evalHistoryStatus')?.value||'').trim();
    const keyword=(document.getElementById('evalHistoryKeyword')?.value||'').trim().toLowerCase();
    if(statusFilter){
      rows=rows.filter(function(r){
        if(statusFilter==='pass') return Number(r.fail||0)===0 && Number(r.warn||0)===0;
        if(statusFilter==='warn') return Number(r.warn||0)>0 && Number(r.fail||0)===0;
        if(statusFilter==='fail') return Number(r.fail||0)>0;
        return true;
      });
    }
    if(keyword){
      rows=rows.filter(function(r){
        return String(r.report_id||'').toLowerCase().indexOf(keyword)>=0;
      });
    }
    if(!rows.length){
      box.innerHTML='<span style="color:var(--text-dim);">暂无符合筛选条件的历史报告</span>';
      return;
    }
    box.innerHTML=rows.map(function(r){
      return '<div class="log-line" style="justify-content:space-between;">'+
        '<span class="log-msg">['+hubSafe(r.report_id)+'] 分数 '+hubSafe(r.score)+' / 通过 '+hubSafe(r.pass)+' 警告 '+hubSafe(r.warn)+' 失败 '+hubSafe(r.fail)+'</span>'+
        '<button class="btn" style="padding:2px 8px;font-size:11px;" onclick="loadEvalReportDetail(\''+hubSafe(r.report_id)+'\')">查看</button>'+
      '</div>';
    }).join('');
  }catch(e){
    box.innerHTML='<span style="color:var(--red);">历史读取失败</span>';
  }
}

async function loadEvalReportDetail(reportId){
  try{
    const res=await fetch('/api/eval/report/'+encodeURIComponent(reportId));
    const data=await res.json();
    if(!data.ok) throw new Error(data.msg||'读取失败');
    renderEvalReport(data.data||{});
  }catch(e){
    toast('报告读取失败: '+e.message,true);
  }
}

async function loadAIStatus(){
  try{
    const res=await fetch('/api/ai/status');
    const s=await res.json();
    document.getElementById('aiMood').textContent=s.emotion.dominant||'平静';
    document.getElementById('aiLevel').textContent=s.growth.level_name||'好友';
    document.getElementById('aiMsg').textContent=s.growth.messages||0;

    // 状态面板
    var panel=document.getElementById('aiStatusPanel');
    if(panel){
      var moodColor=s.emotion.mood_value>0.3?'var(--amber)':(s.emotion.mood_value<-0.3?'var(--red)':'var(--text)');
      panel.innerHTML=
        '<div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--border);">' +
          '<div style="font-size:10px;color:var(--text-dim);font-family:JetBrains Mono,monospace;letter-spacing:1px;">情绪</div>' +
          '<div style="font-size:20px;color:'+moodColor+';margin-top:4px;">'+(s.emotion.dominant||'平静')+'</div>' +
          '<div style="font-size:11px;color:var(--text-dim);">值: '+(s.emotion.mood_value||0).toFixed(2)+' 连续: '+(s.emotion.streak||0)+'</div>' +
        '</div>' +
        '<div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--border);">' +
          '<div style="font-size:10px;color:var(--text-dim);font-family:JetBrains Mono,monospace;letter-spacing:1px;">关系</div>' +
          '<div style="font-size:20px;color:var(--amber);margin-top:4px;">'+(s.growth.level_name||'好友')+'</div>' +
          '<div style="font-size:11px;color:var(--text-dim);">Lv.'+(s.growth.level||5)+' EXP:'+(s.growth.exp||0)+' 共鸣:'+(s.growth.bonds||0)+'</div>' +
        '</div>' +
        '<div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--border);">' +
          '<div style="font-size:10px;color:var(--text-dim);font-family:JetBrains Mono,monospace;letter-spacing:1px;">对话</div>' +
          '<div style="font-size:20px;color:var(--amber);margin-top:4px;">'+(s.growth.messages||0)+'</div>' +
          '<div style="font-size:11px;color:var(--text-dim);">认识 '+(s.growth.days||0)+' 天 经历:'+(s.growth.shared||0)+'</div>' +
        '</div>' +
        '<div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--border);">' +
          '<div style="font-size:10px;color:var(--text-dim);font-family:JetBrains Mono,monospace;letter-spacing:1px;">状态</div>' +
          '<div style="font-size:16px;margin-top:4px;">恋人: '+(s.lover_mode?'<span style="color:var(--red);">ON</span>':'<span style="color:var(--text-dim);">OFF</span>')+'</div>' +
          '<div style="font-size:11px;color:var(--text-dim);">人设: '+(s.persona||'N/A')+'</div>' +
        '</div>' +
        '<div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--border);">' +
          '<div style="font-size:10px;color:var(--text-dim);font-family:JetBrains Mono,monospace;letter-spacing:1px;">情绪趋势</div>' +
          '<div style="font-size:14px;margin-top:4px;color:var(--amber);">'+(s.recent_moods?s.recent_moods.join(' → '):'--')+'</div>' +
          '<div style="font-size:11px;color:var(--text-dim);">话题: '+(s.recent_topics?s.recent_topics.join(' '):'--')+'</div>' +
        '</div>' +
        '<div style="padding:12px;background:rgba(0,0,0,0.3);border:1px solid var(--border);">' +
          '<div style="font-size:10px;color:var(--text-dim);font-family:JetBrains Mono,monospace;letter-spacing:1px;">模型</div>' +
          '<div style="font-size:12px;margin-top:4px;color:var(--amber);">'+(s.llm_model||'N/A')+'</div>' +
          '<div style="font-size:11px;color:var(--text-dim);">TTS: '+(s.tts_model||'N/A')+'</div>' +
        '</div>';
    }
  }catch(e){}
}

// ===== 清空数据库 =====
function clearAllDB(){
  showConfirm(
    '⚠ 清空全部数据库',
    '此操作将永久删除：\n\n- 所有聊天记录\n- 用户画像和亲密度\n- 长期记忆和情绪状态\n- 语音文件和表情包缓存\n- 生活事件和成长记忆\n\n此操作不可恢复！确定要继续吗？',
    async function(){
      var res=await fetch('/api/db/clear',{method:'POST'});
      var data=await res.json();
      toast(data.msg);
      loadStats();
      loadAIStatus();
    }
  );
}

// ===== 重启文明 =====
async function restartBot(){
  toast('重启文明启动中...');
  var res=await fetch('/api/bot/restart',{method:'POST'});
  var data=await res.json();
  toast(data.msg);
}

// ===== 重启 WebUI =====
function restartWebUI(){
  showConfirm(
    '重启 WebUI',
    'WebUI 服务将重启，页面会短暂断开。确定继续吗？',
    async function(){
      toast('WebUI 正在重启...');
      await fetch('/api/webui/restart',{method:'POST'});
      setTimeout(function(){location.reload();},3000);
    }
  );
}

// ===== 刷新全部配置 =====
async function refreshAll(){
  toast('正在刷新...');
  await loadConfig();
  await loadPersonaList();
  await loadScenes();
  await loadTones();
  await loadPlugins();
  await loadBackups();
  await loadStats();
  await loadAIStatus();
  if(typeof loadReadme==='function') await loadReadme();
  toast('刷新完成');
}

// ===== 确认弹窗 =====
var _confirmCallback=null;
function showConfirm(title,text,onConfirm,viewOnly){
  document.getElementById('confirmTitle').textContent=title;
  document.getElementById('confirmText').innerHTML=text.replace(/\n/g,'<br>');
  document.getElementById('confirmOverlay').classList.add('show');
  _confirmCallback=onConfirm;
  var okBtn=document.getElementById('confirmOk');
  if(viewOnly){
    okBtn.textContent='关闭';
    okBtn.onclick=function(){closeConfirm();};
  }else{
    okBtn.textContent='确认';
    okBtn.onclick=function(){
      var cb=_confirmCallback;
      closeConfirm();
      if(cb) cb();
    };
  }
}
function closeConfirm(){
  document.getElementById('confirmOverlay').classList.remove('show');
  _confirmCallback=null;
}

// 页面加载时获取 AI 状态
loadAIStatus();
setInterval(loadAIStatus,30000);


// ===== 备份管理 =====
// ===== 备份管理 =====
async function loadBackups(){
  var res=await fetch('/api/backups');
  var backups=await res.json();
  var body=document.getElementById('backupBody');
  var empty=document.getElementById('backupEmpty');
  var countEl=document.getElementById('backupCount');
  if(countEl) countEl.textContent=backups.length;
  if(backups.length===0){body.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  // 按时间戳分组
  var groups={};
  backups.forEach(function(b){
    var ts=b.name.replace(/^[^_]+_/,'').replace(/\.yaml$/,'');
    if(!groups[ts])groups[ts]=[];
    groups[ts].push(b);
  });
  var h='';
  Object.keys(groups).sort().reverse().forEach(function(ts){
    var files=groups[ts];
    var types=files.map(function(f){return f.name.split('_')[0];}).join('+');
    h+='<tr style="background:var(--bg-panel-hover);"><td colspan="4" style="padding:8px 12px;">';
    h+='<b>'+ts+'</b> ('+types+') ';
    h+='<button class="btn btn-primary" style="padding:4px 10px;font-size:11px;margin-left:8px;" onclick="restoreAllBackup(\''+ts+'\')">一键恢复全部</button> ';
    h+='<button class="btn btn-danger" style="padding:4px 10px;font-size:11px;" onclick="deleteBackupSet(\''+ts+'\')">删除组</button>';
    h+='</td></tr>';
    files.forEach(function(b){
      h+='<tr><td style="padding-left:24px;">'+b.name+'</td><td>'+(b.size/1024).toFixed(1)+'KB</td><td>'+b.time+'</td>';
      h+='<td><button class="btn" style="padding:4px 10px;font-size:11px;" onclick="viewBackupContent(\''+b.name+'\')">查看</button> ';
      h+='<button class="btn" style="padding:4px 10px;font-size:11px;" onclick="importBackup(\''+b.name+'\')">恢复单个</button></td></tr>';
    });
  });
  body.innerHTML=h;
}

async function generateBackup(){
  toast('正在创建备份...');
  var res=await fetch('/api/backup/generate',{method:'POST'});
  var data=await res.json();
  toast(data.msg);
  loadBackups();
}

async function deleteBackup(name){
  showConfirm('删除备份','确定要删除备份文件 '+name+' 吗？',async function(){
    var res=await fetch('/api/backup/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
    var data=await res.json();
    toast(data.msg);
    loadBackups();
  });
}

async function clearAllBackups(){
  showConfirm('清除所有备份','确定要删除所有本地备份文件吗？此操作不可恢复！',async function(){
    var res=await fetch('/api/backup/clear_all',{method:'POST'});
    var data=await res.json();
    toast(data.msg);
    loadBackups();
  });
}

async function viewBackupContent(name){
  try{
    var res=await fetch('/api/backup/view/'+encodeURIComponent(name));
    var data=await res.json();
    if(data.error){toast(data.error);return;}
    var content=data.content||'';
    var display=content.length>5000?content.substring(0,5000)+'\n\n... (内容过长，已截断)':content;
    var html='<div style="max-height:60vh;overflow:auto;"><pre style="font-family:JetBrains Mono,monospace;font-size:11px;line-height:1.6;white-space:pre-wrap;word-break:break-all;color:var(--text);background:var(--bg-deep);padding:12px;border-radius:6px;">'+
      display.replace(/</g,'&lt;').replace(/>/g,'&gt;')+'</pre></div>';
    showConfirm('备份内容 - '+name+' ('+((data.size||0)/1024).toFixed(1)+'KB)', html, null, true);
  }catch(e){toast('加载失败: '+e);}
}

function importBackupPrompt(){
  document.getElementById('importFileInput').click();
}

async function handleImportFile(input){
  if(!input.files.length)return;
  var file=input.files[0];
  var text=await file.text();
  var res=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json'},body:text});
  var data=await res.json();
  toast('已导入配置: '+file.name);
  loadConfig();
  input.value='';
}

async function importBackup(name){
  showConfirm('恢复配置','确定要用备份 '+name+' 覆盖当前配置吗？',async function(){
    var res=await fetch('/api/backup/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
    var data=await res.json();
    toast(data.msg);
    _reloadAfterRestore();
  });
}

async function restoreAllBackup(ts){
  showConfirm('一键恢复','确定要恢复时间戳 '+ts+' 的所有备份文件吗？这会覆盖当前的配置、场景、语气和人设。',async function(){
    var res=await fetch('/api/backup/restore_all',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({timestamp:ts})});
    var data=await res.json();
    toast(data.msg);
    _reloadAfterRestore();
  });
}

async function deleteBackupSet(ts){
  showConfirm('删除备份组','确定要删除时间戳 '+ts+' 的所有备份文件吗？',async function(){
    var res=await fetch('/api/backups');
    var backups=await res.json();
    var toDelete=backups.filter(function(b){return b.name.indexOf(ts)>=0;});
    for(var i=0;i<toDelete.length;i++){
      await fetch('/api/backup/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:toDelete[i].name})});
    }
    toast('已删除 '+toDelete.length+' 个文件');
    loadBackups();
  });
}

async function _reloadAfterRestore(){
  // 恢复后重新加载所有相关数据
  try{await loadConfig();}catch(e){}
  try{await loadPersonas();}catch(e){}
  try{await loadScenes();}catch(e){}
  try{await loadTones();}catch(e){}
  try{await loadSceneGroups();}catch(e){}
  try{await loadToneGroups();}catch(e){}
  try{await loadAudioGroups();}catch(e){}
  toast('所有配置已重新加载');
}

// ===== 数据库管理 =====
var _currentTable='';
var _currentDBData=null;
var _dbTableMeta={};
var _dbAutoRefreshTimer=null;
var _selectedUserId='';

async function loadDBTableMeta(){
  try{
    var res=await fetch('/api/db/table_meta');
    _dbTableMeta=await res.json();
  }catch(e){}
}

async function loadDBUsers(){
  try{
    var res=await fetch('/api/db/users');
    var data=await res.json();
    var sel=document.getElementById('dbUserSelect');
    if(!sel)return;
    var opts='<option value="">-- 全部数据 --</option>';
    if(data.users){
      data.users.forEach(function(u){
        var label=(u.nickname||u.user_id)+' ('+u.total_messages+'条)';
        opts+='<option value="'+u.user_id+'">'+label+'</option>';
      });
    }
    sel.innerHTML=opts;
    if(_selectedUserId) sel.value=_selectedUserId;
  }catch(e){}
}

function onDBUserChange(userId){
  _selectedUserId=userId;
  var info=document.getElementById('dbUserInfo');
  if(userId){
    info.textContent='当前查看: '+userId;
    loadUserDBData(userId);
  }else{
    info.textContent='';
    loadDBTables();
  }
}

async function loadUserDBData(userId){
  var res=await fetch('/api/db/user_data/'+encodeURIComponent(userId));
  var data=await res.json();
  if(data.error){toast(data.error);return;}
  var userData=data.data||{};
  var list=document.getElementById('dbTableList');
  var tables=Object.keys(userData);
  if(tables.length===0){
    list.innerHTML='<div style="color:var(--text-dim);font-size:13px;">该用户暂无数据</div>';
    document.getElementById('dbDataPanel').style.display='none';
    return;
  }
  await loadDBTableMeta();
  list.innerHTML=tables.map(function(t){
    var meta=_dbTableMeta[t]||{};
    var tooltip=meta.cn?' title="'+meta.cn+' - '+meta.desc+'"':'';
    return '<button class="btn" style="padding:6px 14px;font-size:11px;"'+tooltip+' onclick="loadUserTableData(\''+t+'\',\''+userId+'\')">'+
      (meta.cn||t)+' <span style="color:var(--text-dim);">('+userData[t].total+')</span></button>';
  }).join('');
  if(tables.length>0) loadUserTableData(tables[0], userId);
}

async function loadUserTableData(tableName, userId){
  _currentTable=tableName;
  _selectedUserId=userId;
  var res=await fetch('/api/db/user_data/'+encodeURIComponent(userId));
  var data=await res.json();
  if(data.error){toast(data.error);return;}
  var tableData=(data.data||{})[tableName];
  if(!tableData){toast('无数据');return;}
  _currentDBData=tableData.rows||[];
  var meta=_dbTableMeta[tableName]||{};
  document.getElementById('dbTableName').textContent=(meta.cn||tableName)+' ('+tableData.total+' rows)';
  document.getElementById('dbDataPanel').style.display='block';
  document.getElementById('dbDataEmpty').style.display=_currentDBData.length===0?'block':'none';
  renderDBTable(tableData.columns||[], _currentDBData);
}

async function loadDBTables(){
  await loadDBTableMeta();
  await loadDBUsers();
  var res=await fetch('/api/db/tables');
  var data=await res.json();
  var list=document.getElementById('dbTableList');
  if(!data.tables||data.tables.length===0){
    list.innerHTML='<div style="color:var(--text-dim);font-size:13px;">暂无数据表</div>';
    return;
  }
  list.innerHTML=data.tables.map(function(t){
    var meta=_dbTableMeta[t.name]||{};
    var tooltip=meta.cn?' title="'+meta.cn+' - '+meta.desc+'"':'';
    return '<button class="btn" style="padding:6px 14px;font-size:11px;"'+tooltip+' onclick="loadDBTable(\''+t.name+'\')">'+
      (meta.cn||t.name)+' <span style="color:var(--text-dim);">('+t.count+')</span></button>';
  }).join('');
}

async function loadDBTable(name){
  _currentTable=name;
  _selectedUserId='';
  var res=await fetch('/api/db/table/'+encodeURIComponent(name));
  var data=await res.json();
  if(data.error){toast(data.error);return;}
  _currentDBData=data.rows||[];
  var meta=_dbTableMeta[name]||{};
  document.getElementById('dbTableName').textContent=(meta.cn||name)+' ('+data.total+' rows)';
  document.getElementById('dbDataPanel').style.display='block';
  document.getElementById('dbDataEmpty').style.display=_currentDBData.length===0?'block':'none';
  renderDBTable(data.columns||[], _currentDBData);
}

function renderDBTable(cols, rows){
  var head=document.getElementById('dbDataHead');
  head.innerHTML='<tr><th>ROWID</th>'+cols.map(function(c){
    return '<th>'+c+'</th>';
  }).join('')+'<th>操作</th></tr>';

  var body=document.getElementById('dbDataBody');
  body.innerHTML=rows.map(function(r){
    var rowId=(r.ROWID!==undefined&&r.ROWID!==null)?r.ROWID:((r.rowid!==undefined&&r.rowid!==null)?r.rowid:(r._rowid||''));
    var rowIdArg=String(rowId).replace(/\\/g,'\\\\').replace(/'/g,"\\'");
    var cells=cols.map(function(c){
      var val=r[c];
      if(val===null||val===undefined) val='<span style="color:var(--text-dim);">NULL</span>';
      else if(typeof val==='string'&&val.length>40) val=val.substring(0,40)+'...';
      return '<td>'+val+'</td>';
    }).join('');
    return '<tr>'+('<td style="color:var(--text-dim);font-size:11px;">'+rowId+'</td>')+cells+
      '<td><button class="btn" style="padding:2px 8px;font-size:10px;margin-right:2px;" onclick="viewDBRow(\''+rowIdArg+'\')">查看</button>'+
      '<button class="btn" style="padding:2px 8px;font-size:10px;margin-right:2px;" onclick="editDBRow(\''+rowIdArg+'\')">编辑</button>'+
      '<button class="btn btn-danger" style="padding:2px 8px;font-size:10px;" onclick="deleteDBRow(\''+rowIdArg+'\')">删除</button></td></tr>';
  }).join('');
}

async function viewDBRow(rowId){
  if(!_currentDBData||!_currentTable)return;
  var row=_currentDBData.find(function(r){return String((r.ROWID!==undefined&&r.ROWID!==null)?r.ROWID:r.rowid)===String(rowId);});
  if(!row)return;
  var meta=_dbTableMeta[_currentTable]||{};
  var html='<div style="font-family:JetBrains Mono,monospace;font-size:12px;line-height:1.8;">';
  if(meta.cn) html+='<div style="margin-bottom:8px;color:var(--amber);font-size:13px;">'+meta.cn+' - '+meta.desc+'</div>';
  Object.keys(row).forEach(function(k){
    var val=row[k];
    if(val===null||val===undefined) val='<span style="color:var(--text-dim);">NULL</span>';
    html+='<div style="margin-bottom:4px;"><span style="color:var(--text-dim);">'+k+':</span> <span style="color:var(--amber);">'+val+'</span></div>';
  });
  html+='</div>';
  showConfirm('ROWID '+rowId+' - '+(meta.cn||_currentTable), html, null, true);
}

async function editDBRow(rowId){
  if(!_currentDBData||!_currentTable)return;
  var row=_currentDBData.find(function(r){return String((r.ROWID!==undefined&&r.ROWID!==null)?r.ROWID:r.rowid)===String(rowId);});
  if(!row)return;
  var res=await fetch('/api/db/schema/'+encodeURIComponent(_currentTable));
  var schema=await res.json();
  var cols=schema.columns||[];
  var html='<div style="font-size:12px;max-height:60vh;overflow:auto;">';
  html+='<div style="margin-bottom:12px;color:var(--text-dim);">编辑 '+_currentTable+' ROWID='+rowId+'</div>';
  html+='<form id="editRowForm">';
  cols.forEach(function(c){
    if(c.pk) return;
    var val=row[c.name];
    if(val===null||val===undefined) val='';
    html+='<div style="margin-bottom:8px;">';
    html+='<label style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:2px;">'+c.name+' <span style="color:var(--text-dim);">('+c.type+')</span></label>';
    html+='<input type="text" name="'+c.name+'" value="'+String(val).replace(/"/g,'&quot;')+'" style="width:100%;padding:4px 8px;background:var(--bg-deep);border:1px solid var(--border);color:var(--text);border-radius:4px;font-size:12px;">';
    html+='</div>';
  });
  html+='</form></div>';
  showConfirm('编辑数据', html, async function(){
    var form=document.getElementById('editRowForm');
    var inputs=form.querySelectorAll('input');
    var updates={};
    inputs.forEach(function(inp){
      var orig=row[inp.name];
      var newVal=inp.value;
      if(String(orig)!==newVal) updates[inp.name]=newVal;
    });
    if(Object.keys(updates).length===0){toast('无变更');return;}
    var r2=await fetch('/api/db/edit_row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({table:_currentTable,id:rowId,data:updates})});
    var d2=await r2.json();
    toast(d2.msg);
    if(d2.ok){
      if(_selectedUserId) loadUserTableData(_currentTable,_selectedUserId);
      else loadDBTable(_currentTable);
    }
  });
}

function showAddRowForm(){
  if(!_currentTable){toast('请先选择表');return;}
  fetch('/api/db/schema/'+encodeURIComponent(_currentTable))
    .then(function(r){return r.json();})
    .then(function(schema){
      var cols=schema.columns||[];
      var meta=_dbTableMeta[_currentTable]||{};
      var html='<div style="font-size:12px;max-height:60vh;overflow:auto;">';
      html+='<div style="margin-bottom:12px;color:var(--text-dim);">向 '+(meta.cn||_currentTable)+' 添加新数据</div>';
      html+='<form id="addRowForm">';
      cols.forEach(function(c){
        var defaultVal=c.default||'';
        if(defaultVal==='CURRENT_TIMESTAMP') defaultVal=new Date().toISOString().replace('T',' ').substring(0,19);
        html+='<div style="margin-bottom:8px;">';
        html+='<label style="font-size:11px;color:var(--text-dim);display:block;margin-bottom:2px;">'+c.name+' <span style="color:var(--text-dim);">('+c.type+(c.pk?', PK':'')+(c.notnull?', NOT NULL':'')+')</span></label>';
        html+='<input type="text" name="'+c.name+'" value="'+String(defaultVal).replace(/"/g,'&quot;')+'" style="width:100%;padding:4px 8px;background:var(--bg-deep);border:1px solid var(--border);color:var(--text);border-radius:4px;font-size:12px;">';
        html+='</div>';
      });
      html+='</form></div>';
      showConfirm('新增数据', html, async function(){
        var form=document.getElementById('addRowForm');
        var inputs=form.querySelectorAll('input');
        var newData={};
        inputs.forEach(function(inp){
          if(inp.value!=='') newData[inp.name]=inp.value;
        });
        if(Object.keys(newData).length===0){toast('请填写数据');return;}
        var r2=await fetch('/api/db/add_row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({table:_currentTable,data:newData})});
        var d2=await r2.json();
        toast(d2.msg);
        if(d2.ok){
          if(_selectedUserId) loadUserTableData(_currentTable,_selectedUserId);
          else loadDBTable(_currentTable);
          loadDBTables();
        }
      });
    });
}

async function deleteDBRow(rowId){
  if(!_currentTable)return;
  showConfirm('删除数据','确定要删除 '+_currentTable+' 表中 ROWID='+rowId+' 的数据吗？',async function(){
    var row=_currentDBData?_currentDBData.find(function(r){return String((r.ROWID!==undefined&&r.ROWID!==null)?r.ROWID:r.rowid)===String(rowId);}):null;
    var payload={table:_currentTable,id:rowId};
    if(_selectedUserId) payload.user_id=_selectedUserId;
    if(row&&row._persona) payload.persona=row._persona;
    var res=await fetch('/api/db/delete_row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    var data=await res.json();
    toast(data.msg);
    if(data.ok){
      if(_selectedUserId) loadUserTableData(_currentTable,_selectedUserId);
      else loadDBTable(_currentTable);
      loadDBTables();
    }
  });
}

function setDBAutoRefresh(seconds){
  if(_dbAutoRefreshTimer){clearInterval(_dbAutoRefreshTimer);_dbAutoRefreshTimer=null;}
  var status=document.getElementById('dbAutoRefreshStatus');
  if(parseInt(seconds)<=0){
    if(status) status.textContent='自动刷新: 关闭';
    return;
  }
  if(status) status.textContent='自动刷新: '+seconds+'秒';
  _dbAutoRefreshTimer=setInterval(function(){
    if(_currentTable){
      if(_selectedUserId) loadUserTableData(_currentTable,_selectedUserId);
      else loadDBTable(_currentTable);
    }
  }, parseInt(seconds)*1000);
}

// ===== 修复 loadReadme =====
async function loadReadme(){
  var el=document.getElementById('readmeContent');
  try{
    var res=await fetch('/api/readme');
    var data=await res.json();
    if(!data.content||data.content==='README.md 未找到'){
      el.innerHTML='<div style="color:var(--text-dim);">README.md 未找到</div>';
      return;
    }
    el.innerHTML=renderMarkdown(data.content);
  }catch(e){
    el.innerHTML='<div style="color:var(--red);">加载失败: '+e+'</div>';
  }
}

function renderMarkdown(md){
  var html=md
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/^### (.+)$/gm,'<h3>$1</h3>')
    .replace(/^## (.+)$/gm,'<h2>$1</h2>')
    .replace(/^# (.+)$/gm,'<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,'<em>$1</em>')
    .replace(/`([^`]+)`/g,'<code>$1</code>')
    .replace(/^- (.+)$/gm,'<li>$1</li>')
    .replace(/(<li>.*<\/li>)/s,'<ul>$1</ul>')
    .replace(/\n\n/g,'</p><p>')
    .replace(/\n/g,'<br>');
  return '<div style="text-align:left;line-height:1.8;">'+html+'</div>';
}


// ===== 模块管理 =====
async function loadModules(){
try{
  var res=await fetch('/api/modules');
  var modules=await res.json();
  var grid=document.getElementById('modulesGrid');
  var html='';
  Object.keys(modules).forEach(function(k){
    var m=modules[k];
    var toggled=m.enabled?'on':'';
    html+='<div style="padding:16px;background:rgba(0,0,0,0.3);border:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;">'+
      '<div>'+
        '<div style="font-family:JetBrains Mono,monospace;font-size:13px;color:var(--amber);">'+m.name+'</div>'+
        '<div style="font-size:11px;color:var(--text-dim);margin-top:4px;">'+m.desc+'</div>'+
        '<div style="font-size:10px;color:var(--text-dim);margin-top:2px;opacity:0.5;">'+k+'</div>'+
      '</div>'+
      '<div class="toggle '+toggled+'" onclick="toggleModule(this,\''+k+'\')" title="'+(m.enabled?'点击禁用':'点击启用')+'"></div>'+
    '</div>';
  });
  grid.innerHTML=html;
}catch(e){console.error('loadModules error:',e);}
}

async function toggleModule(el,name){
  var enabled=!el.classList.contains('on');
  el.classList.toggle('on');
  var res=await fetch('/api/modules/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name,enabled:enabled})});
  var data=await res.json();
  toast(data.msg);
}

// ===== 主动消息配置 =====
var _proactiveData={};
async function loadProactive(){
  var res=await fetch('/api/proactive');
  _proactiveData=await res.json();
  var form=document.getElementById('proactiveForm');
  var fields=[
    {key:'interval_hours',label:'主动消息间隔（小时）',type:'number',hint:'每隔多久主动发一条消息'},
    {key:'boot_cooldown_minutes',label:'开机保护（分钟）',type:'number',hint:'启动后多久开始发主动消息'},
    {key:'quiet_hours_start',label:'静默开始（小时）',type:'number',hint:'几点开始不发消息（0-23）'},
    {key:'quiet_hours_end',label:'静默结束（小时）',type:'number',hint:'几点恢复发消息（0-23）'},
    {key:'mutter_enabled',label:'碎碎念',type:'toggle',hint:'是否启用碎碎念功能'},
    {key:'mutter_max_per_slot',label:'每时段碎碎念上限',type:'number',hint:'上午/下午/晚上各最多几条'},
    {key:'care_trigger_chance',label:'关心事件触发率',type:'number',hint:'0-1之间，如0.8表示80%'},
  ];
  form.innerHTML=fields.map(function(f){
    var val=_proactiveData[f.key];
    if(f.type==='toggle'){
      var on=val?'on':'';
      return '<div style="display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid var(--border);">'+
        '<div><div style="font-size:13px;">'+f.label+'</div><div style="font-size:11px;color:var(--text-dim);">'+f.hint+'</div></div>'+
        '<div class="toggle '+on+'" onclick="this.classList.toggle(\'on\')" data-key="'+f.key+'"></div></div>';
    }
    return '<div style="padding:12px 0;border-bottom:1px solid var(--border);">'+
      '<div style="font-size:13px;margin-bottom:6px;">'+f.label+'</div>'+
      '<div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">'+f.hint+'</div>'+
      '<input class="form-input" type="number" value="'+(val||0)+'" data-key="'+f.key+'" style="width:120px;" step="0.1"></div>';
  }).join('');
  loadProactiveEvents();
}

async function saveProactive(){
  var data={};
  document.querySelectorAll('#proactiveForm [data-key]').forEach(function(el){
    var key=el.dataset.key;
    if(el.classList.contains('toggle')){
      data[key]=el.classList.contains('on');
    }else{
      data[key]=parseFloat(el.value)||0;
    }
  });
  var res=await fetch('/api/proactive',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  var result=await res.json();
  toast(result.msg);
}

function proactiveEsc(v){
  return String(v===undefined||v===null?'':v).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

async function loadProactiveEvents(){
  var params=new URLSearchParams({limit:'100'});
  var user=document.getElementById('proactiveEventUser');
  var status=document.getElementById('proactiveEventStatus');
  if(user&&user.value.trim())params.set('user_id',user.value.trim());
  if(status&&status.value)params.set('status',status.value);
  var res=await fetch('/api/proactive/events?'+params.toString());
  var data=await res.json();
  var rows=data.data||[];
  var body=document.getElementById('proactiveEventBody');
  var empty=document.getElementById('proactiveEventEmpty');
  if(!rows.length){
    body.innerHTML='';
    empty.style.display='block';
    return;
  }
  empty.style.display='none';
  body.innerHTML=rows.map(function(e){
    var color=e.status==='sent'?'var(--green)':(e.status==='planned'?'var(--cyan)':(e.status==='failed'?'var(--red)':'var(--text-dim)'));
    return '<tr>'+
      '<td><span style="color:'+color+';font-weight:600;">'+proactiveEsc(e.status)+'</span></td>'+
      '<td>'+proactiveEsc(e.trigger_type)+'</td>'+
      '<td style="white-space:normal;min-width:260px;">'+proactiveEsc(e.reason)+'<div style="font-size:10px;color:var(--text-dim);margin-top:4px;">'+proactiveEsc((e.extra_context||'').slice(0,120))+'</div></td>'+
      '<td style="font-size:11px;">'+proactiveEsc(e.created_at)+'<div style="color:var(--text-dim);">'+proactiveEsc(e.sent_at||'')+'</div></td>'+
      '<td>'+proactiveEsc(e.user_id)+'<div style="font-size:10px;color:var(--text-dim);">'+proactiveEsc(e.db_path||'')+'</div></td>'+
    '</tr>';
  }).join('');
}

// ===== 成长目标 =====
let growthGoals=[];

async function loadGrowthGoalsPage(){
  await loadGrowthGoals();
}

function goalEsc(v){
  return String(v===undefined||v===null?'':v).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

async function loadGrowthGoals(){
  const params=new URLSearchParams({limit:'200'});
  const user=document.getElementById('goalUserFilter').value.trim();
  const status=document.getElementById('goalStatusFilter').value;
  const q=document.getElementById('goalQuery').value.trim();
  if(user)params.set('user_id',user);
  if(status)params.set('status',status);
  if(q)params.set('q',q);
  const r=await fetch('/api/growth-goals?'+params.toString());
  const d=await r.json();
  growthGoals=d.data||[];
  renderGrowthGoals();
}

function renderGrowthGoals(){
  const body=document.getElementById('goalBody');
  const empty=document.getElementById('goalEmpty');
  const count=document.getElementById('goalCount');
  count.textContent=growthGoals.length+' 条';
  if(!growthGoals.length){
    body.innerHTML='';
    empty.style.display='block';
    return;
  }
  empty.style.display='none';
  body.innerHTML=growthGoals.map(function(g){
    const tasks=(g.micro_tasks||[]).map(function(t){
      return '<div style="font-size:11px;color:'+(t.done?'var(--text-dim)':'var(--text)')+';">'+(t.done?'✓ ':'□ ')+goalEsc(t.text||'')+'</div>';
    }).join('')||'<span style="color:var(--text-dim);">-</span>';
    const id=goalEsc(g.goal_id);
    const statusColor=g.status==='active'?'var(--green)':(g.status==='paused'?'var(--amber)':(g.status==='completed'?'var(--cyan)':'var(--text-dim)'));
    return '<tr>'+
      '<td><span style="color:'+statusColor+';font-weight:600;">'+goalEsc(g.status)+'</span><div style="font-size:10px;color:var(--text-dim);">'+(g.allow_proactive?'可主动':'不主动')+'</div></td>'+
      '<td>'+goalEsc(g.goal_type||'其他')+'</td>'+
      '<td style="min-width:260px;white-space:normal;"><strong>'+goalEsc(g.title||'')+'</strong><div style="font-size:11px;color:var(--text-dim);margin-top:4px;">'+goalEsc(g.description||'')+'</div><div style="font-size:10px;color:var(--text-dim);margin-top:4px;">'+goalEsc(g.user_id||'')+' · '+goalEsc(g.db_path||'')+'</div></td>'+
      '<td style="min-width:180px;white-space:normal;">'+tasks+'</td>'+
      '<td style="font-size:11px;">'+goalEsc(g.next_follow_up||'-')+'</td>'+
      '<td>'+Number(g.pressure_level||0)+'/5</td>'+
      '<td style="min-width:210px;">'+
        '<button class="btn" style="padding:3px 8px;font-size:10px;" onclick="editGrowthGoal(\''+id+'\')">编辑</button> '+
        '<button class="btn" style="padding:3px 8px;font-size:10px;" onclick="setGrowthGoalStatus(\''+id+'\',\'paused\')">暂停</button> '+
        '<button class="btn" style="padding:3px 8px;font-size:10px;" onclick="setGrowthGoalStatus(\''+id+'\',\'completed\')">完成</button> '+
        '<button class="btn btn-danger" style="padding:3px 8px;font-size:10px;" onclick="deleteGrowthGoal(\''+id+'\')">删除</button>'+
      '</td>'+
    '</tr>';
  }).join('');
}

function showGoalCreate(){
  const user=document.getElementById('goalUserFilter').value.trim();
  const title=prompt('目标标题：');
  if(!title||!title.trim())return;
  const taskText=prompt('微任务，每行一条：','下次复盘进展')||'';
  const tasks=taskText.split(/\n|;|；/).map(function(x){return x.trim();}).filter(Boolean).map(function(x){return {text:x,done:false};});
  fetch('/api/growth-goals',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    user_id:user||'qq_517908311',
    persona:document.getElementById('goalPersonaInput').value.trim(),
    title:title.trim(),
    goal_type:'其他',
    micro_tasks:tasks,
    pressure_level:2,
    allow_proactive:true
  })}).then(r=>r.json()).then(function(d){toast(d.msg||'已创建',!d.ok);loadGrowthGoals();});
}

function editGrowthGoal(id){
  const g=growthGoals.find(function(x){return x.goal_id===id;});
  if(!g)return;
  const title=prompt('目标标题：',g.title||'');
  if(!title||!title.trim())return;
  const follow=prompt('下次跟进时间（YYYY-MM-DD HH:MM:SS，可空）：',g.next_follow_up||'')||'';
  const taskText=(g.micro_tasks||[]).map(function(t){return (t.done?'[x] ':'')+(t.text||'');}).join('\n');
  const tasksRaw=prompt('微任务，每行一条；以 [x] 开头表示已完成：',taskText)||'';
  const tasks=tasksRaw.split(/\n|;|；/).map(function(x){
    x=x.trim();
    if(!x)return null;
    const done=/^\[x\]/i.test(x);
    return {text:x.replace(/^\[x\]\s*/i,''),done:done};
  }).filter(Boolean);
  fetch('/api/growth-goals/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
    goal_id:id,title:title.trim(),next_follow_up:follow.trim(),micro_tasks:tasks
  })}).then(r=>r.json()).then(function(d){toast(d.msg||'已更新',!d.ok);loadGrowthGoals();});
}

async function setGrowthGoalStatus(id,status){
  const r=await fetch('/api/growth-goals/update',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({goal_id:id,status:status})});
  const d=await r.json();
  toast(d.msg||'已更新',!d.ok);
  loadGrowthGoals();
}

async function deleteGrowthGoal(id){
  if(!confirm('确定删除这个成长目标？'))return;
  const r=await fetch('/api/growth-goals/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({goal_id:id})});
  const d=await r.json();
  toast(d.msg||'已删除',!d.ok);
  loadGrowthGoals();
}


// ===== UBAI 粒子水印 =====
(function(){
  var ubaiCanvas=document.createElement('canvas');
  ubaiCanvas.style.cssText='position:fixed;bottom:20px;right:20px;width:200px;height:80px;pointer-events:all;z-index:9998;cursor:pointer;';
  ubaiCanvas.width=200;ubaiCanvas.height=80;
  document.body.appendChild(ubaiCanvas);
  var ctx=ubaiCanvas.getContext('2d');
  var particles=[];
  var alive=true;
  var dissolved=false;

  // Generate particles forming "UBAI"
  var tempCanvas=document.createElement('canvas');
  tempCanvas.width=200;tempCanvas.height=80;
  var tctx=tempCanvas.getContext('2d');
  tctx.fillStyle='#fff';
  tctx.font='bold 48px JetBrains Mono,monospace';
  tctx.textBaseline='top';
  tctx.fillText('UBAI',20,15);
  var imgData=tctx.getImageData(0,0,200,80);

  for(var y=0;y<80;y+=2){
    for(var x=0;x<200;x+=2){
      var idx=(y*200+x)*4;
      if(imgData.data[idx+3]>128){
        particles.push({
          x:x,y:y,
          ox:x,oy:y,
          vx:0,vy:0,
          alpha:0.8,
          size:1.5
        });
      }
    }
  }

  function draw(){
    if(dissolved)return;
    ctx.clearRect(0,0,200,80);
    particles.forEach(function(p){
      ctx.fillStyle='rgba(255,255,255,'+p.alpha+')';
      ctx.fillRect(p.x-p.size/2,p.y-p.size/2,p.size,p.size);
    });
    if(alive) requestAnimationFrame(draw);
  }
  draw();

  // Mouse interaction: dissolve permanently
  ubaiCanvas.addEventListener('mousemove',function(e){
    if(dissolved)return;
    var rect=ubaiCanvas.getBoundingClientRect();
    var mx=e.clientX-rect.left;
    var my=e.clientY-rect.top;
    var interacted=false;
    particles.forEach(function(p){
      var dx=p.x-mx;
      var dy=p.y-my;
      var dist=Math.sqrt(dx*dx+dy*dy);
      if(dist<30){
        p.vx=(Math.random()-0.5)*8;
        p.vy=(Math.random()-0.5)*8-2;
        p.alpha*=0.9;
        interacted=true;
      }
    });
    if(interacted){
      // Animate dissolution
      dissolve();
    }
  });

  function dissolve(){
    dissolved=true;
    var frame=0;
    function anim(){
      frame++;
      ctx.clearRect(0,0,200,80);
      var anyAlive=false;
      particles.forEach(function(p){
        p.x+=p.vx;
        p.y+=p.vy;
        p.vy+=0.1;
        p.alpha*=0.95;
        if(p.alpha>0.01){
          anyAlive=true;
          ctx.fillStyle='rgba(255,255,255,'+p.alpha+')';
          ctx.fillRect(p.x-p.size/2,p.y-p.size/2,p.size,p.size);
        }
      });
      if(anyAlive&&frame<120) requestAnimationFrame(anim);
      else{
        ctx.clearRect(0,0,200,80);
        ubaiCanvas.style.display='none';
      }
    }
    anim();
  }
})();

// ===== 显示起名依据弹窗（仅首次 + 5秒自动关闭）=====
if(!localStorage.getItem('crown_naming_read')){
  setTimeout(function(){
    var popup=document.getElementById('namingPopup');
    if(popup) popup.classList.add('show');
  },1500);
  setTimeout(function(){
    var popup=document.getElementById('namingPopup');
    if(popup){
      popup.classList.remove('show');
      localStorage.setItem('crown_naming_read','1');
    }
  },6500);
}


// ===== 人设数据库信息 =====
async function loadPersonaDBInfo(){
  try{
    var res=await fetch('/api/persona/db_info');
    var data=await res.json();
    var el=document.getElementById('personaDBInfo');
    var html='<div style="margin-bottom:8px;">当前人设: <span style="color:var(--amber);">'+data.current_persona+'</span></div>';
    html+='<div style="margin-bottom:8px;">数据库: <span style="color:var(--text-dim);">'+data.current_db+'</span></div>';
    html+='<div style="margin-bottom:12px;">心理画像模式: <span style="color:var(--amber);">'+(data.psychology_shared?'共享':'独立')+'</span></div>';
    html+='<div style="font-size:11px;color:var(--text-dim);">';
    data.databases.forEach(function(db){
      html+=db.name+': '+db.file+' ('+Math.round(db.size/1024)+'KB)  ';
    });
    html+='</div>';
    el.innerHTML=html;
    var toggle=document.getElementById('psychSharedToggle');
    if(data.psychology_shared) toggle.classList.add('on');
    else toggle.classList.remove('on');
  }catch(e){}
}

async function togglePsychShared(){
  var toggle=document.getElementById('psychSharedToggle');
  var shared=!toggle.classList.contains('on');
  toggle.classList.toggle('on');
  var res=await fetch('/api/persona/psychology_shared',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({shared:shared})});
  var data=await res.json();
  toast(data.msg);
  loadPersonaDBInfo();
}

loadPersonaDBInfo();


// ===== 场景组管理 =====
var _currentSceneGroup='default';
var _bindingLoading=false;
async function loadSceneGroups(){
  var res=await fetch('/api/scene_groups');
  var data=await res.json();
  _currentSceneGroup=data.active||'default';
  var sel=document.getElementById('sceneGroupSelect');
  if(sel){
    sel.innerHTML=data.groups.map(function(g){
      return '<option value="'+g.name+'" '+(g.name===_currentSceneGroup?'selected':'')+'>'+g.name+' ('+g.count+')</option>';
    }).join('');
  }
  // update binding dropdown
  var bindSel=document.getElementById('bindSceneGroup');
  if(bindSel){
    var prevVal=bindSel.value;
    bindSel.innerHTML='<option value="">不绑定</option>'+data.groups.map(function(g){
      return '<option value="'+g.name+'">'+g.name+'</option>';
    }).join('');
    if(prevVal)bindSel.value=prevVal;
  }
}

async function switchSceneGroup(name){
  var res=await fetch('/api/scene_group/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  var data=await res.json();
  toast(data.msg);
  _currentSceneGroup=name;
  loadScenes();
}

async function createSceneGroup(){
  var name=prompt('输入新场景组名称：');
  if(!name)return;
  var res=await fetch('/api/scene_group/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  var data=await res.json();
  toast(data.msg);
  if(data.ok){loadSceneGroups();switchSceneGroup(name);}
}

async function addSceneToGroup(){
  var id=prompt('场景ID（英文，如 work_chat）：');
  if(!id)return;
  var name=prompt('场景名称：');
  if(!name)return;
  var res=await fetch('/api/scene_group/'+_currentSceneGroup+'/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,name:name,description:'',trigger_hint:'',tone:'',extra_hint:''})});
  var data=await res.json();
  toast(data.msg);
  if(data.ok)loadScenes();
}

// ===== 语气组管理 =====
var _currentToneGroup='default';
async function loadToneGroups(){
  var res=await fetch('/api/tone_groups');
  var data=await res.json();
  _currentToneGroup=data.active||'default';
  var sel=document.getElementById('toneGroupSelect');
  if(sel){
    sel.innerHTML=data.groups.map(function(g){
      return '<option value="'+g.name+'" '+(g.name===_currentToneGroup?'selected':'')+'>'+g.name+' ('+g.count+')</option>';
    }).join('');
  }
  var bindSel=document.getElementById('bindToneGroup');
  if(bindSel){
    var prevVal=bindSel.value;
    bindSel.innerHTML='<option value="">不绑定</option>'+data.groups.map(function(g){
      return '<option value="'+g.name+'">'+g.name+'</option>';
    }).join('');
    if(prevVal)bindSel.value=prevVal;
  }
}

async function switchToneGroup(name){
  var res=await fetch('/api/tone_group/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  var data=await res.json();
  toast(data.msg);
  _currentToneGroup=name;
  loadTones();
}

async function createToneGroup(){
  var name=prompt('输入新语气组名称：');
  if(!name)return;
  var res=await fetch('/api/tone_group/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  var data=await res.json();
  toast(data.msg);
  if(data.ok){loadToneGroups();switchToneGroup(name);}
}

async function addToneToGroup(){
  var id=prompt('语气ID（英文，如 soft_comfort）：');
  if(!id)return;
  var name=prompt('语气名称：');
  if(!name)return;
  var res=await fetch('/api/tone_group/'+_currentToneGroup+'/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,name:name,description:'',style:'',verbal_tics:[],sentence_pattern:''})});
  var data=await res.json();
  toast(data.msg);
  if(data.ok)loadTones();
}

// ===== 人设绑定 =====
async function loadPersonaBindings(){
  if(!currentPersona) return;
  try{
    var res=await fetch('/api/persona/'+currentPersona+'/bindings');
    var data=await res.json();
    var sceneBind=document.getElementById('bindSceneGroup');
    var toneBind=document.getElementById('bindToneGroup');
    if(sceneBind&&data.scene_group)sceneBind.value=data.scene_group; else if(sceneBind)sceneBind.value='';
    if(toneBind&&data.tone_group)toneBind.value=data.tone_group; else if(toneBind)toneBind.value='';
    var audioBind=document.getElementById('bindAudioGroup');
    if(audioBind&&data.audio_group)audioBind.value=data.audio_group; else if(audioBind)audioBind.value='';
    // 显示当前绑定状态
    var statusEl=document.getElementById('personaBindingStatus');
    if(statusEl){
      var parts=[];
      if(data.scene_group)parts.push('场景:'+data.scene_group);
      if(data.tone_group)parts.push('语气:'+data.tone_group);
      if(data.audio_group)parts.push('音频:'+data.audio_group);
      statusEl.textContent=parts.length?'当前 '+currentPersona+' 绑定: '+parts.join(' | '):'当前人设暂无绑定';
    }
  }catch(e){}
}

async function savePersonaBindings(){
  if(_bindingLoading) return;
  if(!currentPersona) { toast('请先选择一个人设',true); return; }
  var sceneGroup=document.getElementById('bindSceneGroup').value;
  var toneGroup=document.getElementById('bindToneGroup').value;
  var audioGroup=document.getElementById('bindAudioGroup')?document.getElementById('bindAudioGroup').value:'';
  var res=await fetch('/api/persona/'+currentPersona+'/bindings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scene_group:sceneGroup,tone_group:toneGroup,audio_group:audioGroup})});
  var data=await res.json();
  toast(data.msg);
  loadPersonaBindings();
}

// 页面加载时获取组列表
// page load - ensure correct order: populate dropdowns first, then set bindings
(async function(){
  _bindingLoading=true;
  try{await loadSceneGroups();}catch(e){}
  try{await loadToneGroups();}catch(e){}
  try{await loadAudioGroups();}catch(e){}
  _bindingLoading=false;
  try{await loadPersonaBindings();}catch(e){}
})();


// ===== 打开文件夹 =====
async function openFolder(folder){
  var res=await fetch('/api/open_folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:folder})});
  var data=await res.json();
  if(!data.ok)toast(data.msg);
}

// ===== 音频组管理 =====
var _currentAudioGroup='';
async function loadAudioGroups(){
  var res=await fetch('/api/audio_groups');
  var data=await res.json();
  _currentAudioGroup=data.active||'';
  var sel=document.getElementById('audioGroupSelect');
  if(sel){
    sel.innerHTML='<option value="">请选择</option>'+data.groups.map(function(g){
      return '<option value="'+g.name+'" '+(g.name===_currentAudioGroup?'selected':'')+'>'+g.name+' ('+g.count+' 个文件)</option>';
    }).join('');
  }
  // update binding dropdown
  var bindSel=document.getElementById('bindAudioGroup');
  if(bindSel){
    var prevVal=bindSel.value;
    bindSel.innerHTML='<option value="">不绑定</option>'+data.groups.map(function(g){
      return '<option value="'+g.name+'">'+g.name+'</option>';
    }).join('');
    if(prevVal)bindSel.value=prevVal;
  }
  if(_currentAudioGroup)loadAudioFiles(_currentAudioGroup);
}

async function createAudioGroup(){
  var name=prompt('输入音频组名称（如角色名）：');
  if(!name)return;
  var res=await fetch('/api/audio_group/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:name})});
  var data=await res.json();
  toast(data.msg);
  if(data.ok){loadAudioGroups();document.getElementById('audioGroupSelect').value=name;loadAudioFiles(name);}
}

async function loadAudioFiles(name){
  if(!name){document.getElementById('audioFileList').innerHTML='';document.getElementById('audioFileEmpty').style.display='block';return;}
  _currentAudioGroup=name;
  var res=await fetch('/api/audio_group/'+encodeURIComponent(name)+'/files');
  var data=await res.json();
  var list=document.getElementById('audioFileList');
  var empty=document.getElementById('audioFileEmpty');
  var title=document.getElementById('audioFileTitle');
  if(title)title.textContent=name+' — 音频文件';
  if(!data.files||data.files.length===0){list.innerHTML='';empty.style.display='block';return;}
  empty.style.display='none';
  list.innerHTML=data.files.map(function(f){
    return '<div style="display:flex;align-items:center;justify-content:space-between;padding:10px 0;border-bottom:1px solid var(--border);">'+
      '<div><span style="font-family:JetBrains Mono,monospace;font-size:12px;">'+f.name+'</span>'+
      '<span style="font-size:11px;color:var(--text-dim);margin-left:8px;">'+(f.size/1024).toFixed(1)+'KB</span></div>'+
      '<div style="display:flex;gap:8px;">'+
        '<button class="btn" style="padding:3px 10px;font-size:11px;" onclick="setAudioRef()">设为TTS参考</button>'+
        '<button class="btn btn-danger" style="padding:3px 10px;font-size:11px;" onclick="deleteAudio(\''+f.name+'\')">删除</button>'+
      '</div></div>';
  }).join('');
}

async function uploadAudioFile(input){
  if(!input.files.length||!_currentAudioGroup){toast('请先选择音频组');return;}
  var file=input.files[0];
  var formData=new FormData();
  formData.append('file',file);
  toast('正在上传...');
  var res=await fetch('/api/audio_group/'+encodeURIComponent(_currentAudioGroup)+'/upload',{method:'POST',body:formData});
  var data=await res.json();
  toast(data.msg);
  if(data.ok)loadAudioFiles(_currentAudioGroup);
  input.value='';
}

async function deleteAudio(filename){
  if(!_currentAudioGroup)return;
  showConfirm('删除音频','确定要删除 '+filename+' 吗？',async function(){
    var res=await fetch('/api/audio_group/'+encodeURIComponent(_currentAudioGroup)+'/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({filename:filename})});
    var data=await res.json();
    toast(data.msg);
    loadAudioFiles(_currentAudioGroup);
  });
}

async function setAudioRef(){
  if(!_currentAudioGroup){toast('请先选择音频组');return;}
  var res=await fetch('/api/audio_group/'+encodeURIComponent(_currentAudioGroup)+'/set_reference',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({})});
  var data=await res.json();
  toast(data.msg);
  if(data.ok){
    // 更新页面显示
    loadAudioFiles(_currentAudioGroup);
  }
}

// ===== 关系定制系统 =====
var _relTypes=[];
var _relUsers={};

async function loadRelationships(){
  try{
    var res=await fetch('/api/relationships');
    var data=await res.json();
    if(data.ok){
      _relTypes=data.types||[];
      _relUsers=data.users||{};
      renderRelUsers();
      renderRelTypes();
      loadRelationshipBrief();
    }
  }catch(e){console.error(e);}
}

function renderRelUsers(){
  var el=document.getElementById('relUserList');
  var keys=Object.keys(_relUsers);
  if(!keys.length){el.innerHTML='<div style="color:var(--text-dim);padding:8px;">暂无用户数据</div>';return;}
  var h='<div style="display:flex;flex-wrap:wrap;gap:12px;">';
  keys.forEach(function(uid){
    var u=_relUsers[uid];
    var activeId=u.type_id;
    h+='<div style="background:var(--bg-panel);border:1px solid var(--border);border-radius:8px;padding:14px;min-width:220px;">';
    h+='<div style="font-weight:600;margin-bottom:8px;">'+uid+'</div>';
    h+='<div style="font-size:11px;color:var(--text-dim);margin-bottom:8px;">切换时间: '+u.switched_at+'</div>';
    h+='<div style="display:flex;flex-direction:column;gap:6px;">';
    _relTypes.forEach(function(t){
      var isActive=t.id===activeId;
      h+='<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:6px;cursor:pointer;transition:all 0.2s;background:'+(isActive?'var(--amber-bg)':'transparent')+';border:1px solid '+(isActive?'var(--amber)':'var(--border)')+';" onclick="switchUserRel(\''+uid+'\',\''+t.id+'\')">';
      h+='<div style="width:16px;height:16px;border-radius:50%;border:2px solid '+(isActive?'var(--amber)':'var(--border)')+';display:flex;align-items:center;justify-content:center;">';
      if(isActive)h+='<div style="width:8px;height:8px;border-radius:50%;background:var(--amber);"></div>';
      h+='</div>';
      h+='<span style="font-size:12px;color:'+(isActive?'var(--amber)':'var(--text-dim)')+';">'+t.name+'</span>';
      h+='</div>';
    });
    h+='</div></div>';
  });
  h+='</div>';
  el.innerHTML=h;
}

function renderRelTypes(){
  var el=document.getElementById('relTypeList');
  if(!_relTypes.length){el.innerHTML='<div style="color:var(--text-dim);padding:8px;">暂无关系类型</div>';return;}
  var BASE_TYPES=['default','friend','lover','family','colleague','teacher_student'];
  var h='<div style="display:flex;flex-direction:column;gap:10px;">';
  _relTypes.forEach(function(t){
    var isBase=t.id.charAt(0)==='_'||BASE_TYPES.indexOf(t.id)>=0;
    h+='<div style="background:var(--bg-panel);border:1px solid var(--border);border-radius:8px;padding:14px;">';
    h+='<div style="display:flex;justify-content:space-between;align-items:center;">';
    h+='<div><span style="font-weight:700;font-size:15px;">'+t.name+'</span> <span style="color:var(--text-dim);font-size:12px;">('+t.id+')</span>';
    if(isBase)h+=' <span style="font-size:10px;background:rgba(255,255,255,0.05);color:var(--text-dim);padding:2px 6px;border-radius:3px;">基础</span>';
    h+='</div>';
    h+='<div style="display:flex;gap:6px;">';
    if(isBase){
      h+='<span style="font-size:11px;color:var(--text-dim);padding:4px 10px;">不可编辑</span>';
    }else{
      h+='<button class="btn" style="font-size:11px;padding:4px 10px;" onclick="editRelationshipType(\''+t.id+'\')">编辑</button>';
      h+='<button class="btn" style="font-size:11px;padding:4px 10px;background:rgba(255,100,100,0.15);" onclick="deleteRelType(\''+t.id+'\')">删除</button>';
    }
    h+='</div></div>';
    h+='<div style="font-size:12px;color:var(--text-dim);margin-top:4px;">'+t.description+'</div>';
    h+='<div style="font-size:11px;color:var(--text-dim);margin-top:6px;">经验倍率: '+t.exp_multiplier+'x | 等级: '+Object.keys(t.levels).length+'级 | 亲密: '+(t.personality.intimacy_level||0)+'/3</div>';
    if(t.personality.pet_names&&t.personality.pet_names.length)h+='<div style="font-size:11px;color:var(--text-dim);">称呼: '+t.personality.pet_names.join('、')+'</div>';
    h+='</div>';
  });
  h+='</div>';
  el.innerHTML=h;
}

async function loadRelationshipBrief(){
  var userInput=document.getElementById('relBriefUserInput');
  var personaInput=document.getElementById('relBriefPersonaInput');
  var limitInput=document.getElementById('relBriefLimitInput');
  var summaryEl=document.getElementById('relBriefSummary');
  var timelineEl=document.getElementById('relBriefTimeline');
  if(!summaryEl||!timelineEl)return;
  var userId=userInput?userInput.value.trim():'';
  var persona=personaInput?personaInput.value.trim():'';
  var limit=limitInput?String(limitInput.value||20):'20';
  var p=new URLSearchParams({limit:limit});
  if(userId)p.set('user_id',userId);
  if(persona)p.set('persona',persona);
  summaryEl.innerHTML='读取中...';
  timelineEl.innerHTML='<div style="color:var(--text-dim);font-size:12px;">读取中...</div>';
  try{
    var res=await fetch('/api/relationship/brief?'+p.toString());
    var data=await res.json();
    if(!data.ok)throw new Error(data.error||data.msg||'读取失败');
    var s=data.summary||{};
    var active=s.active_relationship||{};
    var bind=s.account_binding||{};
    summaryEl.innerHTML=
      '<div class="log-line"><span class="log-msg">当前关系：'+hubSafe(active.type_id,'暂无')+'</span></div>'+
      '<div class="log-line"><span class="log-msg">最近切换：'+hubSafe(s.last_relationship_switch_at,'暂无')+'</span></div>'+
      '<div class="log-line"><span class="log-msg">绑定关系：'+hubSafe(bind.relationship_type,'暂无')+' / '+hubSafe(bind.persona_name,'-')+'</span></div>'+
      '<div class="log-line"><span class="log-msg">最近联系：'+hubSafe(s.last_contact_at,'暂无')+'</span></div>'+
      '<div style="margin-top:6px;font-size:11px;color:var(--text-dim);">计数：切换 '+hubSafe((s.counts||{}).relationship_switch||0)+' · 绑定 '+hubSafe((s.counts||{}).account_binding||0)+' · 目标事件 '+hubSafe((s.counts||{}).goal_event||0)+' · 记忆 '+hubSafe((s.counts||{}).memory_event||0)+' · 聊天 '+hubSafe((s.counts||{}).chat_record||0)+'</div>';
    var rows=data.timeline||[];
    if(!rows.length){
      timelineEl.innerHTML='<div style="color:var(--text-dim);font-size:12px;">暂无时间线数据</div>';
      return;
    }
    timelineEl.innerHTML=rows.map(function(item){
      var detail=hubSafe(item.detail||'').slice(0,120);
      return '<div class="log-line"><span class="log-time">['+hubSafe(item.time,'-')+']</span><span class="log-msg">['+hubSafe(item.kind,'event')+'] '+hubSafe(item.title,'')+(detail?(' / '+detail):'')+'</span></div>';
    }).join('');
  }catch(e){
    summaryEl.innerHTML='<span style="color:var(--red);">读取失败：'+hubSafe(e.message)+'</span>';
    timelineEl.innerHTML='<div style="color:var(--red);font-size:12px;">暂无可展示数据</div>';
  }
}

async function switchUserRel(uid,typeId){
  var res=await fetch('/api/relationship/switch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:uid,type_id:typeId})});
  var data=await res.json();
  toast(data.ok?'已切换':('失败: '+data.error));
  if(data.ok)loadRelationships();
}

function showAddRelationship(){
  document.getElementById('relEditTitle').textContent='新增关系类型';
  document.getElementById('relEditForm').innerHTML=_buildRelForm({});
  document.getElementById('relEditOverlay').style.display='flex';
}

function editRelationshipType(typeId){
  var t=null;
  _relTypes.forEach(function(x){if(x.id===typeId)t=x;});
  if(!t)return;
  document.getElementById('relEditTitle').textContent='编辑关系类型: '+t.name;
  document.getElementById('relEditForm').innerHTML=_buildRelForm(t);
  document.getElementById('relEditOverlay').style.display='flex';
}

function _buildRelForm(t){
  var id=t.id||'';
  var name=t.name||'';
  var desc=t.description||'';
  var exp=t.exp_multiplier||1.0;
  var p=t.personality||{};
  var tone=p.tone||'';
  var intimacy=p.intimacy_level||0;
  var canFlirt=p.can_flirt?true:false;
  var canJealous=p.can_jealous?true:false;
  var petNames=(p.pet_names||[]).join('、');
  var prompt=t.prompt_template||'';
  var isEdit=!!id;
  var h='';
  h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">类型ID *</label><input id="reId" value="'+id+'"'+(isEdit?' disabled':'')+' style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;" placeholder="如 lover, bestie"></div>';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">显示名称</label><input id="reName" value="'+name+'" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;"></div>';
  h+='</div>';
  h+='<div style="margin-bottom:10px;"><label style="font-size:11px;color:var(--text-dim);">描述</label><input id="reDesc" value="'+desc+'" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;"></div>';
  h+='<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;margin-bottom:10px;">';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">经验倍率</label><input id="reExp" type="number" step="0.1" value="'+exp+'" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;"></div>';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">语气风格</label><input id="reTone" value="'+tone+'" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;"></div>';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">亲密等级(0-3)</label><input id="reIntimacy" type="number" min="0" max="3" value="'+intimacy+'" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;"></div>';
  h+='</div>';
  h+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">可用称呼（顿号分隔）</label><input id="rePetNames" value="'+petNames+'" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:13px;"></div>';
  h+='<div style="display:flex;gap:16px;align-items:end;padding-bottom:6px;">';
  h+='<label style="font-size:12px;"><input type="checkbox" id="reFlirt"'+(canFlirt?' checked':'')+'> 可调情</label>';
  h+='<label style="font-size:12px;"><input type="checkbox" id="reJealous"'+(canJealous?' checked':'')+'> 可吃醋</label>';
  h+='</div></div>';
  h+='<div style="margin-bottom:10px;"><label style="font-size:11px;color:var(--text-dim);">Prompt 模板</label><textarea id="rePrompt" rows="6" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:12px;font-family:monospace;resize:vertical;">'+prompt+'</textarea></div>';
  h+='<div style="margin-bottom:10px;"><label style="font-size:11px;color:var(--text-dim);">等级配置（JSON 格式，如 {5:{name:"好友",hint:"..."}}）</label><textarea id="reLevels" rows="4" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:12px;font-family:monospace;resize:vertical;">'+JSON.stringify(t.levels||{},null,2)+'</textarea></div>';
  h+='<div><label style="font-size:11px;color:var(--text-dim);">升级事件（JSON 格式，如 {6:"关系更近一步"}）</label><textarea id="reLevelUp" rows="3" style="width:100%;background:var(--bg-deep);color:var(--text);border:1px solid var(--border);border-radius:4px;padding:6px 8px;font-size:12px;font-family:monospace;resize:vertical;">'+JSON.stringify(t.level_up_events||{},null,2)+'</textarea></div>';
  return h;
}

async function saveRelationshipType(){
  var id=document.getElementById('reId').value.trim();
  if(!id){toast('类型ID不能为空');return;}
  var levels={};var levelUp={};
  try{levels=JSON.parse(document.getElementById('reLevels').value||'{}');}catch(e){toast('等级配置JSON格式错误');return;}
  try{levelUp=JSON.parse(document.getElementById('reLevelUp').value||'{}');}catch(e){toast('升级事件JSON格式错误');return;}
  var body={
    id:id,
    name:document.getElementById('reName').value,
    description:document.getElementById('reDesc').value,
    exp_multiplier:parseFloat(document.getElementById('reExp').value)||1.0,
    personality:{
      tone:document.getElementById('reTone').value,
      intimacy_level:parseInt(document.getElementById('reIntimacy').value)||0,
      can_flirt:document.getElementById('reFlirt').checked,
      can_jealous:document.getElementById('reJealous').checked,
      pet_names:document.getElementById('rePetNames').value.split('、').filter(function(s){return s.trim();}),
    },
    prompt_template:document.getElementById('rePrompt').value,
    levels:levels,
    level_up_events:levelUp,
  };
  var res=await fetch('/api/relationship/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  var data=await res.json();
  toast(data.ok?'保存成功':('失败: '+data.error));
  if(data.ok){document.getElementById('relEditOverlay').style.display='none';loadRelationships();}
}

async function autoGenerateWhitelistBindings(){
  if(!confirm('将为所有白名单账号自动生成默认关系配置（朋友），已存在的不会覆盖。继续？'))return;
  try{
    const res=await fetch('/api/relationship/auto-generate',{method:'POST'});
    const data=await res.json();
    toast(data.msg||'已完成');
    if(data.ok)loadRelationships();
  }catch(e){toast('操作失败: '+e.message,true);}
}

async function deleteRelType(typeId){
  if(!confirm('确定删除关系类型 "'+typeId+'" 吗？此操作不可撤销。'))return;
  var res=await fetch('/api/relationship/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:typeId})});
  var data=await res.json();
  toast(data.ok?'已删除':('失败: '+data.error));
  if(data.ok)loadRelationships();
}

// ===== 白名单管理 =====
async function loadWhitelist(){
  try{
    const res=await fetch('/api/whitelist');
    const data=await res.json();
    if(!data.ok){toast(data.error||'加载失败',true);return;}
    const el=document.getElementById('whitelistContent');
    if(!data.users||!data.users.length){
      el.innerHTML='<div style="color:var(--text-dim);padding:12px;">暂无用户。第一个和机器人聊天的用户会自动添加。</div>';
      return;
    }
    let html='<div style="display:grid;gap:8px;">';
    data.users.forEach(u=>{
      const statusClass=u.enabled?'status-ok':'status-off';
      const statusText=u.enabled?'已启用':'已禁用';
      const toggleText=u.enabled?'禁用':'启用';
      html+=`<div style="background:var(--bg-deep);border:1px solid var(--border);border-radius:8px;padding:12px;display:flex;justify-content:space-between;align-items:center;">
        <div>
          <span style="font-weight:700;font-size:15px;">${u.nickname||u.qq_id}</span>
          <span style="font-size:12px;color:var(--text-dim);margin-left:8px;">QQ: ${u.qq_id}</span>
          <span class="${statusClass}" style="margin-left:8px;font-size:11px;">${statusText}</span>
          <div style="font-size:11px;color:var(--text-dim);margin-top:4px;">首次: ${u.first_seen} | 最近: ${u.last_seen}</div>
        </div>
        <div style="display:flex;gap:6px;">
          <button class="btn" style="font-size:11px;padding:4px 10px;" onclick="toggleWhitelistUser('${u.qq_id}',${!u.enabled})">${toggleText}</button>
          <button class="btn btn-danger" style="font-size:11px;padding:4px 10px;" onclick="removeWhitelistUser('${u.qq_id}')">删除</button>
        </div>
      </div>`;
    });
    html+='</div>';
    el.innerHTML=html;
  }catch(e){console.error(e);toast('加载失败',true);}
}

async function toggleWhitelistUser(qqId,enabled){
  const res=await fetch('/api/whitelist/toggle',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq_id:qqId,enabled:enabled})});
  const data=await res.json();
  if(data.ok)loadWhitelist();
  else toast(data.error||'操作失败',true);
}

async function removeWhitelistUser(qqId){
  if(!confirm(`确定删除用户 ${qqId} 吗？`))return;
  const res=await fetch('/api/whitelist/remove',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq_id:qqId})});
  const data=await res.json();
  if(data.ok)loadWhitelist();
  else toast(data.error||'删除失败',true);
}

function showAddWhitelist(){
  const qq=prompt('输入要添加的QQ号：');
  if(!qq)return;
  const nick=prompt('输入备注名（可留空）：')||'';
  fetch('/api/whitelist/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({qq_id:qq,nickname:nick})})
    .then(r=>r.json()).then(d=>{
      if(d.ok)loadWhitelist();
      else toast(d.error||'添加失败',true);
    });
}


// ===== 多维性格页面 =====
let dimensionsInfo={}, currentDimensions={}, dimensionsRadarChart=null, historyRadarChart=null;

async function loadDimensionsPersonaSelect(){
  const sel=document.getElementById('dimPersonaSelect');
  if(!sel)return;
  const r=await fetch('/api/personas');
  const list=await r.json();
  sel.innerHTML=list.map(p=>`<option value="${p}">${p}</option>`).join('');
  if(currentPersona&&list.includes(currentPersona))sel.value=currentPersona;
}

async function loadDimensionsPage(){
  await loadDimensionsPersonaSelect();
  await loadDimensionsData();
}

async function loadDimensionsData(){
  const persona=document.getElementById('dimPersonaSelect').value;
  if(!persona)return;
  // 加载维度定义
  if(!dimensionsInfo||!Object.keys(dimensionsInfo).length){
    const ri=await fetch('/api/dimensions/info');
    dimensionsInfo=await ri.json();
  }
  // 加载当前数据
  const rd=await fetch('/api/dimensions/'+persona);
  const d=await rd.json();
  currentDimensions=d.dimensions||{};
  renderDimensionsRadar(currentDimensions);
  renderDimensionsList(currentDimensions);
  loadDimensionsHistory();
}

function renderDimensionsRadar(dims,compareDims,compareLabel){
  const canvas=document.getElementById('dimensionsRadar');
  if(!canvas)return;
  const ctx=canvas.getContext('2d');
  const keys=Object.keys(dimensionsInfo);
  const labels=keys.map(k=>dimensionsInfo[k].name);
  const values=keys.map(k=>dims[k]||50);
  const datasets=[{label:'当前性格',data:values,borderColor:'rgba(255,207,13,0.9)',backgroundColor:'rgba(255,207,13,0.15)',pointBackgroundColor:'rgba(255,207,13,1)',pointBorderColor:'#fff',pointHoverBackgroundColor:'#fff',pointHoverBorderColor:'rgba(255,207,13,1)',borderWidth:2}];
  if(compareDims){
    const cv=keys.map(k=>compareDims[k]||50);
    datasets.push({label:compareLabel||'对比',data:cv,borderColor:'rgba(100,200,255,0.9)',backgroundColor:'rgba(100,200,255,0.1)',pointBackgroundColor:'rgba(100,200,255,1)',pointBorderColor:'#fff',borderWidth:2});
  }
  if(dimensionsRadarChart)dimensionsRadarChart.destroy();
  dimensionsRadarChart=new Chart(ctx,{type:'radar',data:{labels,datasets},options:{responsive:true,maintainAspectRatio:true,scales:{r:{min:0,max:100,ticks:{stepSize:20,color:'rgba(255,255,255,0.4)',backdropColor:'transparent',font:{size:10}},grid:{color:'rgba(255,255,255,0.08)'},pointLabels:{color:'rgba(255,255,255,0.7)',font:{size:11}},angleLines:{color:'rgba(255,255,255,0.08)'}}},plugins:{legend:{labels:{color:'rgba(255,255,255,0.7)',font:{size:11}}},tooltip:{callbacks:{afterLabel:function(ctx){const key=keys[ctx.dataIndex];return dimensionsInfo[key]?dimensionsInfo[key].description:'';}}}}}});
  // 添加悬停显示描述
  canvas.onmousemove=function(e){
    const rect=canvas.getBoundingClientRect();
    const x=e.clientX-rect.left, y=e.clientY-rect.top;
    const cx=canvas.width/2, cy=canvas.height/2;
    const angleStep=2*Math.PI/keys.length;
    const r=Math.min(cx,cy)*0.75;
    let closest=-1,minDist=Infinity;
    for(let i=0;i<keys.length;i++){
      const angle=-Math.PI/2+i*angleStep;
      const px=cx+r*Math.cos(angle);
      const py=cy+r*Math.sin(angle);
      const d=Math.sqrt((x-px)**2+(y-py)**2);
      if(d<minDist){minDist=d;closest=i;}
    }
    if(minDist<30&&closest>=0){
      canvas.title=dimensionsInfo[keys[closest]].name+': '+dimensionsInfo[keys[closest]].description;
    }else{canvas.title='';}
  };
}

function renderDimensionsList(dims){
  const container=document.getElementById('dimensionsList');
  if(!container)return;
  let html='';
  for(const[key,info]of Object.entries(dimensionsInfo)){
    const val=dims[key]||50;
    html+=`<div style="margin-bottom:14px;padding:8px;background:var(--amber-bg);border-radius:6px;" title="${info.description}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
        <span style="font-size:12px;">${info.icon} ${info.name}</span>
        <span style="font-size:12px;color:var(--amber);font-family:'JetBrains Mono',monospace;">${val}</span>
      </div>
      <input type="range" min="0" max="100" value="${val}" data-key="${key}" style="width:100%;accent-color:var(--amber);" oninput="updateDimValue('${key}',this.value)">
      <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${info.description}</div>
    </div>`;
  }
  container.innerHTML=html;
}

function updateDimValue(key,val){
  currentDimensions[key]=parseInt(val);
  renderDimensionsRadar(currentDimensions);
  const labelEl=document.querySelector(`input[data-key='${key}']`).parentElement.querySelector('span:last-child');
  if(labelEl)labelEl.textContent=val;
}

async function saveDimensions(){
  const persona=document.getElementById('dimPersonaSelect').value;
  if(!persona)return;
  const r=await fetch('/api/dimensions/'+persona,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dimensions:currentDimensions,note:'手动调整'})});
  const d=await r.json();
  toast(d.msg||'已保存');
  loadDimensionsHistory();
}

async function analyzeDimensions(){
  const persona=document.getElementById('dimPersonaSelect').value;
  if(!persona)return;
  const r=await fetch('/api/dimensions/'+persona+'/analyze',{method:'POST'});
  const d=await r.json();
  if(d.ok){currentDimensions=d.dimensions;renderDimensionsRadar(currentDimensions);renderDimensionsList(currentDimensions);toast('分析完成');loadDimensionsHistory();}
  else toast(d.msg||'分析失败',true);
}

async function restoreDimensionsBaseline(){
  const persona=document.getElementById('dimPersonaSelect').value;
  if(!persona)return;
  if(!confirm('确定恢复到创建人设时的默认性格？'))return;
  const r=await fetch('/api/dimensions/'+persona+'/restore-baseline',{method:'POST'});
  const d=await r.json();
  if(d.ok){currentDimensions=d.dimensions;renderDimensionsRadar(currentDimensions);renderDimensionsList(currentDimensions);toast('已恢复默认性格');loadDimensionsHistory();}
}

async function loadDimensionsHistory(){
  const persona=document.getElementById('dimPersonaSelect').value;
  if(!persona)return;
  const r=await fetch('/api/dimensions/'+persona+'/history?hours=8');
  const history=await r.json();
  const sel=document.getElementById('dimHistorySelect');
  if(!sel)return;
  sel.innerHTML='<option value="">选择历史记录...</option>';
  history.forEach(h=>{
    const opt=document.createElement('option');
    opt.value=h.id;
    const dims=JSON.parse(h.dimensions);
    const top3=Object.entries(dims).sort((a,b)=>Math.abs(b[1]-50)-Math.abs(a[1]-50)).slice(0,3).map(([k,v])=>dimensionsInfo[k]?dimensionsInfo[k].name+':'+v:k).join(', ');
    opt.textContent=`${h.timestamp} [${h.source}] ${h.note||''} (${top3})`;
    opt.dataset.dims=h.dimensions;
    sel.appendChild(opt);
  });
}

function previewHistoryDimensions(){
  const sel=document.getElementById('dimHistorySelect');
  const opt=sel.selectedOptions[0];
  if(!opt||!opt.value){document.getElementById('dimHistoryPreview').innerHTML='';return;}
  const histDims=JSON.parse(opt.dataset.dims);
  renderDimensionsRadar(currentDimensions,histDims,opt.textContent.split('[')[0].trim());
  document.getElementById('dimHistoryPreview').innerHTML=`<div style="margin-top:8px;">选中时间: ${opt.textContent.split('[')[0].trim()}</div>`;
}

async function rollbackDimensions(){
  const persona=document.getElementById('dimPersonaSelect').value;
  const sel=document.getElementById('dimHistorySelect');
  const hid=sel.value;
  if(!persona||!hid){toast('请选择历史记录',true);return;}
  if(!confirm('确定回退到该时间点的多维性格数据？'))return;
  const r=await fetch('/api/dimensions/'+persona+'/rollback',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({history_id:parseInt(hid)})});
  const d=await r.json();
  if(d.ok){currentDimensions=d.dimensions;renderDimensionsRadar(currentDimensions);renderDimensionsList(currentDimensions);toast('已回退');loadDimensionsHistory();}
  else toast(d.msg||'回退失败',true);
}

// ===== 人格心理画像页面 =====
let personaPsychologyInfo={}, currentPsychologyDims={};

async function loadPersonaPsychologyPersonaSelect(){
  const sel=document.getElementById('psyPersonaSelect');
  if(!sel)return;
  const r=await fetch('/api/personas');
  const list=await r.json();
  sel.innerHTML=list.map(p=>`<option value="${p}">${p}</option>`).join('');
  if(currentPersona&&list.includes(currentPersona))sel.value=currentPersona;
}

async function loadPersonaPsychologyPage(){
  await loadPersonaPsychologyPersonaSelect();
  await loadPersonaPsychologyData();
}

async function loadPersonaPsychologyData(){
  const persona=document.getElementById('psyPersonaSelect').value;
  if(!persona)return;
  if(!personaPsychologyInfo||!Object.keys(personaPsychologyInfo).length){
    const ri=await fetch('/api/persona-psychology/info');
    personaPsychologyInfo=await ri.json();
  }
  const r=await fetch('/api/persona-psychology/'+persona);
  const d=await r.json();
  currentPsychologyDims=d.dimensions||{};
  renderPsychologyDimensions(currentPsychologyDims);
}

function renderPsychologyDimensions(dims){
  const container=document.getElementById('psyDimensionsList');
  if(!container)return;
  let html='';
  for(const[key,info]of Object.entries(personaPsychologyInfo)){
    const val=dims[key]!==undefined?dims[key]:info.default;
    if(info.type==='range'){
      html+=`<div style="margin-bottom:14px;padding:8px;background:var(--amber-bg);border-radius:6px;" title="${info.description}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span style="font-size:12px;">${info.name}</span>
          <span style="font-size:12px;color:var(--amber);font-family:'JetBrains Mono',monospace;">${val}</span>
        </div>
        <input type="range" min="${info.min}" max="${info.max}" value="${val}" data-key="${key}" style="width:100%;accent-color:var(--amber);" oninput="updatePsyDim('${key}',this.value,'range')">
        <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${info.description}</div>
      </div>`;
    }else if(info.type==='choice'){
      html+=`<div style="margin-bottom:14px;padding:8px;background:var(--amber-bg);border-radius:6px;" title="${info.description}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <span style="font-size:12px;">${info.name}</span>
          <span style="font-size:12px;color:var(--amber);">${val}</span>
        </div>
        <select class="form-input" data-key="${key}" style="width:100%;" onchange="updatePsyDim('${key}',this.value,'choice')">
          ${info.options.map(o=>`<option value="${o}" ${o===val?'selected':''}>${o}</option>`).join('')}
        </select>
        <div style="font-size:10px;color:var(--text-dim);margin-top:2px;">${info.description}</div>
      </div>`;
    }
  }
  container.innerHTML=html;
}

function updatePsyDim(key,val,type){
  currentPsychologyDims[key]=type==='range'?parseInt(val):val;
  const el=document.querySelector(`#psyDimensionsList [data-key='${key}']`);
  if(el&&type==='range')el.parentElement.querySelector('span:last-child').textContent=val;
  if(el&&type==='choice')el.parentElement.querySelector('span:last-child').textContent=val;
}

async function savePersonaPsychology(){
  const persona=document.getElementById('psyPersonaSelect').value;
  if(!persona)return;
  const r=await fetch('/api/persona-psychology/'+persona,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({dimensions:currentPsychologyDims,note:'手动调整'})});
  const d=await r.json();
  toast(d.msg||'已保存');
}

async function createPsychologyBaseline(){
  const persona=document.getElementById('psyPersonaSelect').value;
  if(!persona)return;
  const r=await fetch('/api/persona-psychology/'+persona+'/baseline',{method:'POST'});
  const d=await r.json();
  if(d.ok){currentPsychologyDims=d.dimensions;renderPsychologyDimensions(currentPsychologyDims);toast('基线心理画像已生成');}
  else toast(d.msg||'生成失败',true);
}

async function restorePsychologyBaseline(){
  const persona=document.getElementById('psyPersonaSelect').value;
  if(!persona)return;
  if(!confirm('确定恢复到创建人设时的基线心理状态？'))return;
  const r=await fetch('/api/persona-psychology/'+persona+'/restore',{method:'POST'});
  const d=await r.json();
  if(d.ok){currentPsychologyDims=d.dimensions;renderPsychologyDimensions(currentPsychologyDims);toast('已恢复基线心理状态');}
}

// ===== 账号绑定页面 =====
let allBindings=[], editingBinding=null;

async function loadAccountBindingPage(){
  await loadAccountBindings();
}

async function loadAccountBindings(){
  const r=await fetch('/api/account-binding/list');
  allBindings=await r.json();
  renderAccountBindings();
}

function renderAccountBindings(){
  const container=document.getElementById('accountBindingList');
  if(!container)return;
  if(!allBindings.length){
    container.innerHTML='<div style="text-align:center;padding:40px;color:var(--text-dim);">暂无账号绑定配置</div>';
    return;
  }
  let html='<table class="backup-table"><thead><tr><th>账号ID</th><th>人设</th><th>关系类型</th><th>亲密度</th><th>称呼</th><th>信任度</th><th>操作</th></tr></thead><tbody>';
  allBindings.forEach(b=>{
    html+=`<tr>
      <td>${b.account_id}</td>
      <td>${b.persona_name}</td>
      <td>${b.relationship_type}</td>
      <td>${b.intimacy_level}</td>
      <td>${b.custom_name||b.custom_honorific||'-'}</td>
      <td>${b.trust_level}</td>
      <td>
        <button class="btn btn-sm" onclick="editAccountBinding('${b.account_id}','${b.persona_name}')">编辑</button>
        <button class="btn btn-sm btn-red" onclick="deleteAccountBinding('${b.account_id}','${b.persona_name}')">删除</button>
      </td>
    </tr>`;
  });
  html+='</tbody></table>';
  container.innerHTML=html;
}

async function editAccountBinding(accountId,personaName){
  const r=await fetch(`/api/account-binding/${accountId}/${personaName}`);
  editingBinding=await r.json();
  const form=document.getElementById('bindingEditForm');
  form.innerHTML=`
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">账号ID</label>
    <input id="bindAccountId" class="form-input" value="${editingBinding.account_id}" style="width:100%;" ${accountId?'readonly':''}></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">人设名</label>
    <select id="bindPersonaName" class="form-input" style="width:100%;"></select></div>
    <div id="bindPersonaInfo" style="margin-bottom:12px;padding:8px;background:var(--amber-bg);border-radius:6px;font-size:11px;color:var(--text-dim);">加载中...</div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">关系类型</label>
    <select id="bindRelType" class="form-input" style="width:100%;">
      ${['朋友','恋人','家人','同事','师生','陌生人','自定义'].map(t=>`<option ${t===editingBinding.relationship_type?'selected':''}>${t}</option>`).join('')}
    </select></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">亲密度 (0-100)</label>
    <input id="bindIntimacy" type="range" min="0" max="100" value="${editingBinding.intimacy_level}" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">自定义称呼</label>
    <input id="bindCustomName" class="form-input" value="${editingBinding.custom_name}" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">信任度 (0-100)</label>
    <input id="bindTrust" type="range" min="0" max="100" value="${editingBinding.trust_level}" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">互动风格</label>
    <select id="bindStyle" class="form-input" style="width:100%;">
      ${['默认','亲密','正式','随意','温柔','严厉'].map(s=>`<option ${s===editingBinding.interaction_style?'selected':''}>${s}</option>`).join('')}
    </select></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">备注</label>
    <input id="bindNotes" class="form-input" value="${editingBinding.notes||''}" style="width:100%;"></div>
  `;
  // 加载人设列表
  fetch('/api/personas').then(r=>r.json()).then(list=>{
    var sel=document.getElementById('bindPersonaName');
    if(sel){
      sel.innerHTML=list.map(p=>`<option value="${p}" ${p===personaName?'selected':''}>${p}</option>`).join('');
      sel.onchange=function(){loadPersonaBindingInfo(this.value);};
    }
  });
  loadPersonaBindingInfo(personaName);
  document.getElementById('bindingEditOverlay').style.display='flex';
}

async function loadPersonaBindingInfo(personaName){
  var el=document.getElementById('bindPersonaInfo');
  if(!el||!personaName){if(el)el.textContent='';return;}
  try{
    var r=await fetch('/api/persona/bindings');
    var d=await r.json();
    var parts=[];
    if(d.scene_group)parts.push('场景组: '+d.scene_group);
    if(d.tone_group)parts.push('语气组: '+d.tone_group);
    if(d.audio_group)parts.push('音频组: '+d.audio_group);
    el.innerHTML='<strong>'+personaName+'</strong> 的绑定配置: '+(parts.length?parts.join(' | '):'暂无');
  }catch(e){el.textContent='';}
}

async function saveAccountBinding(){
  const accountId=document.getElementById('bindAccountId').value;
  const personaName=document.getElementById('bindPersonaName').value;
  if(!accountId||!personaName){toast('账号ID和人设名不能为空',true);return;}
  const data={
    relationship_type:document.getElementById('bindRelType').value,
    intimacy_level:parseInt(document.getElementById('bindIntimacy').value),
    custom_name:document.getElementById('bindCustomName').value,
    trust_level:parseInt(document.getElementById('bindTrust').value),
    interaction_style:document.getElementById('bindStyle').value,
    notes:document.getElementById('bindNotes').value,
  };
  const r=await fetch(`/api/account-binding/${accountId}/${personaName}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const d=await r.json();
  document.getElementById('bindingEditOverlay').style.display='none';
  toast(d.msg||'已保存');
  loadAccountBindings();
}

function showAddAccountBinding(){
  editingBinding={account_id:'',persona_name:currentPersona||'',relationship_type:'朋友',intimacy_level:50,custom_name:'',trust_level:50,interaction_style:'默认',notes:''};
  // 直接显示表单，不调用API
  var form=document.getElementById('bindingEditForm');
  form.innerHTML=`
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">账号ID（如QQ号）</label>
    <input id="bindAccountId" class="form-input" value="" placeholder="输入QQ号" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">人设名</label>
    <select id="bindPersonaName" class="form-input" style="width:100%;"></select></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">关系类型</label>
    <select id="bindRelType" class="form-input" style="width:100%;">
      ${['朋友','恋人','家人','同事','师生','陌生人','自定义'].map(t=>`<option ${t==='朋友'?'selected':''}>${t}</option>`).join('')}
    </select></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">亲密度 (0-100)</label>
    <input id="bindIntimacy" type="range" min="0" max="100" value="50" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">自定义称呼</label>
    <input id="bindCustomName" class="form-input" value="" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">信任度 (0-100)</label>
    <input id="bindTrust" type="range" min="0" max="100" value="50" style="width:100%;"></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">互动风格</label>
    <select id="bindStyle" class="form-input" style="width:100%;">
      ${['默认','亲密','正式','随意','温柔','严厉'].map(s=>`<option ${s==='默认'?'selected':''}>${s}</option>`).join('')}
    </select></div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">绑定人设配置</label>
    <div style="font-size:11px;color:var(--text-dim);margin-bottom:4px;">选择人设后将连带绑定该人设的语气、场景库和音频库</div>
    </div>
    <div style="margin-bottom:12px;"><label style="font-size:12px;color:var(--text-dim);">备注</label>
    <input id="bindNotes" class="form-input" value="" style="width:100%;"></div>
  `;
  // 加载人设列表到下拉菜单
  fetch('/api/personas').then(r=>r.json()).then(list=>{
    var sel=document.getElementById('bindPersonaName');
    if(sel)sel.innerHTML=list.map(p=>`<option value="${p}" ${p===currentPersona?'selected':''}>${p}</option>`).join('');
  });
  document.getElementById('bindingEditOverlay').style.display='flex';
}

async function deleteAccountBinding(accountId,personaName){
  if(!confirm(`确定删除 ${accountId} 与 ${personaName} 的绑定？`))return;
  await fetch(`/api/account-binding/${accountId}/${personaName}`,{method:'DELETE'});
  toast('已删除');
  loadAccountBindings();
}

// 高级设置页面的 persona select 在 switchPage 时按需加载

// ===== 统一记忆账本 =====
let ledgerRows=[];

async function loadMemoryLedgerPage(){
  await loadMemoryLedger();
}

function ledgerEsc(v){
  return String(v===undefined||v===null?'':v).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
  });
}

async function loadMemoryLedger(){
  const user=document.getElementById('ledgerUserFilter').value.trim();
  const persona=document.getElementById('ledgerPersonaFilter').value.trim();
  const q=document.getElementById('ledgerQuery').value.trim();
  const type=document.getElementById('ledgerTypeFilter').value;
  const status=document.getElementById('ledgerStatusFilter').value;
  const params=new URLSearchParams({limit:'200',include_pending:'1'});
  if(user)params.set('user_id',user);
  if(persona)params.set('persona',persona);
  if(q)params.set('q',q);
  if(type)params.set('type',type);
  if(status)params.set('status',status);
  const r=await fetch('/api/memory-ledger/items?'+params.toString());
  const d=await r.json();
  ledgerRows=d.data||[];
  renderMemoryLedger();
}

function renderMemoryLedger(){
  const body=document.getElementById('ledgerBody');
  const empty=document.getElementById('ledgerEmpty');
  const count=document.getElementById('ledgerCount');
  count.textContent=ledgerRows.length+' 条';
  if(!ledgerRows.length){
    body.innerHTML='';
    empty.style.display='block';
    return;
  }
  empty.style.display='none';
  body.innerHTML=ledgerRows.map(function(m){
    const id=ledgerEsc(m.memory_id);
    const status=ledgerEsc(m.consent_status||'');
    const badgeColor=status==='confirmed'?'var(--green)':(status==='pending'?'var(--amber)':(status==='rejected'?'var(--red)':'var(--cyan)'));
    const supersede=m.supersedes?'<div style="font-size:10px;color:var(--text-dim);margin-top:4px;">覆盖 '+ledgerEsc(m.supersedes).slice(0,8)+'</div>':'';
    return '<tr>'+
      '<td><span style="color:'+badgeColor+';font-weight:600;">'+status+'</span><div style="font-size:10px;color:var(--text-dim);">'+ledgerEsc(m.sensitivity||'low')+'</div></td>'+
      '<td>'+ledgerEsc(m.type||'fact')+'</td>'+
      '<td style="min-width:260px;white-space:normal;">'+ledgerEsc(m.content||'')+supersede+'<div style="font-size:10px;color:var(--text-dim);margin-top:4px;">'+ledgerEsc(m.user_id||'')+' / '+ledgerEsc(m.persona||'')+'</div></td>'+
      '<td style="max-width:260px;white-space:normal;color:var(--text-dim);">'+ledgerEsc(m.evidence||'')+'</td>'+
      '<td>'+Number(m.confidence||0).toFixed(2)+(m.relevance_score!==undefined?'<div style="font-size:10px;color:var(--text-dim);">R '+Number(m.relevance_score||0).toFixed(2)+'</div>':'')+'</td>'+
      '<td>v'+ledgerEsc(m.version||1)+'</td>'+
      '<td style="font-size:11px;">'+ledgerEsc(m.created_at||'')+'<div style="color:var(--text-dim);">'+ledgerEsc(m.db_path||'')+'</div></td>'+
      '<td style="min-width:220px;">'+
        '<button class="btn" style="padding:3px 8px;font-size:10px;" onclick="setLedgerConsent(\''+id+'\',\'confirmed\')">确认</button> '+
        '<button class="btn" style="padding:3px 8px;font-size:10px;" onclick="setLedgerConsent(\''+id+'\',\'pending\')">挂起</button> '+
        '<button class="btn" style="padding:3px 8px;font-size:10px;" onclick="supersedeLedger(\''+id+'\')">覆盖</button> '+
        '<button class="btn btn-danger" style="padding:3px 8px;font-size:10px;" onclick="deleteLedger(\''+id+'\')">删除</button>'+
      '</td>'+
    '</tr>';
  }).join('');
}

async function setLedgerConsent(id,status){
  const r=await fetch('/api/memory-ledger/consent',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({memory_id:id,status:status})});
  const d=await r.json();
  toast(d.msg||'已更新',!d.ok);
  loadMemoryLedger();
}

async function supersedeLedger(id){
  const old=ledgerRows.find(function(m){return m.memory_id===id;});
  const content=prompt('输入新的记忆内容，用它覆盖旧记忆：',old?old.content:'');
  if(!content||!content.trim())return;
  const r=await fetch('/api/memory-ledger/supersede',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({memory_id:id,content:content.trim(),consent_status:'confirmed'})});
  const d=await r.json();
  toast(d.msg||'已覆盖',!d.ok);
  loadMemoryLedger();
}

async function deleteLedger(id){
  if(!confirm('确定删除这条记忆？'))return;
  const r=await fetch('/api/memory-ledger/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({memory_id:id})});
  const d=await r.json();
  toast(d.msg||'已删除',!d.ok);
  loadMemoryLedger();
}

// ===== 心理健康与分析 =====
function _chatImportFilters(){
  const uidEl=document.getElementById('chatImportUserId');
  const personaEl=document.getElementById('chatImportPersona');
  return {
    user_id:(uidEl&&uidEl.value?uidEl.value:'').trim(),
    persona:(personaEl&&personaEl.value?personaEl.value:'').trim(),
  };
}

function _chatImportRequireUser(){
  const filters=_chatImportFilters();
  if(!filters.user_id){
    toast('请先输入用户ID', true);
    return null;
  }
  return filters;
}

function loadChatImportPage(){
  refreshChatImportDashboard();
}

function _renderChatImportStats(stats){
  const box=document.getElementById('chatImportStatsBox');
  if(!box) return;
  const total=Number((stats||{}).total_records||0);
  const src=Number((stats||{}).total_sources||0);
  box.innerHTML=
    '<div style="display:grid;grid-template-columns:repeat(2,minmax(120px,1fr));gap:10px;">'+
      '<div style="padding:10px;background:var(--bg-deep);border:1px solid var(--line);border-radius:6px;"><div style="font-size:11px;color:var(--text-dim);">消息条数</div><div style="font-size:20px;font-weight:700;">'+total+'</div></div>'+
      '<div style="padding:10px;background:var(--bg-deep);border:1px solid var(--line);border-radius:6px;"><div style="font-size:11px;color:var(--text-dim);">导入批次</div><div style="font-size:20px;font-weight:700;">'+src+'</div></div>'+
    '</div>';
}

function _renderChatImportAnalysis(rows){
  const box=document.getElementById('chatImportAnalysisBox');
  if(!box) return;
  if(!rows||!rows.length){
    box.innerHTML='暂无分析记录';
    return;
  }
  const top=rows[0]||{};
  const keywords=Array.isArray(top.topic_keywords)?top.topic_keywords.slice(0,8):[];
  const participants=top.participants&&typeof top.participants==='object'?Object.keys(top.participants):[];
  box.innerHTML=
    '<div style="font-size:12px;line-height:1.7;">'+
      '<div><span style="color:var(--text-dim);">时间范围:</span> '+ledgerEsc(top.time_range||'未知')+'</div>'+
      '<div><span style="color:var(--text-dim);">消息总量:</span> '+Number(top.total_messages||0)+'</div>'+
      '<div><span style="color:var(--text-dim);">参与者:</span> '+(participants.length?participants.map(ledgerEsc).join(' / '):'暂无')+'</div>'+
      '<div style="margin-top:8px;"><span style="color:var(--text-dim);">关键词:</span> '+(keywords.length?keywords.map(ledgerEsc).join('、'):'暂无')+'</div>'+
    '</div>';
}

function _renderChatImportItems(rows){
  const box=document.getElementById('chatImportItemsBox');
  if(!box) return;
  if(!rows||!rows.length){
    box.innerHTML='暂无消息';
    return;
  }
  box.innerHTML=rows.slice(0,40).map(function(item){
    return '<div style="padding:8px 10px;border-bottom:1px solid var(--line);font-size:12px;line-height:1.65;">'+
      '<div style="display:flex;justify-content:space-between;gap:10px;color:var(--text-dim);font-size:11px;">'+
        '<span>'+ledgerEsc(item.sender||'未知')+' ('+ledgerEsc(item.sender_id||'')+')</span>'+
        '<span>'+ledgerEsc(item.timestamp||item.created_at||'')+'</span>'+
      '</div>'+
      '<div>'+ledgerEsc(item.content||'')+'</div>'+
    '</div>';
  }).join('');
}

async function refreshChatImportDashboard(){
  const filters=_chatImportFilters();
  if(!filters.user_id){
    _renderChatImportStats({total_records:0,total_sources:0});
    _renderChatImportAnalysis([]);
    _renderChatImportItems([]);
    const coldBox=document.getElementById('chatImportColdstartBox');
    if(coldBox)coldBox.innerHTML='暂无数据';
    return;
  }
  const params=new URLSearchParams({user_id:filters.user_id,limit:'20'});
  if(filters.persona) params.set('persona',filters.persona);
  try{
    const [statsRes,analysisRes,itemsRes]=await Promise.all([
      fetch('/api/chat-record/stats?'+params.toString()),
      fetch('/api/chat-record/analysis?'+params.toString()),
      fetch('/api/chat-record/items?'+params.toString()),
    ]);
    const statsJson=await statsRes.json();
    const analysisJson=await analysisRes.json();
    const itemsJson=await itemsRes.json();
    _renderChatImportStats((statsJson&&statsJson.data)||{total_records:0,total_sources:0});
    _renderChatImportAnalysis((analysisJson&&analysisJson.data)||[]);
    _renderChatImportItems((itemsJson&&itemsJson.data)||[]);
  }catch(e){
    toast('聊天记录看板读取失败', true);
  }
}

async function submitChatImportText(){
  const filters=_chatImportRequireUser();
  if(!filters) return;
  const textEl=document.getElementById('chatImportText');
  const sourceEl=document.getElementById('chatImportSourceName');
  const text=(textEl&&textEl.value?textEl.value:'').trim();
  if(!text){
    toast('请粘贴聊天记录', true);
    return;
  }
  const body={
    user_id:filters.user_id,
    persona:filters.persona,
    text:text,
    source_name:(sourceEl&&sourceEl.value?sourceEl.value.trim():'')||'manual_text',
  };
  try{
    const res=await fetch('/api/chat-record/import_text',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await res.json();
    toast(data.msg||'导入完成', !data.ok);
    if(data.ok){
      if(textEl) textEl.value='';
      refreshChatImportDashboard();
    }
  }catch(e){
    toast('导入失败', true);
  }
}

async function submitChatImportFile(){
  const filters=_chatImportRequireUser();
  if(!filters) return;
  const input=document.getElementById('chatImportFile');
  if(!input||!input.files||!input.files.length){
    toast('请先选择文件', true);
    return;
  }
  const formData=new FormData();
  formData.append('user_id', filters.user_id);
  formData.append('persona', filters.persona||'');
  formData.append('file', input.files[0]);
  try{
    const res=await fetch('/api/chat-record/import_file',{method:'POST',body:formData});
    const data=await res.json();
    toast(data.msg||'导入完成', !data.ok);
    if(data.ok){
      input.value='';
      refreshChatImportDashboard();
    }
  }catch(e){
    toast('上传失败', true);
  }
}

function _renderChatColdstartResult(data){
  const box=document.getElementById('chatImportColdstartBox');
  if(!box)return;
  const payload=data||{};
  const candidates=Array.isArray(payload.candidates)?payload.candidates:[];
  const inserted=payload.inserted||{};
  const keywords=Array.isArray(payload.keywords)?payload.keywords:[];
  if(!candidates.length){
    box.innerHTML='暂无冷启动摘要';
    return;
  }
  box.innerHTML=
    '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">样本数: '+Number(payload.sample_size||0)+' / 关键词: '+(keywords.length?keywords.map(ledgerEsc).join('、'):'暂无')+'</div>'+
    '<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">已入账: memory_ledger '+Number(inserted.ledger||0)+' 条，long_term_memory '+Number(inserted.long_term||0)+' 条</div>'+
    candidates.map(function(item){
      return '<div style="padding:8px 10px;border-bottom:1px solid var(--line);font-size:12px;line-height:1.65;">'+
        '<div style="color:var(--text-dim);margin-bottom:2px;">['+ledgerEsc(item.memory_type||'fact')+'] '+ledgerEsc(item.consent_status||'auto')+' / conf '+Number(item.confidence||0).toFixed(2)+'</div>'+
        '<div>'+ledgerEsc(item.content||'')+'</div>'+
      '</div>';
    }).join('');
}

async function generateChatColdstartSummary(){
  const filters=_chatImportRequireUser();
  if(!filters)return;
  const box=document.getElementById('chatImportColdstartBox');
  if(box)box.innerHTML='<span style="color:var(--text-dim);">生成中...</span>';
  try{
    const res=await fetch('/api/chat-record/coldstart_summary',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({user_id:filters.user_id,persona:filters.persona,limit:200}),
    });
    const data=await res.json();
    toast(data.msg||'处理完成', !data.ok);
    if(data.ok)_renderChatColdstartResult(data.data||{});
    else if(box)box.innerHTML='<span style="color:var(--red);">生成失败</span>';
  }catch(e){
    toast('生成失败', true);
    if(box)box.innerHTML='<span style="color:var(--red);">生成失败</span>';
  }
}

async function loadMentalHealthPage(){
  // 加载用户列表
  var r1=await fetch('/api/mental-health/users');
  var d1=await r1.json();
  var userSel=document.getElementById('mhUserSelect');
  userSel.innerHTML='<option value="">选择用户</option>'+((d1.users||[]).map(function(u){return '<option value="'+u+'">'+u+'</option>'}).join(''));
  // 加载人设列表
  var r2=await fetch('/api/mental-health/personas');
  var d2=await r2.json();
  var personaSel=document.getElementById('mhPersonaSelect');
  personaSel.innerHTML=(d2.personas||[]).map(function(p){return '<option value="'+p+'">'+p+'</option>'}).join('');
  // 自动加载数据
  if(userSel.value) loadMentalHealthData();
}

async function loadMentalHealthData(){
  var userId=document.getElementById('mhUserSelect').value;
  var persona=document.getElementById('mhPersonaSelect').value;
  if(!userId||!persona){document.getElementById('mhContent').innerHTML='<div style="padding:20px;color:var(--text-dim);">请选择用户和人设</div>';return;}
  var r=await fetch('/api/mental-health/data?user_id='+encodeURIComponent(userId)+'&persona='+encodeURIComponent(persona));
  var d=await r.json();
  if(!d.ok||!d.data){
    // 没有数据，尝试自动生成
    document.getElementById('mhContent').innerHTML='<div style="padding:20px;color:var(--text-dim);">正在自动生成分析...</div>';
    var r2=await fetch('/api/mental-health/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,persona:persona})});
    var d2=await r2.json();
    if(d2.ok&&d2.data){renderMentalHealth(d2.data);}else{document.getElementById('mhContent').innerHTML='<div style="padding:20px;color:var(--text-dim);">'+(d2.error||'暂无数据，请先多聊几次')+'</div>';}
    return;
  }
  renderMentalHealth(d.data);
}

function renderMentalHealth(data){
  var el=document.getElementById('mhContent');
  var chart=data.chart||{};
  var analysis=data.analysis||{};
  var suggestions=data.suggestions||'';
  var evidence=analysis.last_evidence||[];
  var confidence=(analysis.last_confidence!==undefined&&analysis.last_confidence!==null)?Number(analysis.last_confidence):0;
  var source=analysis.last_source||'recent_chat';
  var html='<div style="display:flex;gap:24px;flex-wrap:wrap;">';
  // 雷达图
  html+='<div class="glass-panel" style="flex:1;min-width:400px;"><div class="panel-header"><div class="panel-title">性格维度雷达图</div></div>';
  html+='<div class="panel-body" style="display:flex;justify-content:center;padding:20px;"><canvas id="mhRadarChart" width="400" height="400"></canvas></div></div>';
  // 画像信息
  html+='<div class="glass-panel" style="flex:1;min-width:350px;"><div class="panel-header"><div class="panel-title">用户画像概览</div></div><div class="panel-body">';
  html+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">';
  var fields=[['用户类型',chart.user_type],['情绪稳定性',chart.emotion_stability],['沟通风格',chart.communication],['心理状态',chart.mental_state],['依恋风格',chart.attachment],['应对方式',chart.coping]];
  fields.forEach(function(f){
    html+='<div style="background:var(--bg-deep);padding:12px;border-radius:6px;"><div style="font-size:11px;color:var(--text-dim);">'+f[0]+'</div><div style="font-size:16px;font-weight:600;margin-top:4px;">'+(f[1]||'未知')+'</div></div>';
  });
  html+='</div>';
  // 性格维度数值
  if(chart.radar&&chart.radar.labels){
    html+='<div style="margin-top:16px;"><div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">性格维度：</div>';
    chart.radar.labels.forEach(function(label,i){
      var val=chart.radar.values[i]||0;
      var barWidth=val+'%';
      html+='<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;"><span style="width:60px;font-size:12px;">'+label+'</span>';
      html+='<div style="flex:1;height:16px;background:var(--bg-deep);border-radius:3px;overflow:hidden;"><div style="width:'+barWidth+';height:100%;background:var(--amber);border-radius:3px;"></div></div>';
      html+='<span style="width:30px;font-size:12px;text-align:right;">'+val+'</span></div>';
    });
    html+='</div>';
  }
  // 解释性元数据
  html+='<div style="margin-top:16px;padding:12px;background:var(--bg-deep);border-radius:6px;border:1px solid var(--line);">';
  html+='<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">画像判断依据</div>';
  html+='<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px;">';
  html+='<div><span style="font-size:11px;color:var(--text-dim);">置信度</span><div style="font-size:15px;font-weight:600;">'+(confidence?confidence.toFixed(2):'暂无')+'</div></div>';
  html+='<div><span style="font-size:11px;color:var(--text-dim);">来源</span><div style="font-size:15px;font-weight:600;">'+source+'</div></div>';
  html+='</div>';
  if(evidence&&evidence.length){
    html+='<div style="font-size:11px;color:var(--text-dim);margin-bottom:6px;">最近证据</div>';
    evidence.slice(0,3).forEach(function(ev){
      html+='<div style="font-size:12px;line-height:1.6;margin-bottom:4px;color:var(--text);">• '+String(ev).replace(/</g,'&lt;')+'</div>';
    });
  }else{
    html+='<div style="font-size:12px;color:var(--text-dim);">暂无证据记录，等待下一次心理画像分析。</div>';
  }
  html+='</div>';
  html+='</div></div>';
  // AI 分析建议
  html+='<div class="glass-panel" style="flex:1;min-width:100%;"><div class="panel-header"><div class="panel-title">AI 心理健康分析与建议</div></div>';
  html+='<div class="panel-body" style="white-space:pre-wrap;line-height:1.8;">'+(suggestions||'暂无分析').replace(/</g,'&lt;')+'</div></div>';
  html+='<div class="glass-panel" style="flex:1;min-width:100%;"><div class="panel-header"><div class="panel-title">心理画像变化历史</div></div>';
  html+='<div class="panel-body" id="mhHistoryBox" style="min-height:80px;color:var(--text-dim);">正在加载历史...</div></div>';
  html+='<div style="font-size:11px;color:var(--text-dim);margin-top:8px;">更新时间：'+(data.updated_at||'未知')+'</div>';
  html+='</div>';
  el.innerHTML=html;
  // 渲染雷达图
  if(chart.radar&&chart.radar.labels&&chart.radar.values){
    var ctx=document.getElementById('mhRadarChart');
    if(ctx){
      new Chart(ctx.getContext('2d'),{type:'radar',data:{labels:chart.radar.labels,datasets:[{label:'性格维度',data:chart.radar.values,backgroundColor:'rgba(255,255,255,0.1)',borderColor:'rgba(255,255,255,0.6)',borderWidth:1,pointBackgroundColor:'rgba(255,255,255,0.8)'}]},options:{scales:{r:{min:0,max:100,ticks:{stepSize:20,color:'rgba(255,255,255,0.5)',backdropColor:'transparent'},grid:{color:'rgba(255,255,255,0.1)'},pointLabels:{color:'rgba(255,255,255,0.8)',font:{size:12}}}},plugins:{legend:{display:false}}}});
    }
  }
  loadMentalHealthHistory(data.user_id||document.getElementById('mhUserSelect').value);
}

async function loadMentalHealthHistory(userId){
  var box=document.getElementById('mhHistoryBox');
  if(!box||!userId)return;
  try{
    var r=await fetch('/api/mental-health/history?user_id='+encodeURIComponent(userId)+'&limit=20');
    var d=await r.json();
    if(!d.ok){box.innerHTML='<div style="color:var(--text-dim);">历史读取失败</div>';return;}
    var rows=d.data||[];
    if(!rows.length){box.innerHTML='<div style="color:var(--text-dim);">暂无画像变化历史</div>';return;}
    var html='<div style="display:flex;flex-direction:column;gap:8px;">';
    rows.forEach(function(row){
      var ev=row.evidence||[];
      html+='<div style="padding:10px;background:var(--bg-deep);border-radius:6px;border:1px solid var(--line);">';
      html+='<div style="display:flex;justify-content:space-between;gap:12px;align-items:center;">';
      html+='<div style="font-weight:600;">'+(row.dimension||'未知维度')+'</div>';
      html+='<div style="font-size:11px;color:var(--text-dim);">'+(row.timestamp||'')+' / '+(row.source||'recent_chat')+' / '+Number(row.confidence||0).toFixed(2)+'</div>';
      html+='</div>';
      html+='<div style="font-size:12px;color:var(--text-dim);margin-top:4px;">'+String(row.old_value||'')+' → '+String(row.new_value||'')+'</div>';
      if(ev.length){
        html+='<div style="font-size:12px;margin-top:6px;line-height:1.6;">证据：'+ev.slice(0,2).map(function(x){return String(x).replace(/</g,'&lt;')}).join('；')+'</div>';
      }
      html+='</div>';
    });
    html+='</div>';
    box.innerHTML=html;
  }catch(e){
    box.innerHTML='<div style="color:var(--text-dim);">历史读取失败</div>';
  }
}

async function generateMentalHealth(){
  var userId=document.getElementById('mhUserSelect').value;
  var persona=document.getElementById('mhPersonaSelect').value;
  if(!userId||!persona){toast('请先选择用户和人设',true);return;}
  toast('正在生成分析，请稍候...');
  var r=await fetch('/api/mental-health/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,persona:persona})});
  var d=await r.json();
  if(d.ok){toast('分析已生成');renderMentalHealth(d.data);}else{toast(d.error||'生成失败',true);}
}

async function deleteMentalHealthData(){
  var userId=document.getElementById('mhUserSelect').value;
  var persona=document.getElementById('mhPersonaSelect').value;
  if(!userId||!persona){toast('请先选择用户和人设',true);return;}
  showConfirm('删除数据','确定要删除 '+userId+' 的心理健康分析数据吗？',async function(){
    var r=await fetch('/api/mental-health/delete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:userId,persona:persona})});
    var d=await r.json();
    toast(d.msg);
    document.getElementById('mhContent').innerHTML='<div style="padding:20px;color:var(--text-dim);">数据已删除</div>';
  });
}

async function openMentalHealthDb(){
  await fetch('/api/mental-health/open-db',{method:'POST'});
}

</script>

<!-- 确认弹窗 -->
<div class="confirm-overlay" id="confirmOverlay">
  <div class="confirm-box">
    <div class="confirm-title" id="confirmTitle">确认操作</div>
    <div class="confirm-text" id="confirmText"></div>
    <div class="confirm-actions">
      <button class="confirm-cancel" onclick="closeConfirm()">取消</button>
      <button class="confirm-ok" id="confirmOk">确认</button>
    </div>
  </div>
</div>


<!-- 起名依据弹窗 -->
<div class="confirm-overlay" id="namingPopup" style="z-index:100000;">
  <div class="confirm-box" style="border-color:var(--amber);max-width:480px;">
    <div class="confirm-title" style="color:var(--amber);">推荐阅读</div>
    <div class="confirm-text">
      <div style="margin-bottom:12px;">强烈推荐阅读 C.R.O.W.N. 的起名依据文档，了解项目命名灵感来源。</div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:16px;">
        <a href="CROWN命名依据.md" target="_blank" style="color:var(--amber);text-decoration:underline;">📄 打开 CROWN命名依据.md</a>
      </div>
      <div style="font-size:11px;color:var(--text-dim);">本次启动不再显示（刷新后重新提示）</div>
    </div>
    <div class="confirm-actions">
      <button class="confirm-ok" onclick="document.getElementById('namingPopup').classList.remove('show');localStorage.setItem('crown_naming_read','1');" style="border-color:var(--amber);color:var(--amber);background:rgba(255,255,255,0.05);">我知道了</button>
    </div>
  </div>
</div>

<div class="ubai-watermark">by UBAI</div>
</body>
</html>"""

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  C.R.O.W.N. // 黑冠 配置终端")
    print("  http://127.0.0.1:5050")
    print("=" * 50 + "\n")
    import threading; threading.Thread(target=_auto_shutdown_check, daemon=True).start()
    app.run(host="127.0.0.1", port=5050, debug=False)

# [0.0.4 PATCH FIX] Applied requested modifications here.
