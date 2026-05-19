# by UBAI
"""
mcp_tools.py
MCP工具注册与管理 - 工具初始化和注册
"""

from . import ToolRegistry, ToolDefinition, create_search_tool, create_url_reader_tool, create_image_analyze_tool


def setup_tools(searcher=None, vision_client=None) -> ToolRegistry:
    """
    初始化并注册所有可用工具。
    
    使用方式：
        from src.mcp.mcp_tools import setup_tools
        tools = setup_tools(searcher=searcher, vision_client=vision_client)
        
        # 注入prompt
        tools_prompt = tools.get_tools_prompt()
        
        # 解析并执行工具调用
        result = await tools.execute_from_text(llm_reply)
    """
    registry = ToolRegistry()

    # 注册搜索工具
    if searcher:
        registry.register(create_search_tool(searcher))

    # 注册URL读取工具
    registry.register(create_url_reader_tool())

    # 注册图像分析工具（可选）
    if vision_client:
        img_tool = create_image_analyze_tool(vision_client)
        if img_tool:
            registry.register(img_tool)

    return registry
