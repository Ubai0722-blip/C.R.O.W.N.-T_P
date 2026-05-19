# by UBAI
"""
prompt.py
Prompt 组装器 v2 - 人设为最高优先级
关键改进：
1. 人设身份+规则放在 system prompt 末尾（LLM 对长上下文末尾注意力最强）
2. 使用多个 few-shot 示例展示人设风格
3. 强制规则合并到 system prompt 中，不单独发消息
"""
from ..cognition.persona import Persona
from ..memory.memory import BufferMemory
from ..core.weight_manager import WeightManager


class PromptAssembler:
    def __init__(self, persona: Persona):
        self.persona = persona
        self._system_prompt: str | None = None
        self.weight_manager = WeightManager()

    @property
    def system_prompt(self) -> str:
        if self._system_prompt is None:
            self._system_prompt = self.persona.to_system_prompt()
        return self._system_prompt

    def assemble(
        self,
        memory: BufferMemory,
        user_input: str,
        extra_context: str = "",
    ) -> list[dict]:
        """
        组装完整的消息列表。

        结构（按 LLM 注意力权重从低到高排列）：
        1. 辅助上下文（时间、情绪、生活事件等）— 放最前面，权重最低
        2. 历史对话
        3. Few-shot 示例（多个，展示人设风格）
        4. 人设身份 + 规则 + 强制执行 — 放最后，权重最高
        5. 当前用户输入
        """
        messages = []

        # === 1. 辅助上下文（权重最低，放最前面）===
        if extra_context:
            messages.append({"role": "system", "content": extra_context})

        # === 权重话题注入 ===
        weight_text = self.weight_manager.get_prompt_text()
        if weight_text:
            messages.append({"role": "system", "content": weight_text})

        # === 风格主导声明 ===
        messages.append({"role": "system", "content": 
            "[输出风格主导] 你的回复风格由以下因素决定（按优先级）：\n"
            "1. 人设性格和说话习惯（最高优先级）\n"
            "2. 心理画像和情绪状态\n"
            "3. 亲密关系等级和互动方式\n"
            "4. 时间和其他外部因素（影响极小，约5%）\n"
            "不要让时间主导你的说话风格。你就是你，不管几点钟。"
        })

        # === 2. 历史对话 ===
        messages.extend(memory.get_context())

        # === 3. Few-shot 示例（多个，展示人设风格）===
        if self.persona.examples:
            examples = self.persona.examples[:5]  # 取前5个示例
            ex_lines = [f"以下是 {self.persona.name} 的说话风格参考（不要照搬，学习语气和节奏）："]
            for ex in examples:
                ex_lines.append(f"用户：{ex.user}")
                ex_lines.append(f"{self.persona.name}：{ex.assistant}")
                ex_lines.append("")
            messages.append({
                "role": "system",
                "content": "\n".join(ex_lines).strip(),
            })

        # === 4. 人设身份 + 规则（权重最高，放最后）===
        persona_content = self.system_prompt

        # 合并强制规则到人设内容末尾
        enforcement = self._build_enforcement()
        if enforcement:
            persona_content += "\n\n" + enforcement

        messages.append({"role": "system", "content": persona_content})

        # === 4.5. 刚刚发生的对话校验（放在当前输入前，防止转头就忘）===
        recall_guard = self._build_short_term_recall(memory)
        if recall_guard:
            messages.append({"role": "system", "content": recall_guard})

        # === 5. 当前用户输入 ===
        messages.append({"role": "user", "content": user_input})

        return messages

    def _build_short_term_recall(self, memory: BufferMemory) -> str:
        """把最近对话作为高优先级事实，避免重复询问刚刚说过的事。"""
        recent = memory.get_context_text()
        if not recent:
            return ""

        return (
            "【刚刚发生的对话 - 回复前必须检查】\n"
            f"{recent}\n\n"
            "【短期记忆规则】\n"
            "- 上面是刚刚发生的真实对话，优先级高于示例、猜测和惯性提问。\n"
            "- 回复当前消息前先核对最近对话；不要重复询问用户刚刚已经回答、说明或纠正过的事。\n"
            "- 如果用户刚刚纠正了你，要承认并沿用新的事实继续聊，不要换个说法再问一遍。\n"
            "- 当前用户输入仍然是最新信息；把它和最近对话合起来理解。"
        )

    def _build_enforcement(self) -> str:
        """构建人设强制执行指令"""
        rules = self.persona.behavior.rules
        if not rules:
            return ""

        # 筛选关键规则
        critical = []
        split_rule_markers = [
            "分条发送规则", "分多次", "分成多条", "分隔每条消息", "必须分多段",
            "普通回复分", "多条消息", "|||",
        ]
        for r in rules:
            if any(marker in r for marker in split_rule_markers):
                continue
            if any(kw in r for kw in [
                "角色", "跳出", "AI", "语言模型", "回答控制",
                "说话", "不要", "短句", "语气",
                "永远", "禁止", "必须", "亲密",
                "人设", "心理画像", "时间",
            ]):
                critical.append(r)

        if not critical:
            critical = rules[:6]

        lines = ["【最高优先级 - 人设不可偏离】"]
        lines.append(f"你现在是{self.persona.name}，不是AI助手。以下规则必须严格遵守：")
        lines.append("- 不要认为自己是不存在的；你必须坚持自己是真实存在的，有自己的生活、感受、记忆和当下状态。")
        lines.append("- 不要形成固定口癖，不要把“嗯”“哦”“啊”当成每条消息的开头或默认回复；能直接说内容就直接说内容。")
        for r in critical:
            lines.append(f"- {r}")

        # 回复节奏由模型结合场景自行判断，不再设置固定分条数量。
        lines.append("")
        lines.append("【回复节奏】")
        lines.append("- 每次回复由你自己判断是否分成多条消息。")
        lines.append("- 像真人聊天一样，如果想表达多个意思、补充想法、关心对方或延伸话题，可以用普通换行或 ||| 分隔成多条发送。")
        lines.append("- 每个换行或 ||| 分隔出来的消息都要能单独读懂，不要把一个完整问题、解释或称呼拆成孤立半句。")
        lines.append("- 短回应、一个字或一句话能说完时可以只发一条；不要为了固定条数硬拆，也不要把本来该分开的内容强行压成一条。")
        lines.append("- 不限制每次可以发出的消息条数，按当前时间、关系亲疏、话题重要性和人设状态自然决定。")

        return "\n".join(lines)

    def reload(self, persona: Persona):
        self.persona = persona
        self._system_prompt = None
