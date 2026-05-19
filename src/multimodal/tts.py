# by UBAI
"""
tts.py
TTS 语音合成模块 - MiMo 音色克隆
"""
import os
import base64
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

from openai import OpenAI


def dlog(msg):
    with open("debug.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")


from ..utils.config import get_config

class TTSClient:
    """TTS 客户端 - MiMo 音色克隆"""

    @property
    def api_base(self):
        if getattr(self, "_api_base_override", None):
            return self._api_base_override
        return get_config().get("tts", {}).get("api_base", "")

    @property
    def api_key(self):
        if getattr(self, "_api_key_override", None):
            return self._api_key_override
        conf = get_config()
        return conf.get("tts", {}).get("api_key", conf.get("llm", {}).get("api_key", ""))

    @property
    def model(self):
        if getattr(self, "_model_override", None):
            return self._model_override
        return get_config().get("tts", {}).get("model", "mimo-v2.5-tts-voiceclone")

    def __init__(
        self,
        api_base: str = None,
        api_key: str = None,
        model: str = None,
        reference_audio: str = "",
    ):
        self.output_dir = Path("data/voice")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._api_base_override = api_base
        self._api_key_override = api_key
        self._model_override = model
        conf = get_config().get("tts", {})
        self.timeout = float(conf.get("timeout", 60.0))
        # reference_audio 可以考虑也放进配置，这里保持现状

        # ffmpeg 路径
        self.ffmpeg_path = self._find_ffmpeg()

        # OpenAI 客户端
        self.client = OpenAI(
            api_key=api_key or self.api_key,
            base_url=api_base or self.api_base,
            timeout=self.timeout,
        )

        # 加载参考音频（限制在30秒内，避免API拒绝）
        self._voice_base64 = ""
        if reference_audio and os.path.exists(reference_audio):
            file_size = os.path.getsize(reference_audio)
            # 如果文件大于5MB，用ffmpeg截取前30秒
            if file_size > 5 * 1024 * 1024:
                dlog(f"[tts] 参考音频过大({file_size/1024/1024:.1f}MB)，截取前30秒...")
                trimmed_path = str(self.output_dir / "reference_trimmed.wav")
                try:
                    import subprocess
                    subprocess.run([
                        self.ffmpeg_path, "-y",
                        "-i", reference_audio,
                        "-t", "30",  # 截取前30秒
                        "-ar", "24000",
                        "-ac", "1",
                        trimmed_path,
                    ], capture_output=True, timeout=30)
                    if os.path.exists(trimmed_path):
                        with open(trimmed_path, "rb") as f:
                            voice_bytes = f.read()
                        dlog(f"[tts] 截取后大小：{len(voice_bytes)/1024:.0f}KB")
                    else:
                        with open(reference_audio, "rb") as f:
                            voice_bytes = f.read()
                except Exception as e:
                    dlog(f"[tts] 截取失败，使用原文件：{e}")
                    with open(reference_audio, "rb") as f:
                        voice_bytes = f.read()
            else:
                with open(reference_audio, "rb") as f:
                    voice_bytes = f.read()
            self._voice_base64 = base64.b64encode(voice_bytes).decode("utf-8")
            dlog(f"[tts] 参考音频已加载：{reference_audio}（{len(voice_bytes)} bytes）")
        else:
            dlog(f"[tts] 警告：参考音频不存在：{reference_audio}")

        dlog(f"[tts] 初始化完成，模型：{self.model}，超时：{self.timeout}s")

    def _find_ffmpeg(self) -> str:
        """查找 ffmpeg"""
        import shutil
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg

        common_paths = [
            "ffmpeg"
        ]
        for p in common_paths:
            if os.path.exists(p):
                return p

        return "ffmpeg"

    async def synthesize(self, text: str, user_id: str = "") -> str | None:
        """
        合成语音，返回 silk 文件路径。
        """
        if not text or len(text) > 500:
            dlog(f"[tts] 文本过长或为空：{len(text) if text else 0}字符")
            return None

        if not self._voice_base64:
            dlog("[tts] 参考音频未加载，跳过")
            return None

        try:
            # 第一步：调用 MiMo TTS API
            wav_path = await asyncio.wait_for(
                asyncio.to_thread(self._call_api, text),
                timeout=self.timeout + 5,
            )
            if not wav_path:
                return None

            # 第二步：wav → silk
            silk_path = await self._wav_to_silk(wav_path)
            if not silk_path:
                return None

            # 清理 wav
            if os.path.exists(wav_path):
                os.remove(wav_path)

            dlog(f"[tts] 语音合成成功：{silk_path}")
            # 自动清理旧语音文件
            self.cleanup_old_files()
            return silk_path

        except Exception as e:
            dlog(f"[tts] 合成失败：{e}")
            dlog(traceback.format_exc())
            return None

    def _call_api(self, text: str) -> str | None:
        """
        调用 MiMo TTS API（同步，用 asyncio.to_thread 包装）。
        语气优化：去掉书面语痕迹，让 TTS 输出更像口语。
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        wav_path = str(self.output_dir / f"tts_{timestamp}.wav")

        # 口语化预处理：去掉书面语痕迹
        spoken_text = text
        spoken_text = spoken_text.replace("。", " ").replace("，", " ").replace("！", " ")
        spoken_text = spoken_text.replace("？", " ").replace("、", " ")
        spoken_text = spoken_text.replace("——", " ").replace("…", " ")
        spoken_text = spoken_text.replace("\n", " ").replace("|||", " ")
        # 去掉括号动作
        import re
        spoken_text = re.sub(r'[（(][^）)]{1,15}[）)]', '', spoken_text)
        spoken_text = re.sub(r'\*[^*]{1,15}\*', '', spoken_text)
        spoken_text = re.sub(r'\s+', ' ', spoken_text).strip()

        if not spoken_text:
            return None

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "用自然随意的语气说，像朋友聊天一样，不要念稿腔。"},
                    {"role": "user", "content": ""},
                    {"role": "assistant", "content": spoken_text},
                ],
                audio={
                    "format": "wav",
                    "voice": f"data:audio/mpeg;base64,{self._voice_base64}",
                },
            )

            message = completion.choices[0].message
            audio_bytes = base64.b64decode(message.audio.data)

            with open(wav_path, "wb") as f:
                f.write(audio_bytes)

            dlog(f"[tts] API 返回音频：{len(audio_bytes)} bytes")
            return wav_path

        except Exception as e:
            dlog(f"[tts] API 调用失败：{e}")
            dlog(traceback.format_exc())
            return None

    async def _wav_to_silk(self, wav_path: str) -> str | None:
        """
        wav → pcm → silk
        """
        import pilk

        silk_path = wav_path.rsplit(".", 1)[0] + ".silk"
        pcm_path = wav_path.rsplit(".", 1)[0] + ".pcm"

        try:
            # wav → pcm（24kHz, 单声道, 16bit）
            proc = await asyncio.create_subprocess_exec(
                self.ffmpeg_path, "-y",
                "-i", wav_path,
                "-f", "s16le",
                "-ar", "24000",
                "-ac", "1",
                pcm_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)

            if proc.returncode != 0:
                dlog(f"[tts] ffmpeg 失败：{stderr.decode()[:200]}")
                return None

            # pcm → silk
            await asyncio.to_thread(pilk.encode, pcm_path, silk_path, 24000, True)

            # 清理 pcm
            if os.path.exists(pcm_path):
                os.remove(pcm_path)

            return silk_path

        except ImportError:
            dlog("[tts] pilk 未安装，请运行: pip install pilk")
            return None
        except Exception as e:
            dlog(f"[tts] silk 转换失败：{e}")
            dlog(traceback.format_exc())
            return None

    def cleanup_old_files(self, max_age_hours: int = 24):
        """清理旧的语音文件"""
        import time
        now = time.time()
        for f in self.output_dir.glob("tts_*"):
            if now - f.stat().st_mtime > max_age_hours * 3600:
                f.unlink()
