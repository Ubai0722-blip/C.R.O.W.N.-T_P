# by UBAI
"""
sticker.py
表情包识别系统 - 下载、识别、情绪提取
"""
import httpx
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass


@dataclass
class StickerAnalysis:
    """表情包分析结果"""
    description: str     # 表情包内容描述
    emotion: str         # 识别出的情绪
    intensity: str       # 强度
    context_hint: str    # 给 AI 的提示


# 表情包情绪到通用情绪的映射
STICKER_EMOTION_MAP = {
    "搞笑": "开心",
    "可爱": "开心",
    "卖萌": "撒娇",
    "无语": "生气",
    "白眼": "生气",
    "嫌弃": "生气",
    "哭": "难过",
    "流泪": "难过",
    "委屈": "难过",
    "愤怒": "生气",
    "暴怒": "生气",
    "抓狂": "生气",
    "惊讶": "好奇",
    "震惊": "好奇",
    "害怕": "焦虑",
    "紧张": "焦虑",
    "困": "疲惫",
    "睡觉": "疲惫",
    "害羞": "撒娇",
    "脸红": "撒娇",
    "得意": "开心",
    "偷笑": "开心",
    "加油": "开心",
    "鼓励": "感动",
    "比心": "感动",
    "爱心": "感动",
    "鄙视": "生气",
    "嘲讽": "生气",
    "发呆": "无聊",
    "摸鱼": "无聊",
}


class StickerManager:
    """表情包管理器"""

    def __init__(self):
        self.save_dir = Path("data/stickers")
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self._vlm_client = None

    def set_vlm_client(self, vlm_client):
        """设置 VLM 客户端实例"""
        self._vlm_client = vlm_client

    async def analyze_with_vlm(self, image_path_or_url: str, qq_tag: str = "") -> StickerAnalysis:
        """
        使用 VLM API 分析表情包。
        qq_tag: QQ 自带的表情包标签（如果有）
        """
        if not self._vlm_client:
            # 没有 VLM 客户端，回退到标签映射
            if qq_tag:
                emotion, intensity = self.map_emotion(qq_tag)
                return StickerAnalysis(
                    description=qq_tag,
                    emotion=emotion,
                    intensity=intensity,
                    context_hint=f"用户发了一个表情包，标签是「{qq_tag}」",
                )
            return StickerAnalysis(description="未知表情包", emotion="平静", intensity="中度", context_hint="")

        prompt = "请用一两句话描述这个表情包的内容和表达的情绪。只输出描述，不要多余的话。"
        if qq_tag:
            prompt = f"这个表情包的QQ标签是「{qq_tag}」。{prompt}"

        try:
            result = await self._vlm_client.analyze_image(image_path_or_url, prompt)
            emotion, intensity = self.map_emotion(result)
            return StickerAnalysis(
                description=result,
                emotion=emotion,
                intensity=intensity,
                context_hint=f"表情包内容：{result}",
            )
        except Exception as e:
            # VLM 调用失败，回退到标签
            if qq_tag:
                emotion, intensity = self.map_emotion(qq_tag)
                return StickerAnalysis(
                    description=qq_tag,
                    emotion=emotion,
                    intensity=intensity,
                    context_hint=f"用户发了一个表情包，标签是「{qq_tag}」",
                )
            return StickerAnalysis(description="分析失败", emotion="平静", intensity="中度", context_hint="")

    def save_sticker(self, image_url: str, user_id: str) -> str | None:
        """下载表情包到本地"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_uid = user_id.replace("/", "_").replace("\\", "_")
            filename = f"{safe_uid}_{timestamp}.jpg"
            filepath = self.save_dir / filename

            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(image_url)
                if resp.status_code == 200:
                    filepath.write_bytes(resp.content)
                    return str(filepath)
        except Exception:
            pass
        return None

    def map_emotion(self, ai_description: str) -> tuple[str, str]:
        """
        根据 AI 的描述，映射出情绪和强度。
        返回 (情绪, 强度)
        """
        desc_lower = ai_description.lower()

        # 关键词匹配
        for keyword, emotion in STICKER_EMOTION_MAP.items():
            if keyword in desc_lower:
                # 判断强度
                intensity = "中度"
                strong_words = ["非常", "特别", "很", "超级", "非常搞笑", "大笑", "爆笑"]
                if any(w in desc_lower for w in strong_words):
                    intensity = "强烈"
                weak_words = ["有点", "稍微", "微微", "轻轻"]
                if any(w in desc_lower for w in weak_words):
                    intensity = "轻度"
                return emotion, intensity

        # 默认
        return "平静", "中度"

    def get_sticker_count(self) -> int:
        return len(list(self.save_dir.glob("*.jpg"))) + len(list(self.save_dir.glob("*.png")))
