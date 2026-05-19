# by UBAI
"""
scene.py
场景识别系统 - AI 驱动，从本地 YAML 加载语气和场景
"""
import yaml
from pathlib import Path
from dataclasses import dataclass
from ..core.llm import LLMClient


@dataclass
class ToneConfig:
    """语气配置"""
    id: str
    name: str
    description: str
    style: str
    verbal_tics: list[str]
    sentence_pattern: str


@dataclass
class SceneConfig:
    """场景配置"""
    id: str
    name: str
    description: str
    trigger_hint: str
    tone_id: str
    extra_hint: str


@dataclass
class SceneContext:
    """场景上下文"""
    scene: str
    style_hint: str
    emotion_modifier: str


class SceneDetector:
    """场景检测器 - AI 驱动"""

    def __init__(self, llm: LLMClient):
        self.llm = llm
        self.tones: dict[str, ToneConfig] = {}
        self.scenes: dict[str, SceneConfig] = {}
        self._load_configs()

    def _load_configs(self):
        """从 YAML 加载语气和场景配置"""
        # 加载语气库
        # 读取人设绑定的组
        import yaml as _yaml
        _cfg_path = Path("config.yaml")
        active_tone = "default"
        active_scene = "default"
        if _cfg_path.exists():
            try:
                with open(_cfg_path, "r", encoding="utf-8") as _f:
                    _cfg = _yaml.safe_load(_f) or {}
                _bindings = _cfg.get("persona_bindings", {})
                active_tone = _bindings.get("tone_group", "default")
                active_scene = _bindings.get("scene_group", "default")
            except:
                pass

        tones_path = Path(f"data/tone_groups/{active_tone}.yaml")
        if not tones_path.exists():
            tones_path = Path("data/tones.yaml")
        if tones_path.exists():
            with open(tones_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for tid, tdata in data.get("tones", {}).items():
                self.tones[tid] = ToneConfig(
                    id=tid,
                    name=tdata.get("name", ""),
                    description=tdata.get("description", ""),
                    style=tdata.get("style", ""),
                    verbal_tics=tdata.get("verbal_tics", []),
                    sentence_pattern=tdata.get("sentence_pattern", ""),
                )

        # 加载场景库
        scenes_path = Path(f"data/scene_groups/{active_scene}.yaml")
        if not scenes_path.exists():
            scenes_path = Path("data/scenes.yaml")
        if scenes_path.exists():
            with open(scenes_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for sid, sdata in data.get("scenes", {}).items():
                self.scenes[sid] = SceneConfig(
                    id=sid,
                    name=sdata.get("name", ""),
                    description=sdata.get("description", ""),
                    trigger_hint=sdata.get("trigger_hint", ""),
                    tone_id=sdata.get("tone", ""),
                    extra_hint=sdata.get("extra_hint", ""),
                )

    def _build_scene_list(self) -> str:
        """构建场景列表给 AI 判断用"""
        lines = []
        for sid, scene in self.scenes.items():
            lines.append(f"- {sid}（{scene.name}）：{scene.trigger_hint}")
        return "\n".join(lines)

    async def detect(
        self,
        text: str,
        emotion: str = "平静",
        hour: int = -1,
        relationship_level: int = 5,
    ) -> SceneContext:
        """用 AI 检测当前对话场景"""
        if not text or not self.scenes:
            return self._default_scene()

        # 时间描述
        if 6 <= hour < 12:
            time_desc = "上午"
        elif 12 <= hour < 14:
            time_desc = "中午"
        elif 14 <= hour < 18:
            time_desc = "下午"
        elif 18 <= hour < 23:
            time_desc = "晚上"
        elif 23 <= hour or hour < 2:
            time_desc = "深夜"
        else:
            time_desc = "凌晨"

        scene_list = self._build_scene_list()

        system_prompt = (
            "你是一个对话场景分析专家。根据用户的消息，判断当前对话属于什么场景。\n\n"
            f"可选的场景类型：\n{scene_list}\n\n"
            "输出 JSON 格式：\n"
            '{"scene_id": "场景ID", "reason": "判断理由"}\n\n'
            "规则：\n"
            "1. 只输出 JSON，不要其他内容\n"
            "2. 如果不确定，选 casual\n"
            "3. 综合考虑文字内容、情绪、语气来判断\n"
            "4. 注意区分真实情绪和撒娇/开玩笑，关系亲近时的生气可能是撒娇\n"
            "5. 注意正反话，'才不想你'可能是'很想你'的意思"
        )

        prompt = (
            f"用户消息：{text}\n"
            f"用户情绪：{emotion}\n"
            f"当前时间：{time_desc}\n"
            f"关系亲密度：{relationship_level}/10\n\n"
            f"请判断当前对话场景。"
        )

        result = await self.llm.generate_json(prompt, system_prompt, use_light=True)

        if not result or "scene_id" not in result:
            return self._default_scene()

        scene_id = result["scene_id"]

        if scene_id not in self.scenes:
            return self._default_scene()

        return self._build_context(self.scenes[scene_id])

    def _build_context(self, scene: SceneConfig) -> SceneContext:
        """根据场景配置构建上下文"""
        tone = self.tones.get(scene.tone_id)

        style_parts = []
        if tone:
            style_parts.append(tone.style.strip())
            if tone.sentence_pattern:
                style_parts.append(f"句式：{tone.sentence_pattern}")
        if scene.extra_hint:
            style_parts.append(scene.extra_hint.strip())

        emotion_modifier = tone.name if tone else "自然"

        return SceneContext(
            scene=scene.name,
            style_hint="\n".join(style_parts),
            emotion_modifier=emotion_modifier,
        )

    def _default_scene(self) -> SceneContext:
        """默认场景"""
        if "casual" in self.scenes:
            return self._build_context(self.scenes["casual"])

        return SceneContext(
            scene="日常闲聊",
            style_hint="轻松随意，简短自然",
            emotion_modifier="自然",
        )

    def format_for_prompt(self, ctx: SceneContext) -> str:
        """格式化为 Prompt 注入内容"""
        return (
            f"[当前场景] {ctx.scene}\n"
            f"说话方式调整：\n{ctx.style_hint}\n"
            f"语气：{ctx.emotion_modifier}"
        )

    def reload(self):
        """重新加载配置（热更新）"""
        self.tones.clear()
        self.scenes.clear()
        self._load_configs()
