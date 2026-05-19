# by UBAI
"""
mcp_tools.py
MCP风格工具抽象层 - 轻量级实现

设计理念（参考 Model Context Protocol）：
将各种外部能力（搜索、URL读取、图像识别等）抽象为"工具"，
让LLM自己决定什么时候调用什么工具，而不是在pipeline里硬编码。

参考项目：
- FastMCP (github.com/PrefectHQ/fastmcp) - MCP Python框架
- MCP Python SDK (github.com/modelcontextprotocol/python-sdk)
- MCP Servers (github.com/modelcontextprotocol/servers)

本模块是轻量级实现，不依赖官方MCP SDK，用Tool Registry模式。
"""

import json
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any


@dataclass
class ToolDefinition:
    """工具定义（MCP风格）"""
    name: str                        # 工具名称
    description: str                 # 工具描述（给LLM看的）
    parameters: dict                 # JSON Schema格式的参数定义
    handler: Callable[..., Awaitable[Any]] = None  # 实际处理函数
    category: str = "general"        # 工具分类
    requires_auth: bool = False      # 是否需要认证


@dataclass
class ToolCall:
    """工具调用请求"""
    tool_name: str
    arguments: dict


@dataclass
class ToolResult:
    """工具调用结果"""
    tool_name: str
    success: bool
    result: Any = None
    error: str = ""


class ToolRegistry:
    """
    工具注册中心 - MCP风格
    
    使用方式：
        registry = ToolRegistry()
        registry.register(ToolDefinition(
            name="search",
            description="搜索互联网获取最新信息",
            parameters={"query": {"type": "string", "description": "搜索关键词"}},
            handler=search_handler,
        ))
        
        # 注入到LLM的system prompt
        tools_prompt = registry.get_tools_prompt()
        
        # LLM返回工具调用
        result = await registry.execute("search", {"query": "天气"})
    """

    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition):
        """注册一个工具"""
        self._tools[tool.name] = tool

    def unregister(self, name: str):
        """注销一个工具"""
        self._tools.pop(name, None)

    def get_tool(self, name: str) -> ToolDefinition | None:
        """获取工具定义"""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolDefinition]:
        """列出所有已注册的工具"""
        return list(self._tools.values())

    def get_tools_prompt(self) -> str:
        """
        生成工具描述文本，注入到LLM的system prompt中。
        让LLM知道有哪些工具可用，以及如何调用。
        """
        if not self._tools:
            return ""

        lines = ["[可用工具] 你可以使用以下工具来辅助回答："]
        lines.append("")

        for tool in self._tools.values():
            lines.append(f"📦 {tool.name}")
            lines.append(f"   描述：{tool.description}")

            if tool.parameters:
                params = []
                for pname, pdef in tool.parameters.items():
                    ptype = pdef.get("type", "string")
                    pdesc = pdef.get("description", "")
                    params.append(f"{pname}({ptype}): {pdesc}")
                lines.append(f"   参数：{', '.join(params)}")

            lines.append("")

        lines.append(
            "调用工具的格式（在回复中使用）：\n"
            "```tool_call\n"
            '{"tool": "工具名", "params": {"参数名": "参数值"}}\n'
            "```\n"
            "注意：只有在确实需要时才调用工具，日常闲聊不需要。"
        )

        return "\n".join(lines)

    def parse_tool_call(self, text: str) -> ToolCall | None:
        """
        从LLM回复中解析工具调用。
        检测格式：```tool_call\n{"tool": "...", "params": {...}}\n```
        """
        import re
        pattern = r'```tool_call\s*\n(.*?)\n\s*```'
        match = re.search(pattern, text, re.DOTALL)
        if not match:
            return None

        try:
            data = json.loads(match.group(1).strip())
            tool_name = data.get("tool", "")
            params = data.get("params", {})
            if tool_name in self._tools:
                return ToolCall(tool_name=tool_name, arguments=params)
        except json.JSONDecodeError:
            pass

        return None

    async def execute(self, tool_name: str, arguments: dict) -> ToolResult:
        """执行一个工具调用"""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(
                tool_name=tool_name, success=False,
                error=f"工具 '{tool_name}' 不存在",
            )

        if not tool.handler:
            return ToolResult(
                tool_name=tool_name, success=False,
                error=f"工具 '{tool_name}' 没有处理函数",
            )

        try:
            result = await tool.handler(**arguments)
            return ToolResult(tool_name=tool_name, success=True, result=result)
        except Exception as e:
            return ToolResult(
                tool_name=tool_name, success=False,
                error=f"{type(e).__name__}: {str(e)[:200]}",
            )

    async def execute_from_text(self, text: str) -> ToolResult | None:
        """从文本中解析并执行工具调用"""
        call = self.parse_tool_call(text)
        if not call:
            return None
        return await self.execute(call.tool_name, call.arguments)


# ========== 预置工具定义 ==========

def create_search_tool(searcher) -> ToolDefinition:
    """创建搜索工具"""
    async def search_handler(query: str) -> str:
        result = await searcher.search(query)
        if result.success:
            return result.answer
        return f"搜索失败: {result.answer}"

    return ToolDefinition(
        name="search",
        description="搜索互联网获取最新信息。当你不知道某个问题的答案，或者用户要求搜索时使用。",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
        },
        handler=search_handler,
        category="information",
    )


def create_url_reader_tool() -> ToolDefinition:
    """创建URL读取工具"""
    from ..multimodal.url_reader import read_url

    async def url_handler(url: str, max_chars: int = 3000) -> str:
        result = await read_url(url, max_chars)
        if result.success:
            title = f"【{result.title}】\n" if result.title else ""
            return f"{title}{result.content}"
        return f"读取失败: {result.error}"

    return ToolDefinition(
        name="read_url",
        description="读取网页链接的内容。当用户发送了一个链接，或者搜索结果中有链接需要深入查看时使用。",
        parameters={
            "url": {"type": "string", "description": "要读取的URL"},
            "max_chars": {"type": "integer", "description": "最大返回字符数，默认3000"},
        },
        handler=url_handler,
        category="information",
    )


def create_image_analyze_tool(vision_client=None) -> ToolDefinition | None:
    """创建图像分析工具（需要视觉模型）"""
    if not vision_client:
        return None

    async def image_handler(image_path: str, prompt: str = "描述这张图片的内容") -> str:
        result = await vision_client.analyze(image_path, prompt)
        return result

    return ToolDefinition(
        name="analyze_image",
        description="分析图片内容。当用户发送图片并需要理解图片内容时使用。",
        parameters={
            "image_path": {"type": "string", "description": "图片路径或URL"},
            "prompt": {"type": "string", "description": "分析提示，默认为描述图片内容"},
        },
        handler=image_handler,
        category="multimodal",
    )
