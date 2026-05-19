import sys, asyncio
sys.path.insert(0, '.')

async def test():
    from src.core.llm import LLMClient
    from src.cognition.persona import PersonaLoader
    from src.core.pipeline import MessagePipeline
    
    personas = PersonaLoader.load_all("personas")
    llm = LLMClient()
    pipeline = MessagePipeline(llm=llm, personas=personas, default_persona="Theresa")
    
    print("Pipeline created, testing message...")
    try:
        result = await pipeline.process("test_user", "你好", "")
        print(f"Reply: {result[:100] if result else 'EMPTY'}")
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())
