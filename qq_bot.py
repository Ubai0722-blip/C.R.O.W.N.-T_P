import os
import yaml

# 1. 优先读取 config.yaml 并注入环境变量
try:
    with open('config.yaml', 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
        
        # 注入 API Key
        if 'llm' in config and 'api_key' in config['llm']:
            os.environ["OPENAI_API_KEY"] = config['llm']['api_key']
            
        # 注入 API Base URL (注意新版 openai 库识别的是 OPENAI_BASE_URL)
        if 'llm' in config and 'api_base' in config['llm']:
            os.environ["OPENAI_BASE_URL"] = config['llm']['api_base']
            
    print("[OK] config.yaml 环境变量已注入")
except Exception as e:
    print(f"[WARN] config.yaml 读取失败: {e}")


"""
qq_bot.py
NoneBot2 入口，接入 NapCatQQ
"""
import nonebot
from nonebot.adapters.onebot.v11 import Adapter as OneBotV11Adapter

# ========== 初始化 ==========
nonebot.init(
    # NapCatQQ 会连到这个地址
    host="127.0.0.1",
    port=8081,

    # 日志级别，调试时用 DEBUG，正式用 INFO
    log_level="INFO",
)

# 注册 OneBot V11 适配器
driver = nonebot.get_driver()
driver.register_adapter(OneBotV11Adapter)

# 加载插件
nonebot.load_plugins("src/plugins")

if __name__ == "__main__":
    nonebot.run()
