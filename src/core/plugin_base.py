# by UBAI
"""
plugin_base.py
插件基类 - 所有插件必须继承
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class PluginInfo:
    """插件元信息"""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    triggers: list[str] = field(default_factory=list)  # 触发关键词
    priority: int = 50          # 优先级，数字越小越先执行
    enabled: bool = True
    require_prefix: bool = True  # 是否需要 / 前缀


class PluginBase(ABC):
    """插件基类"""

    def __init__(self):
        self.info = self.get_info()

    @abstractmethod
    def get_info(self) -> PluginInfo:
        """返回插件信息"""
        ...

    @abstractmethod
    def match(self, text: str, user_id: str) -> bool:
        """判断是否匹配当前插件"""
        ...

    @abstractmethod
    async def handle(self, user_id: str, text: str, context: dict) -> str | None:
        """
        处理消息
        context 包含:
            - event: 原始事件对象
            - emotion: 情绪分析结果
            - pipeline: pipeline 实例
            - extra: 额外数据
        返回: 回复文本，None 表示不回复
        """
        ...

    async def on_startup(self):
        """插件启动时调用"""
        pass

    async def on_shutdown(self):
        """插件关闭时调用"""
        pass

    async def on_message_sent(self, user_id: str, reply: str):
        """AI 回复后调用（可用于后处理）"""
        pass
