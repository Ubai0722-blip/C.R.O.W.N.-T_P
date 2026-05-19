# by UBAI
"""
memory_fermentation.py
记忆残缺与发酵系统 (Memory Fermentation)

人回忆事情是不可能像读数据库那样精确到一字不差的，记忆会有衰减（模糊化）。
同时，在夜深人静或者隔天，旧的记忆可能会突然像“走马灯”一样发酵，并成为新的重提话题。
"""

import random
from datetime import datetime, timedelta

class MemoryFermenter:
    def __init__(self, long_memory):
        # 依赖于现有的长期记忆模块来读取记录
        self.lm = long_memory
        
    def fuzzify_recall(self, memory_text: str, timestamp: datetime) -> str:
        """
        把长期记忆提取出来的内容，强制添加“模糊修饰”，喂给LLM的时候假装自己忘了一些细节
        """
        now = datetime.now()
        diff = now - timestamp
        days = diff.days

        if days <= 1:
            return f"[昨日清醒记忆] “我们昨天刚聊到过，{memory_text}”"
        elif days <= 3:
            fuzzy_prefix = random.choice([
                "我有点印象几天前...",
                "如果没记错的话，",
                "我记得你之前是不是说过..."
            ])
            return f"[短期记忆] {fuzzy_prefix}：{memory_text}（让AI用不太确定的语气）"
        elif days <= 14:
            fuzzy_prefix = random.choice([
                "突然想起很久以前你好像提过一嘴",
                "隐约记得...",
                "脑子里有点模糊的印象"
            ])
            return f"[模糊回忆] {fuzzy_prefix}：{memory_text}（让AI用极其模糊、甚至可能有点记错的猜测句式提出来，不要说死）"
        else:
            # 大于两周的深层记忆
            return f"[深层记忆闪回] “哇我脑海深处突然飘过一个很早之前的记忆片段，{memory_text}，当时是这样吗？”"

    def get_nightly_fermentation_topic(self, user_id: str) -> str:
        """
        在主动搭话（比如半夜或第二天早上）时，不要干巴巴地说“早上好”，
        而是把昨天或者前天聊过的一个话题拿出来重新回味（发酵）。
        返回供 LLM 自由发挥的 Prompt 提示。
        """
        # 假设提供一个抽象方法，从数据库或 long_memory 获取过去12~48小时重要度较高的记忆
        # 这里的实现可以对接原有的 long_memory.py
        recent_memories = self.lm.get_records_in_time_range(
            user_id, 
            hours_ago_start=48, 
            hours_ago_end=12,
            min_importance=3 # 只回味比较重要的事情
        )
        
        if not recent_memories:
            return ""
            
        topic = random.choice(recent_memories)
        
        ferment_prompt = (
            f"\n[记忆发酵要求]\n你昨天或者前天下线后，其实脑子里稍微回味了一下这件事：\n"
            f"『{topic.content}』\n"
            f"请在这个主动聊天里，非常自然地起个头，表达一下你对这件事的延后感触或后续关心。\n"
            f"例如：‘唉对了，昨天讲的那个事，你后来怎么处理的呀’\n"
        )
        
        return ferment_prompt
