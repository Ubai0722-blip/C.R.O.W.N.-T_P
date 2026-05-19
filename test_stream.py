import asyncio
import yaml
from src.core.llm import LLMClient

async def test():
    llm = LLMClient()
    
    messages = [{"role": "user", "content": "你好，请回复测试"}]
    
    print("Testing stream...")
    async for chunk in llm.chat_stream(messages):
        print(f"CHUNK: {chunk}")
        
    await llm.close()

if __name__ == "__main__":
    asyncio.run(test())
