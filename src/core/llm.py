# by UBAI
"""
llm.py
"""
import json
import asyncio
import httpx
from ..cognition.persona import Persona
from ..utils.config import get_config


def dlog(msg):
    try:
        with open("debug.log", "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except:
        pass


class LLMClient:
    @property
    def api_base(self):
        base = get_config().get("llm", {}).get("api_base", "").rstrip("/")
        if not base.endswith("/v1") and "v1" not in base:
            base += "/v1"
        return base

    @property
    def api_key(self):
        return get_config().get("llm", {}).get("api_key", "")

    @property
    def model(self):
        return get_config().get("llm", {}).get("model", "")

    @property
    def light_model(self):
        """轻量模型（后台任务专用：心理画像/成长总结/漂移检测等）"""
        return get_config().get("llm", {}).get("light_model", self.model)

    def __init__(
        self,
        api_base: str = None,
        api_key: str = None,
        model: str = None,
        max_tokens: int = 512,
        temperature: float = 0.3,
        timeout: float = 60.0,
    ):
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = httpx.AsyncClient(timeout=timeout)

    @property
    def retry_attempts(self) -> int:
        """LLM 请求重试次数，默认 2 次，避免短暂网络/API 抖动直接让聊天失败。"""
        value = get_config().get("llm", {}).get("retry_attempts", 2)
        try:
            return max(0, int(value))
        except Exception:
            return 2

    async def _post_chat(self, payload: dict, tag: str = "llm") -> dict | None:
        """统一请求入口：重试、错误日志和响应解析集中处理。"""
        retryable_status = {408, 409, 425, 429, 500, 502, 503, 504}
        max_attempts = self.retry_attempts + 1

        for attempt in range(1, max_attempts + 1):
            try:
                resp = await self.client.post(
                    f"{self.api_base}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                if resp.status_code == 200:
                    return resp.json()

                body = resp.text[:300].replace("\n", " ")
                dlog(f"[{tag}] API错误 status={resp.status_code} attempt={attempt}/{max_attempts} body={body}")
                if resp.status_code not in retryable_status or attempt >= max_attempts:
                    return None

            except httpx.TimeoutException:
                dlog(f"[{tag}] 请求超时 attempt={attempt}/{max_attempts}")
                if attempt >= max_attempts:
                    return None
            except (httpx.ConnectError, httpx.NetworkError) as e:
                dlog(f"[{tag}] 网络错误 attempt={attempt}/{max_attempts}: {e}")
                if attempt >= max_attempts:
                    return None
            except Exception as e:
                dlog(f"[{tag}] 未知错误 attempt={attempt}/{max_attempts}: {type(e).__name__}: {e}")
                return None

            await asyncio.sleep(min(0.8 * attempt, 3.0))

        return None

    @staticmethod
    def _extract_message_content(data: dict) -> str:
        try:
            return data["choices"][0]["message"]["content"] or ""
        except Exception as e:
            dlog(f"[llm] 响应结构异常: {type(e).__name__}: {e}")
            return ""

    async def chat(self, messages: list[dict], temperature: float = None, model: str = None) -> str:
        temp = temperature if temperature is not None else self.temperature
        use_model = model or self.model
        data = await self._post_chat({
            "model": use_model,
            "messages": messages,
            "temperature": temp,
            "safety_settings": [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
            ],
        })
        if data:
            return self._extract_message_content(data)
        return ""

    async def generate_json(self, prompt: str, system: str = "", use_light: bool = False) -> dict | None:
        """
        生成结构化 JSON 输出。
        用于生活事件、心理画像、时间解析、场景识别等后台任务。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        use_model = self.light_model if use_light else self.model
        data = await self._post_chat({
            "model": use_model,
            "messages": messages,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }, tag="llm json")
        if not data:
            return None

        content = self._extract_message_content(data).strip()
        if not content:
            return None
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            dlog(f"[llm json] JSON解析失败: {e}; content={content[:300]}")
            return None

    async def chat_light(self, messages: list[dict], temperature: float = 0.5) -> str:
        """用轻量模型调用（后台任务专用，省钱）"""
        return await self.chat(messages, temperature=temperature, model=self.light_model)

    async def chat_multimodal(self, messages: list[dict]) -> str:
        """
        多模态对话（支持图片）。
        messages 中可以包含 image_url 类型的 content。
        """
        data = await self._post_chat({
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }, tag="llm mm")
        if not data:
            return "图片分析出了点问题，请再试一次。"
        return self._extract_message_content(data).strip() or "图片分析出了点问题，请再试一次。"

    async def chat_stream(self, messages: list[dict], temperature: float = None, model: str = None):
        """
        流式接口兜底实现。
        当前底层客户端统一走非流式请求，保证调用方不会因缺少 chat_stream 崩溃。
        """
        result = await self.chat(messages, temperature=temperature, model=model)
        if result:
            yield result

    async def close(self):
        await self.client.aclose()


class VLMClient:
    """VLM (Vision Language Model) 客户端 - 通过 API 进行图像识别"""

    @property
    def api_base(self):
        base = get_config().get("vlm", {}).get("api_base", "").rstrip("/")
        if not base.endswith("/v1") and "v1" not in base:
            base += "/v1"
        return base

    @property
    def api_key(self):
        cfg = get_config()
        return cfg.get("vlm", {}).get("api_key", "") or cfg.get("llm", {}).get("api_key", "")

    @property
    def model(self):
        return get_config().get("vlm", {}).get("model", "mimo-v2.5-vl")

    @property
    def light_model(self):
        return get_config().get("llm", {}).get("light_model", get_config().get("llm", {}).get("model", ""))

    def __init__(self):
        cfg = get_config().get("vlm", {})
        self.max_tokens = cfg.get("max_tokens", 512)
        self.temperature = cfg.get("temperature", 0.3)
        timeout = cfg.get("timeout", 30.0)
        self.client = httpx.AsyncClient(timeout=timeout)

    async def analyze_image(self, image_url_or_path: str, prompt: str = "描述这张图片的内容") -> str:
        """
        通过 VLM API 分析图片。
        支持图片 URL 或本地文件路径。
        """
        import base64
        from pathlib import Path

        # 构建图片内容
        if image_url_or_path.startswith(("http://", "https://")):
            image_content = {
                "type": "image_url",
                "image_url": {"url": image_url_or_path},
            }
        else:
            # 本地文件：转 base64
            try:
                path = Path(image_url_or_path)
                if not path.exists():
                    return "图片文件不存在"
                suffix = path.suffix.lower()
                mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif", ".webp": "image/webp"}
                mime = mime_map.get(suffix, "image/jpeg")
                with open(path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                image_content = {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                }
            except Exception as e:
                dlog(f"[vlm] 读取图片失败: {e}")
                return "图片读取失败"

        messages = [
            {
                "role": "user",
                "content": [
                    image_content,
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            resp = await self.client.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
            else:
                dlog(f"[vlm] API 错误: {resp.status_code}")
                return "图片分析出了点问题"
        except httpx.TimeoutException:
            return "图片分析超时了"
        except Exception as e:
            dlog(f"[vlm err] {e}")
            return "图片分析出了点问题"

    async def close(self):
        await self.client.aclose()

    async def generate_json(self, prompt: str, system: str = "", use_light: bool = False) -> dict | None:
        """
        生成结构化 JSON 输出。
        用于生活事件生成、心理画像分析等。
        use_light=True 时使用轻量模型。
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        use_model = self.light_model if use_light else self.model
        try:
            resp = await self.client.post(
                f"{self.api_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": use_model,
                    "messages": messages,
                    "temperature": 0.8,
                    "response_format": {"type": "json_object"},
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                return json.loads(content)
            else:
                dlog(f"[llm json] API 错误: {resp.status_code}")
        except json.JSONDecodeError as e:
            dlog(f"[llm json] JSON 解析失败: {e}")
        except Exception as e:
            dlog(f"[llm json err] {e}")
        return None
