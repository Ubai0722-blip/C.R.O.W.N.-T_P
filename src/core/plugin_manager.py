# by UBAI
"""
plugin_manager.py
插件管理器 - 发现、加载、调度插件
"""
import os
import yaml
import json
import importlib.util
import traceback
from pathlib import Path
from .plugin_base import PluginBase, PluginInfo


class PluginManager:
    """插件管理器"""

    def __init__(self, plugin_dirs: list[str] = None):
        self.plugins: dict[str, PluginBase] = {}
        self.plugin_dirs = plugin_dirs or [
            "src/plugins/builtin",
            "src/plugins/custom",
        ]
        self._log = print

    def set_logger(self, log_func):
        self._log = log_func


        self.state_file = "plugin_states.json"
        self.plugin_states = {}
        self._load_states()

    def _load_states(self):
        """从文件加载插件开关状态"""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    self.plugin_states = json.load(f)
            except Exception as e:
                self._log(f"[plugin] 读取状态文件失败: {e}")

    def _save_states(self):
        """保存插件开关状态到文件"""
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.plugin_states, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self._log(f"[plugin] 保存状态文件失败: {e}")

    # ========== 加载 ==========

    def load_all(self):
        """扫描并加载所有插件"""
        loaded = 0
        for plugin_dir in self.plugin_dirs:
            if not os.path.exists(plugin_dir):
                os.makedirs(plugin_dir, exist_ok=True)
                self._log(f"[plugin] 创建插件目录: {plugin_dir}")
                continue

            for item in sorted(Path(plugin_dir).iterdir()):
                if item.is_dir() and (item / "__init__.py").exists():
                    try:
                        self._load_plugin(item)
                        loaded += 1
                    except Exception as e:
                        self._log(f"[plugin] 加载失败 {item.name}: {e}")

        self._log(f"[plugin] 共加载 {loaded} 个插件")

    def _load_plugin(self, plugin_path: Path):
        """加载单个插件"""
        name = plugin_path.name
        init_file = plugin_path / "__init__.py"
        manifest_file = plugin_path / "manifest.yaml"

        # 读取 manifest
        manifest = {}
        if manifest_file.exists():
            with open(manifest_file, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {}

        # 检查是否禁用
        if manifest.get("enabled") is False:
            self._log(f"[plugin] 跳过已禁用的插件: {name}")
            return

        # 动态导入
        spec = importlib.util.spec_from_file_location(
            f"plugin_{name}", str(init_file)
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # 查找插件类（必须有 Plugin 类或继承 PluginBase 的类）
        plugin_class = None
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type)
                    and issubclass(attr, PluginBase)
                    and attr is not PluginBase):
                plugin_class = attr
                break

        if not plugin_class:
            self._log(f"[plugin] {name} 中未找到插件类")
            return

        # 实例化
        instance = plugin_class()
        
        # --- 新增：读取本地状态，如果没记录过，则默认 False (关闭) ---
        instance.info.enabled = self.plugin_states.get(name, False)
        self.plugin_states[name] = instance.info.enabled # 确保未记录的也写回字典
        
        self.plugins[name] = instance
        self._log(f"[plugin] 已加载: {name} v{instance.info.version} - 状态: {'开启' if instance.info.enabled else '关闭'}")
        
        # 每次加载顺手保存一次初始状态
        self._save_states()
    # ========== 匹配与处理 ==========

    async def try_handle(self, text: str, user_id: str, context: dict) -> str | None:
        """
        尝试匹配并处理插件
        按优先级排序，第一个匹配的插件处理
        """
        sorted_plugins = sorted(
            self.plugins.items(),
            key=lambda x: x[1].info.priority,
        )

        for name, plugin in sorted_plugins:
            if not plugin.info.enabled:
                continue

            # 检查前缀
            if plugin.info.require_prefix and not text.startswith("/"):
                continue

            # 检查触发词
            cmd_text = text.lstrip("/").strip()
            if plugin.info.triggers:
                matched = False
                for trigger in plugin.info.triggers:
                    if cmd_text.startswith(trigger):
                        matched = True
                        break
                if not matched:
                    continue

            # 调用插件的 match
            try:
                if plugin.match(cmd_text, user_id):
                    result = await plugin.handle(user_id, cmd_text, context)
                    if result is not None:
                        self._log(f"[plugin] {name} 处理: {text[:30]} -> {result[:50]}")
                        return result
            except Exception as e:
                self._log(f"[plugin] {name} 执行出错: {e}")
                traceback.print_exc()

        return None  # 没有插件处理

    async def notify_startup(self):
        """通知所有插件启动"""
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_startup()
            except Exception as e:
                self._log(f"[plugin] {name} 启动失败: {e}")

    async def notify_shutdown(self):
        """通知所有插件关闭"""
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_shutdown()
            except Exception as e:
                self._log(f"[plugin] {name} 关闭失败: {e}")

    async def notify_message_sent(self, user_id: str, reply: str):
        """通知所有插件消息已发送"""
        for name, plugin in self.plugins.items():
            try:
                await plugin.on_message_sent(user_id, reply)
            except:
                pass

    # ========== 管理 ==========

    def enable(self, name: str) -> bool:
        if name in self.plugins:
            self.plugins[name].info.enabled = True
            self.plugin_states[name] = True  
            self._save_states()
            return True
        return False

    def disable(self, name: str) -> bool:
        if name in self.plugins:
            self.plugins[name].info.enabled = False
            self.plugin_states[name] = False  
            self._save_states()
            return True
        return False

    def list_plugins(self) -> list[dict]:
        result = []
        for name, plugin in self.plugins.items():
            result.append({
                "name": name,
                "version": plugin.info.version,
                "description": plugin.info.description,
                "author": plugin.info.author,
                "triggers": plugin.info.triggers,
                "enabled": plugin.info.enabled,
                "priority": plugin.info.priority,
            })
        return result

    def reload(self, name: str) -> bool:
        """重新加载单个插件"""
        if name in self.plugins:
            del self.plugins[name]

        for plugin_dir in self.plugin_dirs:
            plugin_path = Path(plugin_dir) / name
            if plugin_path.exists():
                try:
                    self._load_plugin(plugin_path)
                    return True
                except Exception as e:
                    self._log(f"[plugin] 重载失败 {name}: {e}")
        return False
