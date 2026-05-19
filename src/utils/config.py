# by UBAI
import yaml
import os
import time
from .paths import CONFIG_FILE

_config_cache = {}
_last_mtime = 0

def get_config():
    global _config_cache, _last_mtime
    if not os.path.exists(CONFIG_FILE):
        return {}
    
    current_mtime = os.path.getmtime(CONFIG_FILE)
    if current_mtime > _last_mtime:
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                _config_cache = yaml.safe_load(f) or {}
                _last_mtime = current_mtime
        except Exception:
            pass
    return _config_cache
