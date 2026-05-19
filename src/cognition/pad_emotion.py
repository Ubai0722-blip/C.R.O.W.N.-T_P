# by UBAI
"""
pad_emotion.py
拟真情感系统 (Realistic Emotion System) - PAD 三维情感模型

此模块使用心理学经典的 PAD（Pleasure-愉悦度, Arousal-唤醒度, Dominance-支配度）情感空间模型，
来替代简单的分类情绪。它引入了：
1. 情绪惯性 (Emotional Inertia)：情绪不会由于一句笑话瞬间从大怒变成大喜，而是像物理坐标一样缓慢游动。
2. 情绪阻尼 (Time Decay)：随着时间推移，唤醒度（激动程度）会逐渐降息，愉悦度也会向基线靠拢。
"""

import time
import math

class PADEmotionModel:
    def __init__(self, base_p=0.0, base_a=0.0, base_d=0.0):
        # 当前的情绪坐标 [-1.0, 1.0]
        self.p = base_p
        self.a = base_a
        self.d = base_d
        
        # 角色性格的基线（比如乐天派 base_p 会倾向于 > 0）
        self.base_p = base_p
        self.base_a = base_a
        self.base_d = base_d
        
        self.last_update = time.time()

    def receive_stimulus(self, target_p: float, target_a: float, target_d: float, intensity: float = 0.3):
        """
        接收外界刺激（比如用户说了一句很冒犯的话）
        intensity 决定了刺激有多强（0.0 ~ 1.0），它就是情绪惯性的核心因子。
        如果处于极度激动状态，对负面刺激的敏感度可能还会放大。
        """
        self._apply_time_decay()
        
        # 如果当前非常激动，惯性大，难以被轻易拉回；如果被激怒，更容易受负面影响
        if self.a > 0.5 and target_p < 0:
            intensity *= 1.5  # 冲动状态下更敏感

        self.p = self.p * (1 - intensity) + target_p * intensity
        self.a = self.a * (1 - intensity) + target_a * intensity
        self.d = self.d * (1 - intensity) + target_d * intensity
        
        # 钳制在 [-1.0, 1.0] 内
        self.p = max(-1.0, min(1.0, self.p))
        self.a = max(-1.0, min(1.0, self.a))
        self.d = max(-1.0, min(1.0, self.d))
        self.last_update = time.time()

    def _apply_time_decay(self):
        """
        随时间推移的情绪淡化（以小时为单位）
        人的激动(Arousal)褪去最快，愉悦(Pleasure)慢慢恢复原状。
        """
        now = time.time()
        elapsed_hours = (now - self.last_update) / 3600.0
        
        if elapsed_hours <= 0:
            return
            
        # 例如每过1小时，唤醒度衰减50%（变得平静），愉悦度衰减20%
        self.a = self.a * (0.5 ** elapsed_hours)
        
        # P 和 D 逐渐向性格基线靠拢
        self.p = self.base_p + (self.p - self.base_p) * (0.8 ** elapsed_hours)
        self.d = self.base_d + (self.d - self.base_d) * (0.9 ** elapsed_hours)

    def get_discrete_emotion(self) -> str:
        """映射回离散情绪分类，方便传递给 LLM 或者决定表情"""
        if self.p > 0.3 and self.a > 0.3: return "开心/狂喜"
        if self.p > 0.3 and self.a < -0.2: return "舒适/放松"
        if self.p < -0.3 and self.a > 0.3: return "烦躁/愤怒"
        if self.p < -0.3 and self.a < -0.3: return "抑郁/悲伤"
        if self.p > -0.2 and self.p < 0.2 and self.a > 0.5: return "惊奇/紧张"
        return "平静"

    def get_context_prompt(self) -> str:
        """生成发送给 LLM 的心理暗示 prompt"""
        label = self.get_discrete_emotion()
        prompt = f"[内心深处的真实情感流露]\n当前由于惯性，你的情绪坐标是 ({self.p:.2f}, {self.a:.2f}) -> {label}。"
        
        # 惯性补充
        if self.a > 0.6:
            prompt += "（你现在有点心率加速，情绪略激动，讲话可能会冲动一点或者带感叹号）"
        elif self.p < -0.5:
            prompt += "（你心里一直憋着一股闷气或者委屈还没消散，虽然表面可能在正常回复，但态度比较冷淡）"
        elif self.a < -0.5:
            prompt += "（你现在处于非常慵懒、疲惫的状态，连字都不想多打，只想随声附和）"
            
        return prompt
