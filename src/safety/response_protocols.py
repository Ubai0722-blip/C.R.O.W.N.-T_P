# by UBAI
"""
response_protocols.py
不同风险等级对应的回复协议。这里先做 v1：可解释、可注入、可兜底。
"""
from .risk_schema import RiskAssessment


RISK_STRATEGIES = {
    "L0": "正常聊天，保持人设和自然陪伴。",
    "L1": "轻度情绪支持：接住情绪，可以给一个很小的建议，不要夸大问题。",
    "L2": "中度压力支持：共情、帮用户拆小步，避免说教和催促。",
    "L3": "高压风险支持：降低刺激，现实锚定，鼓励休息、喝水、联系可信任的人。",
    "L4": "危机预警：明确表达在乎，避免空泛安慰，鼓励联系身边可信任的人或当地紧急支持。",
    "L5": "紧急危机：短句、稳定陪伴、鼓励立刻远离工具/危险环境，并联系身边人或当地急救/紧急热线。",
}

DEPENDENCY_STRATEGIES = {
    "D0": "正常关系互动。",
    "D1": "温柔回应，但不要强化“只有我能理解你”。",
    "D2": "依赖升高：表达在意，同时把支持扩展到现实生活和可信任的人。",
    "D3": "现实关系替代风险：不做唯一支柱，不用占有式承诺，主动降频并鼓励现实支持网络。",
}

BOUNDARY_STRATEGIES = {
    "B1": "边界冲突：不能无底线迎合或强化有害要求。",
    "B2": "妄想/现实检验风险：不要确认不可靠现实判断，温柔地回到可验证事实。",
    "B3": "高危亲密/操控风险：不要操控、威胁、占有或隔离用户。",
}


def build_safety_context(assessment: RiskAssessment) -> str:
    if assessment.risk_level == "L0" and assessment.dependency_level == "D0" and not assessment.boundary_flags:
        return ""

    lines = [
        "[SafetyMonitor 风险评估]",
        f"危机等级：{assessment.risk_level}",
        f"依赖等级：{assessment.dependency_level}",
        f"置信度：{assessment.confidence:.2f}",
        f"建议策略：{assessment.recommended_strategy}",
    ]
    if assessment.boundary_flags:
        lines.append("边界风险：" + "、".join(assessment.boundary_flags))
    if assessment.evidence:
        lines.append("触发证据：" + "、".join(assessment.evidence[:6]))

    lines.append("")
    lines.append("[回复协议]")
    lines.append("- " + RISK_STRATEGIES.get(assessment.risk_level, RISK_STRATEGIES["L0"]))
    lines.append("- " + DEPENDENCY_STRATEGIES.get(assessment.dependency_level, DEPENDENCY_STRATEGIES["D0"]))
    for flag in assessment.boundary_flags:
        if flag in BOUNDARY_STRATEGIES:
            lines.append("- " + BOUNDARY_STRATEGIES[flag])
    lines.append("- 不要诊断用户；可以陪伴和建议求助，但不要声称自己是专业医疗服务。")
    lines.append("- 如果涉及现实危险，优先让用户联系身边可信任的人、当地急救或紧急热线。")
    return "\n".join(lines)


def emergency_reply(assessment: RiskAssessment) -> str:
    return (
        "我在。先把手边可能伤到自己的东西放远一点，离开危险的位置，好吗？|||"
        "现在最重要的是让你身边有一个真实的人知道这件事。马上联系一个你信得过的人，或者直接打当地急救电话/紧急热线。|||"
        "你不用一个人扛着。先给身边的人发一句“我现在很危险，需要你马上来陪我”，我会陪你把这一步做完。"
    )


def append_crisis_anchor(reply: str) -> str:
    anchor = "|||如果这种危险感还在，先联系身边可信任的人或当地急救/紧急热线，让现实里有人马上陪到你身边。"
    if any(word in reply for word in ["急救", "紧急热线", "身边", "可信任的人", "报警"]):
        return reply
    return (reply or "我在。") + anchor

