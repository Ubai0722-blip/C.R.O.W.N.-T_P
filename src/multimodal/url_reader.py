# by UBAI
"""
url_reader.py
URL内容读取模块 - 读取链接内容并提取正文

功能：
1. 读取URL内容（网页、文章、博客等）
2. 提取正文（去除广告、导航等噪音）
3. 限制返回长度，避免token爆炸
4. 支持搜索结果中的链接发送

依赖：
- trafilatura: 网页正文提取（最佳选择，支持多语言）
- httpx: 异步HTTP请求

参考项目：
- trafilatura (github.com/adbar/trafilatura) - 网页正文提取
"""

import re
from dataclasses import dataclass
import httpx


@dataclass
class URLContent:
    """URL读取结果"""
    url: str
    title: str
    content: str           # 提取的正文
    success: bool
    error: str = ""


# URL检测正则
URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]]+',
    re.IGNORECASE
)


def extract_urls(text: str) -> list[str]:
    """从文本中提取URL"""
    urls = URL_PATTERN.findall(text)
    # 清理末尾标点
    cleaned = []
    for url in urls:
        url = url.rstrip('.,;:!?。，；：！？')
        cleaned.append(url)
    return list(set(cleaned))


async def read_url(url: str, max_chars: int = 3000) -> URLContent:
    """
    读取URL内容并提取正文。
    
    参数：
    - url: 目标URL
    - max_chars: 最大返回字符数
    
    返回：URLContent 对象
    """
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return URLContent(
                    url=url, title="", content="",
                    success=False, error=f"HTTP {resp.status_code}",
                )

            html = resp.text

        # 尝试用 trafilatura 提取正文
        try:
            import trafilatura
            content = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=True,
                favor_precision=True,
                url=url,
            )
            # 也提取标题
            metadata = trafilatura.extract(html, output_format='json', url=url)
            title = ""
            if metadata:
                import json
                try:
                    meta = json.loads(metadata) if isinstance(metadata, str) else metadata
                    title = meta.get("title", "")
                except:
                    pass
        except ImportError:
            # trafilatura 未安装，用简单的正则提取
            content = _simple_extract(html)
            title = _extract_title(html)

        if not content:
            return URLContent(
                url=url, title="", content="",
                success=False, error="无法提取正文",
            )

        # 截断
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[内容截断，共{len(content)}字符]"

        return URLContent(
            url=url,
            title=title or "",
            content=content,
            success=True,
        )

    except httpx.TimeoutException:
        return URLContent(url=url, title="", content="", success=False, error="请求超时")
    except Exception as e:
        return URLContent(url=url, title="", content="", success=False, error=str(e)[:100])


def format_for_prompt(url_contents: list[URLContent]) -> str:
    """将URL内容格式化为注入Prompt的文本"""
    if not url_contents:
        return ""

    lines = ["[链接内容] 用户发送了以下链接，以下是提取的内容："]
    for i, uc in enumerate(url_contents, 1):
        if uc.success:
            title_part = f"【{uc.title}】" if uc.title else ""
            lines.append(f"\n--- 链接{i}: {uc.url} {title_part} ---")
            lines.append(uc.content)
        else:
            lines.append(f"\n--- 链接{i}: {uc.url} ---")
            lines.append(f"[读取失败: {uc.error}]")

    lines.append("\n请基于以上链接内容回应用户，可以用你自己的话总结或评论。")
    return "\n".join(lines)


def _simple_extract(html: str) -> str:
    """简单的HTML正文提取（trafilatura不可用时的后备方案）"""
    # 去除script和style标签
    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # 去除HTML标签
    text = re.sub(r'<[^>]+>', ' ', html)
    # 清理空白
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:3000]


def _extract_title(html: str) -> str:
    """简单提取HTML标题"""
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.DOTALL | re.IGNORECASE)
    if match:
        return re.sub(r'<[^>]+>', '', match.group(1)).strip()[:100]
    return ""
