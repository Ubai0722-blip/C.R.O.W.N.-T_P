# by UBAI
"""
paths.py
自动检测项目根目录，所有路径基于根目录计算
"""
import os

# 项目根目录 = 这个文件往上两级（src/utils/paths.py → src/ → 项目根）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 常用路径
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PERSONAS_DIR = os.path.join(PROJECT_ROOT, "personas")
LOGS_DIR = os.path.join(PROJECT_ROOT, "logs")
NAPCAT_DIR = os.path.join(PROJECT_ROOT, "NapCat")
NAPCAT_BAT = os.path.join(NAPCAT_DIR, "napcat.bat")
NAPCAT_OUTPUT_LOG = os.path.join(NAPCAT_DIR, "napcat_output.log")
QRCODE_PATH = os.path.join(NAPCAT_DIR, "napcat", "cache", "qrcode.png")
DB_PATH = os.path.join(DATA_DIR, "chatbot.db")
HEARTBEAT_FILE = os.path.join(DATA_DIR, "bot_heartbeat.json")
DEBUG_LOG = os.path.join(PROJECT_ROOT, "debug.log")
WATCHDOG_LOG = os.path.join(PROJECT_ROOT, "watchdog.log")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.yaml")
VOICE_DIR = os.path.join(PROJECT_ROOT, "voice")
STICKER_DIR = os.path.join(DATA_DIR, "stickers")


def ensure_dirs():
    """确保所有必要目录存在"""
    for d in [DATA_DIR, LOGS_DIR, VOICE_DIR, STICKER_DIR]:
        os.makedirs(d, exist_ok=True)
