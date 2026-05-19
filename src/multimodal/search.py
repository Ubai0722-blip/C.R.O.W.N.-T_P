# by UBAI
"""
search.py
联网搜索模块 - Tavily API
"""
import httpx
from dataclasses import dataclass


@dataclass
class SearchResult:
    """一条搜索结果"""
    title: str
    url: str
    content: str


@dataclass
class SearchResponse:
    """搜索响应"""
    query: str
    answer: str              # Tavily 生成的摘要答案
    results: list[SearchResult]
    success: bool


from ..utils.config import get_config

class WebSearcher:
    """联网搜索"""

    @property
    def api_key(self):
        return get_config().get("search", {}).get("api_key", "")
        
    @property
    def max_results(self):
        return get_config().get("search", {}).get("max_results", 3)

    def __init__(self, api_key: str = None, max_results: int = None):
        pass

    async def search(self, query: str) -> SearchResponse:
        """
        搜索并返回结果。
        Tavily 会自动返回一个摘要答案 + 搜索结果列表。
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": self.max_results,
                        "include_answer": True,
                        "search_depth": "basic",
                    },
                )

                if resp.status_code != 200:
                    return SearchResponse(
                        query=query,
                        answer=f"搜索失败（{resp.status_code}）",
                        results=[],
                        success=False,
                    )

                data = resp.json()

                results = []
                for item in data.get("results", []):
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        content=item.get("content", ""),
                    ))

                return SearchResponse(
                    query=query,
                    answer=data.get("answer", ""),
                    results=results,
                    success=True,
                )

        except httpx.TimeoutException:
            return SearchResponse(
                query=query,
                answer="搜索超时了",
                results=[],
                success=False,
            )
        except Exception as e:
            return SearchResponse(
                query=query,
                answer=f"搜索出错：{e}",
                results=[],
                success=False,
            )

    def format_for_prompt(self, response: SearchResponse) -> str:
        """把搜索结果格式化为注入 Prompt 的文本"""
        if not response.success:
            return ""

        parts = []

        # Tavily 的摘要答案
        if response.answer:
            parts.append(f"搜索摘要：{response.answer}")

        # 搜索结果
        for i, r in enumerate(response.results, 1):
            parts.append(f"[{i}] {r.title}")
            parts.append(f"    {r.content[:200]}")

        return "\n".join(parts)


# ========== 搜索意图判断 ==========

# 触发搜索的关键词
SEARCH_TRIGGERS = [
    # 直接要求搜索
    "搜一下", "查一下", "帮我搜", "帮我查", 
    "搜索", "百度一下", "谷歌一下", "网上搜",

    # 实时信息
    "实时", "新闻", "热搜",


    # 时事
    "发生了什么"

    # 知识查询
    "是什么", "什么意思", "怎么解释",
    "什么是", "介绍一下", "给我讲讲",

]

# 不需要搜索的场景（避免无意义搜索）
NO_SEARCH_PATTERNS = [
    "你好", "在吗", "在不在", "干嘛呢", "吃了吗",
    "晚安", "早安", "好的", "嗯", "哦", "谢谢",
    "哈哈", "嘿嘿", "嘻嘻", "呜呜",
]


def should_search(text: str) -> bool:
    """
    判断是否需要搜索。
    返回 True 表示应该搜索。
    """
    if not text or len(text) < 3:
        return False

    # 排除不需要搜索的场景
    for pattern in NO_SEARCH_PATTERNS:
        if text.strip() == pattern:
            return False

    # 检查是否包含搜索触发词
    for trigger in SEARCH_TRIGGERS:
        if trigger in text:
            return True

    # 问号结尾且包含疑问词
    if text.rstrip().endswith("?") or text.rstrip().endswith("？"):
        question_words = ["什么", "怎么", "为什么", "哪", "谁", "几", "多少", "是否"]
        for w in question_words:
            if w in text:
                return True

    return False


def extract_search_query(text: str) -> str:
    """
    从用户消息中提取搜索关键词。
    去掉"帮我搜一下"之类的前缀，保留核心内容。
    """
    # 去掉常见前缀
    prefixes = [
        "帮我搜一下", "帮我查一下", "帮我搜", "帮我查",
        "搜一下", "查一下", "搜搜", "查查",
        "你帮我查", "你帮我搜", "你搜一下", "你查一下",
        "百度一下", "谷歌一下", "网上搜一下",
    ]

    query = text.strip()
    for prefix in prefixes:
        if query.startswith(prefix):
            query = query[len(prefix):].strip()
            break

    # 如果提取后太短，用原文
    if len(query) < 2:
        query = text.strip()

    return query
