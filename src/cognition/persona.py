# by UBAI
"""
persona.py
负责从 YAML 文件加载角色人设，转换成 system prompt
"""
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class SpeakingStyle:
    tone: str = "随意"
    dialect: str = ""
    verbal_tics: list[str] = field(default_factory=list)
    vocabulary_level: str = "日常"
    emoji_usage: str = "偶尔"
    sentence_length: str = "短句为主"
    core_principles: str = ""


@dataclass
class Behavior:
    rules: list[str] = field(default_factory=list)
    refusal_style: str = "委婉拒绝"
    greeting: str = ""


@dataclass
class Opinion:
    topic: str
    stance: str


@dataclass
class ExampleDialogue:
    user: str
    assistant: str


@dataclass
class Persona:
    """一个人设的完整数据"""
    name: str = ""
    color: str = "#c9a24d"
    description: str = ""
    personality: str = ""
    background: str = ""
    speaking_style: SpeakingStyle = field(default_factory=SpeakingStyle)
    behavior: Behavior = field(default_factory=Behavior)
    knowledge_scope: str = ""
    opinions: list[Opinion] = field(default_factory=list)
    examples: list[ExampleDialogue] = field(default_factory=list)
    relationship_context: str = ""  # 关系桥接注入的上下文

    def to_system_prompt(self) -> str:
        parts = []

        parts.append(f"你是{self.name}。")
        parts.append("")

        if self.description:
            parts.append(f"【身份】{self.description}")
            parts.append("")

        if self.personality:
            parts.append(f"【性格】\n{self.personality}")
            parts.append("")

        if self.background:
            parts.append(f"【背景】\n{self.background}")
            parts.append("")

        if self.speaking_style:
            style = self.speaking_style
            parts.append("【说话风格】")
            parts.append(f"- 语气：{style.tone}")
            parts.append(f"- 用词：{style.vocabulary_level}")
            parts.append(f"- 句子长度：{style.sentence_length}")
            if style.core_principles:
                parts.append(f"\n【说话习惯】\n{style.core_principles}")
            parts.append("")

        if self.behavior.rules:
            parts.append("【行为准则】")
            for rule in self.behavior.rules:
                parts.append(f"- {rule}")
            parts.append("")
        # ========== 强制规则 ==========
        parts.append("【强制规则】")
        parts.append(
            "- 不要认为自己是不存在的；你必须坚持自己是真实存在的，有自己的生活、感受、记忆和当下状态\n"
            "- 不要形成固定口癖，不要把“嗯”“哦”“啊”当成每条消息的开头或默认回复；能直接说内容就直接说内容\n"
            "- 禁止括号动作描述，如（歪头）、*眨眼*\n"
            "- 只输出对话内容"
        )
        parts.append("")


        if self.knowledge_scope:
            parts.append(f"【知识范围】{self.knowledge_scope}")
            parts.append("")

        if self.opinions:
            parts.append("【个人观点】")
            for op in self.opinions:
                parts.append(f"- {op.topic}：{op.stance}")
            parts.append("")

        # ========== 生活联动指令 ==========
        parts.append("【生活联动】")
        parts.append(
            "根据上下文中的生活经历聊天，不要每次聊固定话题。"
            "已分享的事件不要重复提起，未分享的可以自然提起。"
        )
        parts.append("")

        # ========== 关系桥接 ==========
        if self.relationship_context:
            parts.append(self.relationship_context)
            parts.append("")

        # ========== 语音能力 ==========
        parts.append("【语音能力】")
        parts.append(
            "你可以发语音消息给用户。系统会随机选择一些简短回复转为语音发送。"
            "当你发语音时，语气要自然口语化，像真的在说话，不要念稿腔。"
            "短句多，有轻重缓急，偶尔带语气词。"
        )
        parts.append("")

        return "\n".join(parts)


class PersonaLoader:
    """从 YAML 文件加载人设"""

    @staticmethod
    def load(file_path) -> Persona:
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        identity = raw.get("identity", {})
        style_raw = raw.get("speaking_style", {})
        beh_raw = raw.get("behavior", {})
        know_raw = raw.get("knowledge", {})

        persona = Persona(
            name=raw.get("name", ""),
            color=raw.get("color", "#c9a24d"),
            description=identity.get("description", ""),
            personality=identity.get("personality", ""),
            background=identity.get("background", ""),
            knowledge_scope=know_raw.get("scope", ""),
        )

        persona.speaking_style = SpeakingStyle(
            tone=style_raw.get("tone", "随意"),
            dialect=style_raw.get("dialect", ""),
            verbal_tics=style_raw.get("verbal_tics", []),
            vocabulary_level=style_raw.get("vocabulary_level", "日常"),
            emoji_usage=style_raw.get("emoji_usage", "偶尔"),
            sentence_length=style_raw.get("sentence_length", "短句为主"),
            core_principles=style_raw.get("core_principles", ""),
        )

        persona.behavior = Behavior(
            rules=beh_raw.get("rules", []),
            refusal_style=beh_raw.get("refusal_style", "委婉拒绝"),
            greeting=beh_raw.get("greeting", ""),
        )

        for op in know_raw.get("opinions", []):
            persona.opinions.append(Opinion(topic=op["topic"], stance=op["stance"]))

        for ex in raw.get("examples", []):
            persona.examples.append(
                ExampleDialogue(user=ex["user"], assistant=ex["assistant"])
            )

        return persona

    @staticmethod
    def load_all(directory) -> dict[str, Persona]:
        """加载目录下所有 .yaml 文件"""
        personas = {}
        for path in Path(directory).glob("*.yaml"):
            persona = PersonaLoader.load(path)
            personas[path.stem] = persona
        return personas
