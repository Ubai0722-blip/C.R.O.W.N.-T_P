# by UBAI
"""
typing_simulator.py
物理限制模拟（阅读延迟、打字延迟、偶尔的小错别字纠正）

为了打破 API 秒级生成并瞬间发送的机器感，这套拦截层用于在回复前模拟人类真实的
物理操作耗时，并在极低概率下模拟打错字并在下一秒补发修正的行为。
"""

import asyncio
import random

class TypingSimulator:
    def __init__(self, cpm_read=800, cpm_type=180):
        """
        cpm_read: 每分钟阅读汉字数 (Characters Per Minute)，默认800字/分钟，约 13字/s
        cpm_type: 每分钟打字数，默认180字/分钟，约 3字/s
        """
        self.cps_read = cpm_read / 60.0
        self.cps_type = cpm_type / 60.0

    async def simulate_human_response(self, user_msg: str, ai_reply: str, send_func) -> None:
        """
        send_func: 个异步回调函数，比如 await send_func(msg)
        """
        # 1. 模拟阅读理解耗时
        read_time = len(user_msg) / self.cps_read
        # 加一点思考的随机发呆时间（0~1秒）
        read_time += random.uniform(0.2, 1.2)
        # 上限控制，太长了用户会无语，最多假装读5秒
        read_time = min(read_time, 5.0)
        await asyncio.sleep(read_time)

        # 这里可以调用 NoneBot 的 api 显示正在打字状态
        # await bot.call_api("set_group_special_title" 或相关接口，依场景而定)

        # 2. 模拟打字耗时
        type_time = len(ai_reply) / self.cps_type
        # 人打字时快时慢，加上随机浮动
        type_time *= random.uniform(0.8, 1.3)
        type_time = min(type_time, 15.0)  # 最多让你等15秒
        await asyncio.sleep(type_time)

        # 3. 超真实：手滑发错字纠正机制 (触发率: 3%)
        if len(ai_reply) > 5 and random.random() < 0.03:
            # 假装没打完最后几个字就手滑按下回车，或者少发了一个标点
            cut_idx = max(len(ai_reply) - random.randint(2, 4), len(ai_reply) // 2)
            mistake_msg = ai_reply[:cut_idx]
            correct_append = ai_reply[cut_idx:]
            
            # 第一步，发送截断的话
            await send_func(mistake_msg)
            
            # 第二步，发现没打完，赶紧补上
            await asyncio.sleep(random.uniform(0.8, 1.5))
            await send_func(correct_append)
        else:
            # 正常发送
            await send_func(ai_reply)
