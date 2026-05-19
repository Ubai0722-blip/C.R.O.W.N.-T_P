# by UBAI
# -*- coding: utf-8 -*-
import os
import re
import random
import asyncio
import traceback
import yaml
import nonebot
import datetime
from pathlib import Path
from nonebot import on_message
from nonebot import require
from nonebot.adapters.onebot.v11 import Event, PrivateMessageEvent
from src.cognition.persona import PersonaLoader
from src.memory.database import Database
from src.memory.memory import BufferMemory
from src.core.llm import LLMClient, VLMClient
from src.core.pipeline import MessagePipeline
from src.cognition.life import LifeSystem, LifeScheduler
from src.multimodal.sticker import StickerManager
from src.multimodal.search import WebSearcher
from src.interaction.proactive import ProactiveSystem
from src.interaction.proactive_scheduler import ProactiveScheduler
from src.multimodal.tts import TTSClient
from src.core.weight_manager import WeightManager
nonebot.require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler
from src.core.plugin_manager import PluginManager
from src.utils.paths import HEARTBEAT_FILE, DEBUG_LOG, ensure_dirs
from src.utils.text_filter import strip_invisible, is_effectively_empty
ensure_dirs()


# ========== 日志系统（带轮转）==========
import os as _os

DEBUG_LOG_PATH = DEBUG_LOG
_MAX_LOG_SIZE = 10 * 1024 * 1024  # 10MB
_LOG_BACKUP_COUNT = 3

def _rotate_log():
    """日志轮转：超过 10MB 时轮转，保留最近 3 个备份"""
    try:
        if _os.path.exists(DEBUG_LOG_PATH) and _os.path.getsize(DEBUG_LOG_PATH) > _MAX_LOG_SIZE:
            for i in range(_LOG_BACKUP_COUNT - 1, 0, -1):
                src = f"{DEBUG_LOG_PATH}.{i}"
                dst = f"{DEBUG_LOG_PATH}.{i+1}"
                if _os.path.exists(src):
                    _os.replace(src, dst)
            _os.replace(DEBUG_LOG_PATH, f"{DEBUG_LOG_PATH}.1")
    except:
        pass

# 启动时清空 debug.log
with open(DEBUG_LOG_PATH, "w", encoding="utf-8") as _f:
    _f.write("")

def dlog(msg):
    try:
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
        # 每 100 条日志检查一次轮转
        dlog._counter = getattr(dlog, '_counter', 0) + 1
        if dlog._counter >= 100:
            dlog._counter = 0
            _rotate_log()
    except:
        pass



with open("config.yaml", "r", encoding="utf-8") as f:
    config = yaml.safe_load(f)
# 插件初始化
c = config["llm"]
personas = PersonaLoader.load_all("personas")
llm = LLMClient()
vlm = VLMClient()
weight_manager = WeightManager()
life = LifeSystem(persona_name="Theresa", llm=llm)
life_scheduler = LifeScheduler(life, min_interval=1800, max_interval=3600)
sticker_mgr = StickerManager()
sticker_mgr.set_vlm_client(vlm)
proactive = ProactiveSystem()
plugin_mgr = PluginManager()
plugin_mgr.set_logger(dlog)
plugin_mgr.load_all()
search_conf = config.get("search", {})
searcher = WebSearcher() if search_conf.get("api_key") else None

# ========== TTS 初始化 ==========
tts_conf = config.get("tts", {})
tts_client = TTSClient(
    reference_audio=tts_conf.get("reference_audio", ""),
) if tts_conf.get("enabled", False) else None

if tts_client:
    dlog("[tts] 语音合成已启用")
else:
    dlog("[tts] 语音合成未启用")

pipeline = MessagePipeline(
    llm=llm,
    personas=personas,
    default_persona=config.get("default_persona", "Theresa"),
    life_system=life,
    searcher=searcher,
)
pipeline.debounce_seconds = 7.0
proactive.time_awareness = pipeline.time_awareness
proactive_scheduler = ProactiveScheduler(
    proactive_system=proactive,
    growth_system=pipeline.growth,
    time_awareness=pipeline.time_awareness,
    safety_monitor=pipeline.safety_monitor,
)

# ========== 配置 ==========
PROACTIVE_USERS = [
    517908311,
]
PROACTIVE_CHECK_INTERVAL = 300

dlog("[mychat] loaded " + c["model"])


@nonebot.get_driver().on_startup
async def _():
    # 使用 _spawn_bg 保存 task 引用，防止 GC 回收
    pipeline._spawn_bg(life_scheduler.start())
    pipeline._spawn_bg(_proactive_loop_wrapper())
    await plugin_mgr.notify_startup()
    dlog("[life] scheduler started")
    dlog("[proactive] proactive loop started")

async def _proactive_loop_wrapper():
    """包装 proactive_loop 以便统一异常处理"""
    try:
        await proactive_loop()
    except Exception as e:
        dlog(f"[proactive loop fatal] {e}")

@nonebot.get_driver().on_shutdown
async def _on_shutdown():
    """关闭时清理资源"""
    try:
        await llm.close()
        dlog("[shutdown] llm client closed")
    except Exception as e:
        dlog(f"[shutdown err] {e}")
    try:
        await vlm.close()
        dlog("[shutdown] vlm client closed")
    except Exception as e:
        dlog(f"[shutdown err] {e}")


# 每天凌晨3点自动衰减权重
@scheduler.scheduled_job("cron", hour=3, minute=0)
async def decay_word_weights():
    decayed = weight_manager.decay_weights()
    if decayed:
        dlog(f"[weight] 权重衰减: {', '.join(decayed)}")


# ========== 主动消息循环 ==========
async def proactive_loop():
    # 从配置读取参数
    proactive_conf = config.get("proactive", {})
    boot_cooldown = proactive_conf.get("boot_cooldown_minutes", 5)
    quiet_start = proactive_conf.get("quiet_hours_start", 0)
    quiet_end = proactive_conf.get("quiet_hours_end", 7)
    mutter_enabled = proactive_conf.get("mutter_enabled", True)
    care_chance = proactive_conf.get("care_trigger_chance", 0.8)
    check_interval = proactive_conf.get("interval_hours", 0.5) * 3600  # 转为秒

    proactive.boot_cooldown_minutes = boot_cooldown

    # 开机等待
    await asyncio.sleep(boot_cooldown * 60)
    dlog(f"[proactive] 主动消息循环启动（已等待{boot_cooldown}分钟）")

    while True:
        try:
            now = datetime.datetime.now()
            hour = now.hour

            # 深夜静默
            if quiet_start <= hour < quiet_end:
                await asyncio.sleep(300)
                continue

            for qq_id in PROACTIVE_USERS:
                user_id = f"qq_{qq_id}"
                pending_count = pipeline.get_pending_count(user_id)
                if pending_count > 0:
                    dlog(f"[proactive] 跳过: user={user_id}, type=chat_pending, reason=pending_count={pending_count}")
                    continue
                if user_id in _pending_events:
                    dlog(f"[proactive] 跳过: user={user_id}, type=chat_pending, reason=event_pending")
                    continue
                active_until = _chat_active_until.get(user_id)
                if active_until and now < active_until:
                    remain = max(1, int((active_until - now).total_seconds()))
                    dlog(f"[proactive] 跳过: user={user_id}, type=chat_active, reason=remain_{remain}s")
                    continue
                profile = pipeline.growth.get_profile(user_id)
                level = profile.relationship_level
                decision = proactive_scheduler.decide(user_id, level, proactive_conf)
                if not decision.should_send:
                    dlog(f"[proactive] 跳过: user={user_id}, type={decision.trigger_type}, reason={decision.reason}")
                    continue
                sent = await _send_proactive_message(qq_id, user_id, decision.extra_context, decision)
                if sent:
                    proactive_scheduler.mark_sent(decision)
                    if decision.trigger_type == "mutter":
                        proactive.record_mutter(user_id)
                    else:
                        proactive.record_sent(user_id, "proactive")
                    await asyncio.sleep(random.uniform(5, 15))
                else:
                    proactive_scheduler.mark_failed(decision, "empty_or_send_failed")

            # 检查间隔
            await asyncio.sleep(check_interval)

        except Exception as e:
            dlog(f"[proactive loop err] {e}")
            await asyncio.sleep(60)


async def _send_proactive_message(qq_id: int, user_id: str, extra_context: str, decision=None) -> bool:
    """发送主动消息的统一入口"""
    try:
        trigger = getattr(decision, "trigger_type", "manual")
        reason = getattr(decision, "reason", "")
        dlog(f"[proactive] 触发主动消息给 {qq_id}: {trigger} {reason}")
        allowed, safety_reason = pipeline.safety_monitor.proactive_precheck(user_id)
        if not allowed:
            dlog(f"[proactive] SafetyPrecheck 拦截: {safety_reason}")
            return False
        reply = await pipeline.generate_proactive_reply(user_id, extra_context=extra_context)
        if not reply:
            return False

        bot = nonebot.get_bot()
        reply = _clean_bracket_actions(reply)
        reply = _control_filler_words(reply)
        if not reply.strip():
            return False
        parts = _split_ai_marked_messages(reply)
        if len(parts) <= 1:
            final_text = parts[0] if parts else reply.replace("|||", "").strip()
            await bot.call_api(
                "send_private_msg",
                user_id=int(qq_id),
                message=final_text,
            )
        else:
            for i, part in enumerate(parts):
                await bot.call_api(
                    "send_private_msg",
                    user_id=int(qq_id),
                    message=part,
                )
                if i < len(parts) - 1:
                    await asyncio.sleep(random.uniform(3.0, 5.0))
        dlog(f"[proactive] 已发送: {reply[:50]}")
        return True
    except Exception as e:
        dlog(f"[proactive err] {e}")
        return False

# ========== 消息拆分 ==========
def _split_ai_marked_messages(text: str) -> list[str]:
    """Split when the model marks separate chat messages with ||| or line breaks."""
    if not text:
        return []

    marked_text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    # 兼容模型把换行输出成字面量 "\\n" 的场景。
    marked_text = re.sub(r'\\n+', '\n', marked_text)
    marked_text = marked_text.replace("|||", "\n")
    parts = [p.strip() for p in marked_text.splitlines() if p.strip()]
    if parts:
        return parts

    stripped = text.strip()
    return [stripped] if stripped else []


def split_message(text: str) -> list[str]:
    if not text:
        return []

    raw_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            raw_lines.append(line)

    segments = []
    for line in raw_lines:
        if len(line) > 80:
            parts = re.split(r'(?<=[。！？.!?~])', line)
            for p in parts:
                p = p.strip()
                if p:
                    segments.append(p)
        else:
            segments.append(line)

    if not segments:
        return [text]

    merged = []
    buffer = ""
    for seg in segments:
        if len(buffer) > 0 and len(buffer) + len(seg) < 10:
            buffer += seg
        else:
            if buffer:
                merged.append(buffer)
            buffer = seg
    if buffer:
        merged.append(buffer)

    return merged if merged else [text]

# ========== 发送文字 ==========
def _clean_bracket_actions(text: str) -> str:
    """删除括号内的动作描述，如（歪头）（笑）*眨眼*"""
    text = re.sub(r'（[^）]{1,10}）', '', text)
    text = re.sub(r'$$[^)]{1,10}$$', '', text)
    text = re.sub(r'\*[^*]{1,10}\*', '', text)
    # 清理多余空格
    text = re.sub(r'  +', ' ', text).strip()
    return text

# ========== 语气词频率控制 ==========
_FILLER_WORDS = set('嗯啊哦噢呃额唉哎呀哇嘛呢吧啦哈')
_FILLER_MAX_RATIO = 0.2

def _control_filler_words(text: str) -> str:
    """控制语气词出现频率，使其不超过 0.2"""
    if not text:
        return text
    text = re.sub(r'^\s*[嗯哦噢啊呃额][，,。.、\s]+', '', text).strip()
    if len(text) <= 1:
        return text
    # 统计语气词
    filler_count = sum(1 for ch in text if ch in _FILLER_WORDS)
    total_chars = len(text.replace(' ', '').replace('\n', ''))
    if total_chars == 0:
        return text
    ratio = filler_count / total_chars
    if ratio <= _FILLER_MAX_RATIO:
        return text
    # 需要减少语气词：保留第一个，后续按概率保留
    target_count = int(total_chars * _FILLER_MAX_RATIO)
    need_remove = filler_count - max(target_count, 1)
    if need_remove <= 0:
        return text
    result = []
    removed = 0
    first_found = False
    for ch in text:
        if ch in _FILLER_WORDS:
            if not first_found:
                first_found = True
                result.append(ch)
            elif removed < need_remove:
                # 按概率决定是否删除
                if random.random() < 0.7:
                    removed += 1
                    continue
                else:
                    result.append(ch)
            else:
                result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)

def _is_whitelisted(qq_id: str) -> bool:
    """检查QQ号是否在白名单中"""
    try:
        from src.memory.database import Database
        db = Database()
        with db.get_conn() as conn:
            # 如果白名单表为空（首次运行），自动添加第一个用户
            count = conn.execute("SELECT COUNT(*) FROM chat_whitelist").fetchone()[0]
            if count == 0:
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute(
                    "INSERT OR IGNORE INTO chat_whitelist (qq_id, enabled, first_seen, last_seen) VALUES (?, 1, ?, ?)",
                    (qq_id, now, now)
                )
                dlog(f"[whitelist] 首次运行，自动添加用户 {qq_id}")
                return True
            # 检查是否在白名单中且已启用
            row = conn.execute(
                "SELECT enabled FROM chat_whitelist WHERE qq_id = ?", (qq_id,)
            ).fetchone()
            if row and row[0]:
                # 更新最后活跃时间
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("UPDATE chat_whitelist SET last_seen = ? WHERE qq_id = ?", (now, qq_id))
                return True
            return False
    except Exception as e:
        dlog(f"[whitelist err] {e}")
        return True  # 出错时放行，避免锁死


def _auto_split(text, max_len=100):
    """自动拆分长消息"""
    if len(text) <= max_len:
        return [text]

    parts = []
    remaining = text

    while remaining:
        if len(remaining) <= max_len:
            parts.append(remaining.strip())
            break

        chunk = remaining[:max_len]
        cut = _find_cut(chunk)

        parts.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    return [m for m in parts if m]


def _find_cut(text):
    """找最佳切割点"""
    max_len = len(text)
    # 段落分隔
    idx = text.rfind('\n\n')
    if idx > len(text) * 0.3:
        return idx + 2

    # 句号
    for punct in ['。', '！', '？', '!', '?']:
        idx = text.rfind(punct)
        if idx > len(text) * 0.3:
            return idx + 1

    # 换行
    idx = text.rfind('\n')
    if idx > len(text) * 0.3:
        return idx + 1

    # 分号冒号
    for punct in ['；', '：', ';', ':']:
        idx = text.rfind(punct)
        if idx > len(text) * 0.3:
            return idx + 1

    # 逗号
    for punct in ['，', ',', '、']:
        idx = text.rfind(punct)
        if idx > len(text) * 0.3:
            return idx + 1

    # 空格
    idx = text.rfind(' ')
    if idx > len(text) * 0.3:
        return idx + 1

    # 硬切
    return max_len

async def _ai_learn_weights(pipeline, user_id, recent_messages):
    """每30条消息用AI判断是否需要录入权重"""
    try:
        # 收集最近的对话内容
        msgs_text = ""
        for msg in recent_messages[-15:]:
            role = "用户" if msg["role"] == "user" else "AI"
            msgs_text += f"{role}: {msg['content'][:60]}\n"

        if not msgs_text.strip():
            return

        prompt = (
            "以下是最近的对话记录。请分析用户反复提到的、明显感兴趣的关键词或话题。\n"
            "只输出值得记录的关键词，每行一个，格式：词:权重(0.1~5.0):分类\n"
            "如果用户没有明显反复提到的话题，只输出：无\n\n"
            f"{msgs_text}\n\n"
            "示例输出：\n吉他:3.0:兴趣\n编程:2.5:工作\n\n"
            "你的输出："
        )

        messages = [{"role": "user", "content": prompt}]
        result = await pipeline.llm.chat(messages)

        if not result or "无" in result.strip()[:5]:
            return

        for line in result.strip().split("\n"):
            line = line.strip()
            if ":" not in line or not line:
                continue
            parts = line.split(":")
            if len(parts) >= 2:
                word = parts[0].strip()
                try:
                    weight = float(parts[1].strip())
                except:
                    weight = 2.0
                category = parts[2].strip() if len(parts) >= 3 else "AI识别"
                weight = max(0.1, min(5.0, weight))
                if word and len(word) >= 2:
                    pipeline.weight_manager.set_weight(word, weight, category)
                    dlog(f"[weight] AI识别: {word} = {weight} [{category}]")

    except Exception as e:
        dlog(f"[weight learn err] {e}")


async def send_msg(event: PrivateMessageEvent, text: str, emotion: str = "平静", reply_to: int = 0, is_cmd: bool = False):
    """发送消息；只有 AI 明确使用 ||| 时才拆成多条。"""
    if not text:
        return

    # 删除括号动作
    text = _clean_bracket_actions(text)
    if not text:
        return

    # 控制语气词频率
    text = _control_filler_words(text)

    bot = nonebot.get_bot()

    parts = _split_ai_marked_messages(text)

    # 如果是命令，就强制视为一条
    if is_cmd and parts:
        parts = ["\n".join(parts)]

    # 只有一条且很短，直接发
    if len(parts) <= 1:
        final_text = parts[0] if parts else text

        if reply_to:
            message = f"[CQ:reply,id={reply_to}]{final_text}"
        else:
            message = final_text

        await bot.call_api(
            "send_private_msg",
            user_id=event.user_id,
            message=message,
        )

    else:
        for i, part in enumerate(parts):
            if i == 0 and reply_to:
                message = f"[CQ:reply,id={reply_to}]{part}"
            else:
                message = part

            await bot.call_api(
                "send_private_msg",
                user_id=event.user_id,
                message=message,
            )
            if i < len(parts) - 1:
                # 给大模型普通聊天消息添加2-5秒发送间隔
                sleep_time = random.uniform(2.0, 5.0) if not is_cmd else 0.1
                await asyncio.sleep(sleep_time)


# ========== 发送语音 ==========
async def send_voice(event, silk_path: str) -> bool:
    """发送语音消息"""
    bot = nonebot.get_bot()
    try:
        abs_path = os.path.abspath(silk_path)
        await bot.call_api(
            "send_private_msg",
            user_id=event.user_id,
            message=f"[CQ:record,file=file:///{abs_path}]",
        )
        dlog(f"[voice] 已发送语音：{silk_path}")
        return True
    except Exception as e:
        dlog(f"[voice] 发送失败：{e}")
        return False


# ========== 语音回复判断 ==========
VVOICE_REPLY_CHANCE = 0.03  # 3% 概率发语音

def _is_explicit_voice_request(user_text: str) -> bool:
    """是否是用户明确要求“这次就发语音”"""
    text = (user_text or "").strip()
    if not text:
        return False
    keywords = [
        "发语音", "语音回复", "用语音", "语音说", "说给我听",
        "念出来", "读出来", "读给我听", "你说话", "直接语音",
    ]
    if any(kw in text for kw in keywords):
        return True
    # 较宽松兜底：包含“语音”且伴随请求语气词
    if "语音" in text and any(kw in text for kw in ["要", "请", "给我", "用", "来", "行不行", "可以吗", "好吗"]):
        return True
    return False

def _should_voice_reply(user_text: str, ai_reply: str) -> bool:
    """随机语音策略（不含“明确语音请求”分支）"""

    # 回复太长不发语音
    if len(ai_reply) > 80:
        dlog(f"[voice] 跳过：回复太长({len(ai_reply)}字)")
        return False

    # 回复太短不发语音
    if len(ai_reply) < 2:
        dlog(f"[voice] 跳过：回复太短({len(ai_reply)}字)")
        return False

    # 包含代码/链接/特殊格式不发语音
    if any(ch in ai_reply for ch in ["http", "|", "```", "|||"]):
        dlog(f"[voice] 跳过：包含代码或链接")
        return False

    # 3% 概率随机发语音
    hit = random.random() < VVOICE_REPLY_CHANCE
    dlog(f"[voice] 随机判断：{'命中' if hit else '未命中'} (概率{VVOICE_REPLY_CHANCE*100}%)")
    return hit



# ========== 消息解析 ==========
def parse_message(event: PrivateMessageEvent) -> dict:
    result = {
        "text": "",
        "images": [],
        "stickers": [],
        "faces": [],
        "files": [],
        "forwarded": [],
        "quoted": "",
    }
    msg = event.message

    for seg in msg:
        if seg.type == "text":
            text = seg.data.get("text", "").strip()
            if text:
                result["text"] += text

        elif seg.type == "image":
            url = seg.data.get("url", "")
            sub_type = seg.data.get("sub_type", 0)
            if sub_type == 1:
                result["stickers"].append(url)
                dlog(f"[parse] sticker: {url[:60]}")
            else:
                result["images"].append(url)
                dlog(f"[parse] image: {url[:60]}")

        elif seg.type == "face":
            face_id = seg.data.get("id", "")
            result["faces"].append(face_id)

        elif seg.type == "forward":
            # 转发消息，记录 ID
            forward_id = seg.data.get("id", "")
            if forward_id:
                result["forwarded"].append(forward_id)
        elif seg.type == "reply":
            # 引用消息，获取被引用的消息 ID
            msg_id = seg.data.get("id", "")
            if msg_id:
                result["quoted"] = msg_id

        elif seg.type == "file":
            result["files"].append({
                "file_id": seg.data.get("file_id", ""),
                "file_name": seg.data.get("file", "未知文件"),
                "file_size": seg.data.get("file_size", 0),
            })

    return result


# ========== 时间提及检测 ==========
_TIME_KEYWORDS = [
    "明天", "后天", "大后天", "昨天", "前天",
    "下周", "下个月", "这周", "本周", "这月", "本月",
    "周一", "周二", "周三", "周四", "周五", "周六", "周日",
    "星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日",
    "上午", "下午", "晚上", "中午", "凌晨", "早上", "傍晚",
    "今天", "今晚", "明早", "明晚",
    "周末", "假期", "过年",
]

_TIME_REGEX_PATTERNS = [
    r"(今天|明天|后天|大后天|昨天|前天)",
    r"(上午|中午|下午|晚上|凌晨|早上|傍晚|今晚|明早|明晚)",
    r"(周[一二三四五六日天末]|星期[一二三四五六日天])",
    r"(\d{1,2}\s*[:：]\s*\d{1,2})",
    r"(\d{1,2}\s*点\s*半?)",
    r"(\d+\s*(分钟|小时)\s*后)",
    r"(下周|这周|本周|下个月|这月|本月|周末|假期|过年)",
]

def _extract_time_mentions(text: str) -> list[str]:
    """提取更可靠的时间提及，避免把“有点”“差点”误判成时间。"""
    found = []

    for kw in _TIME_KEYWORDS:
        if kw in text and kw not in found:
            found.append(kw)

    for pattern in _TIME_REGEX_PATTERNS:
        for m in re.finditer(pattern, text):
            val = (m.group(1) if m.lastindex else m.group(0)).strip()
            if val and val not in found:
                found.append(val)

    return found

def _check_time_mentions(user_id: str, text: str) -> None:
    """检测用户消息中是否提到了时间，如果有则存储"""
    if not text:
        return
    mentioned = _extract_time_mentions(text)
    if not mentioned:
        return

    # 尝试从文本中提取时间描述
    time_desc = "、".join(mentioned[:3])  # 取前3个关键词作为描述
    context = text[:100]  # 保留上下文

    try:
        from datetime import timedelta
        db = Database()
        # 计算 expires_at：默认为提及时间 + 12 小时
        # 由于无法精确解析用户提到的时间，使用创建时间 + 12 小时
        expires_at = (datetime.datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
        db.save_time_mention(
            user_id=user_id,
            mentioned_time=time_desc,
            context=context,
            expires_at=expires_at,
        )
        dlog(f"[time] 检测到时间提及: user={user_id}, time={time_desc}")
    except Exception as e:
        dlog(f"[time mention err] {e}")


# ========== 存储 ==========
_pending_events: dict[str, PrivateMessageEvent] = {}
_pending_emotions: dict[str, str] = {}
_pending_texts: dict[str, str] = {} 
_pending_msg_ids: dict[str, int] = {}  # 新增：存储用户消息ID
_chat_active_until: dict[str, datetime.datetime] = {}


# ========== 私聊 ==========
ph = on_message(priority=10, block=True)


@ph.handle()

async def handle_private(event: PrivateMessageEvent):
    try:

        parsed = parse_message(event)
        text = parsed["text"]
        images = parsed["images"]
        stickers = parsed["stickers"]
        faces = parsed["faces"]
        files = parsed["files"]
        forwarded = parsed["forwarded"]

        # ========== 不可见字符过滤 ==========
        text = strip_invisible(text)
        # 如果去掉不可见字符后文本为空，且没有其他媒体内容，直接忽略
        if is_effectively_empty(text) and not images and not stickers and not faces and not files:
            dlog("[p] 过滤后为空消息（仅含不可见字符），跳过")
            return

        # ========== 白名单检查 ==========
        raw_qq = str(event.user_id)
        if not _is_whitelisted(raw_qq):
            dlog(f"[p] 用户 {raw_qq} 不在白名单中，忽略")
            return

        dlog(
            f"[p] text='{text}' "
            f"images={len(images)} "
            f"stickers={len(stickers)} "
            f"faces={len(faces)} "
            f"files={len(files)}"
            f"forwarded={len(forwarded)}"
        )

        user_id = "qq_" + str(event.user_id)
        _pending_events[user_id] = event
        active_secs = int(config.get("proactive", {}).get("active_chat_cooldown_seconds", 120) or 120)
        _chat_active_until[user_id] = datetime.datetime.now() + datetime.timedelta(seconds=max(30, active_secs))

        # 刷新碎碎念冷却（防止碎碎念插入对话）
        try:
            proactive.db.set_user(user_id)
            proactive.refresh_mutter_cooldown(user_id)
            proactive.record_proactive(user_id)
        except Exception as cooldown_err:
            dlog(f"[proactive] 冷却刷新失败: user={user_id}, err={cooldown_err}")

        session = pipeline.get_session(user_id)

        # ========== 时间提及检测 ==========
        _check_time_mentions(user_id, text)

        # ========== 命令处理 ==========
        if text.startswith("/"):
            cmd = text.split(" ", 1)[0]
            args = text.split(" ", 1)[1] if len(text.split(" ", 1)) > 1 else ""
            # ========== 全局菜单指令 ==========
            if cmd in ["/cmd", "/help", "/菜单"]:
                bot = nonebot.get_bot()
                help_menu = (
                    "✨ 机器人全局控制面板 ✨\n\n"
                    "🔧 基础控制\n"
                    "/clear - 清空当前对话上下文\n"
                    "/debug - 查看后台核心运行数据\n"
                    "/恋人模式 开/关 - 切换专属沉浸式聊天视角\n"
                    "/reload_scenes - 重载场景情绪配置\n\n"
                    "🧠 记忆与羁绊\n"
                    "/memory - 查看 AI 为你生成的长期记忆摘要\n"
                    "/forget [关键词] - 让 AI 遗忘某条关于你的记忆\n"
                    "/profile - 查看好感度等级与话题偏好分析\n\n"
                    "📊 偏好权重调节\n"
                    "/weight list - 查看目前高频触发的话题库\n"
                    "/weight help - 查看完整的权重管理指令\n\n"
                    "🔍 调试观测\n"
                    "/persona - 查看当前人格状态与残差分析\n"
                    "/drift - 查看人格漂移检测统计\n"
                    "/narrative - 手动触发一次叙事自我表露\n\n"
                    "💕 关系管理\n"
                    "/relationship - 查看当前关系状态与可切换类型\n"
                    "/relationship [类型] - 切换关系类型（如 lover/bestie/mentor/pet）\n\n"
                    "🔌 扩展功能插件\n"
                    "/plugin list - 查看所有插件及当前开关状态\n"
                    "/plugin on [插件名] - 开启指定的插件\n"
                    "/plugin off [插件名] - 关闭指定的插件"
                )
                await bot.call_api("send_private_msg", user_id=event.user_id, message=help_menu)
                return
            user_id = "qq_" + str(event.user_id)

            
            # ========== 插件管理指令 ==========
            if cmd == "/plugin":
                bot = nonebot.get_bot()
                if not args or args.strip() == "list":
                    plugins = plugin_mgr.list_plugins()
                    if not plugins:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="没有已加载的插件")
                    else:
                        lines = ["🔌 已安装插件：\n"]
                        for p in plugins:
                            status = "✅" if p["enabled"] else "❌"
                            triggers = ", ".join(p["triggers"]) if p["triggers"] else "AI判断"
                            lines.append(f"{status} {p['name']} v{p['version']}")
                            lines.append(f"   {p['description']}")
                            lines.append(f"   触发: {triggers}")
                            lines.append("")
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="\n".join(lines))

                elif args.strip() == "help":
                    help_text = (
                        "🔌 插件管理指令：\n\n"
                        "/plugin list       - 查看所有插件\n"
                        "/plugin on 插件名   - 启用插件\n"
                        "/plugin off 插件名  - 禁用插件\n"
                        "/plugin reload 插件名 - 重载插件\n"
                        "/plugin help       - 查看帮助"
                    )
                    await bot.call_api("send_private_msg", user_id=event.user_id, message=help_text)

                elif args.startswith("on "):
                    name = args[3:].strip()
                    if plugin_mgr.enable(name):
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"✅ 已启用插件: {name}")
                    else:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"❌ 未找到插件: {name}")

                elif args.startswith("off "):
                    name = args[4:].strip()
                    if plugin_mgr.disable(name):
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"❌ 已禁用插件: {name}")
                    else:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"❌ 未找到插件: {name}")

                elif args.startswith("reload "):
                    name = args[7:].strip()
                    if plugin_mgr.reload(name):
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"🔄 已重载插件: {name}")
                    else:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"❌ 重载失败: {name}")

                else:
                    await bot.call_api("send_private_msg", user_id=event.user_id, message="❌ 未知指令，输入 /plugin help 查看帮助")

                return

            # ========== 权重管理指令 ==========
            if cmd == "/weight":
                bot = nonebot.get_bot()
                wparts = text.split()

                if len(wparts) == 1:
                    help_text = (
                        "📊 词条权重管理指令：\n\n"
                        "/weight list          - 查看所有权重\n"
                        "/weight chart         - 可视化图表\n"
                        "/weight stats         - 分类统计\n"
                        "/weight get 词条      - 查看单个权重\n"
                        "/weight set 词条 数值 - 设置权重\n"
                        "/weight del 词条      - 删除词条\n"
                        "/weight search 关键词 - 搜索词条\n"
                        "/weight add 词条 数值 分类 - 添加词条\n\n"
                        "权重范围：0.1 ~ 10.0\n"
                        "数值越大，AI 越容易提到这个词"
                    )
                    await bot.call_api("send_private_msg", user_id=event.user_id, message=help_text)

                elif wparts[1] == "list":
                    items = weight_manager.get_all()
                    if not items:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="暂无权重数据")
                    else:
                        lines = [f"📊 共 {len(items)} 个词条：\n"]
                        for i, item in enumerate(items[:20], 1):
                            lines.append(f"{i}. {item['word']} = {item['weight']:.1f} [{item['category']}]")
                        if len(items) > 20:
                            lines.append(f"\n... 还有 {len(items)-20} 个")
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="\n".join(lines))

                elif wparts[1] == "chart":
                    chart = weight_manager.get_chart()
                    await bot.call_api("send_private_msg", user_id=event.user_id, message=chart)

                elif wparts[1] == "stats":
                    stats = weight_manager.get_category_stats()
                    await bot.call_api("send_private_msg", user_id=event.user_id, message=stats)

                elif wparts[1] == "get" and len(wparts) >= 3:
                    word = wparts[2]
                    w = weight_manager.get_weight(word)
                    await bot.call_api("send_private_msg", user_id=event.user_id, message=f"「{word}」的权重：{w:.1f}")

                elif wparts[1] == "set" and len(wparts) >= 4:
                    word = wparts[2]
                    try:
                        weight = float(wparts[3])
                        weight = max(0.1, min(10.0, weight))
                        weight_manager.set_weight(word, weight)
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"✅ 已设置「{word}」权重为 {weight:.1f}")
                    except ValueError:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="❌ 权重必须是数字")

                elif wparts[1] == "del" and len(wparts) >= 3:
                    word = wparts[2]
                    if weight_manager.delete(word):
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"✅ 已删除「{word}」")
                    else:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"❌ 未找到「{word}」")

                elif wparts[1] == "search" and len(wparts) >= 3:
                    keyword = wparts[2]
                    results = weight_manager.search(keyword)
                    if not results:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"未找到包含「{keyword}」的词条")
                    else:
                        lines = [f"🔍 搜索「{keyword}」结果：\n"]
                        for item in results[:10]:
                            lines.append(f"  {item['word']} = {item['weight']:.1f} [{item['category']}]")
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="\n".join(lines))

                elif wparts[1] == "add" and len(wparts) >= 4:
                    word = wparts[2]
                    try:
                        weight = float(wparts[3])
                        weight = max(0.1, min(10.0, weight))
                        category = wparts[4] if len(wparts) >= 5 else "默认"
                        weight_manager.set_weight(word, weight, category)
                        await bot.call_api("send_private_msg", user_id=event.user_id, message=f"✅ 已添加「{word}」权重 {weight:.1f} [{category}]")
                    except ValueError:
                        await bot.call_api("send_private_msg", user_id=event.user_id, message="❌ 权重必须是数字")

                else:
                    await bot.call_api("send_private_msg", user_id=event.user_id, message="❌ 指令格式错误，输入 /weight 查看帮助")

                return
                        # ========== 查看记忆 ==========
            if cmd == "/memory":
                memories = pipeline.get_session(user_id).long_memory.get_all_memories()
                if not memories:
                    await send_msg(event, "还没有记住关于你的事情", is_cmd=True)
                else:
                    lines = [f"共记住了 {len(memories)} 件事："]
                    for m in memories[-15:]:
                        lines.append(f"- [{m.category}] {m.content}（重要度:{m.importance} 访问:{m.access_count}次）")
                    await send_msg(event, "\n".join(lines), is_cmd=True)
                return

            # ========== 调试信息 ==========
            if cmd == "/debug":
                session = pipeline.get_session(user_id)
                profile = pipeline.growth.get_profile(user_id)
                level_info = pipeline.growth._check_level_info(profile)
                is_lover = pipeline.growth.is_lover_mode(user_id)

                lines = [
                    "🔧 调试信息：\n",
                    f"用户ID：{user_id}",
                    f"亲密度：{level_info['name']}（{profile.relationship_level}/10）",
                    f"经验值：{profile.relationship_exp}/{level_info['exp_needed']}",
                    f"恋人模式：{'开启' if is_lover else '关闭'}",
                    f"认识天数：{profile.total_days}",
                    f"消息总数：{profile.total_messages}",
                    f"对话历史：{len(session.memory.messages)} 条(内存)",
                    f"长期记忆：{len(session.long_memory.get_all_memories())} 条",
                    f"共同经历：{profile.shared_experiences} 次",
                    f"情感共鸣：{profile.emotional_bonds} 次",
                ]

                if profile.favorite_topics:
                    sorted_topics = sorted(profile.favorite_topics.items(), key=lambda x: x[1], reverse=True)[:5]
                    topics = "、".join(f"{t[0]}({t[1]})" for t in sorted_topics)
                    lines.append(f"常聊话题：{topics}")

                if profile.growth_memories:
                    lines.append(f"\n最近成长记忆：")
                    for m in profile.growth_memories[-3:]:
                        emotion_str = f"（{m['emotion']}）" if m.get("emotion") and m["emotion"] != "平静" else ""
                        lines.append(f"  - [{m['category']}] {m['event']}{emotion_str}")

                await send_msg(event, "\n".join(lines), is_cmd=True)
                return


            # ========== 恋人模式（联动关系系统）==========
            if cmd == "/恋人模式":
                if args.strip() in ["开", "开启", "on", "true"]:
                    pipeline.growth.set_lover_mode(user_id, True)
                    pipeline.relationship.set_active_type(user_id, "lover")
                    await send_msg(event, "恋人模式已开启", is_cmd=True)
                elif args.strip() in ["关", "关闭", "off", "false"]:
                    pipeline.growth.set_lover_mode(user_id, False)
                    pipeline.relationship.set_active_type(user_id, "default")
                    await send_msg(event, "恋人模式已关闭", is_cmd=True)
                else:
                    is_on = pipeline.growth.is_lover_mode(user_id)
                    status = "开启" if is_on else "关闭"
                    await send_msg(event, f"恋人模式当前：{status}\n发送 /恋人模式 开 或 /恋人模式 关 来切换", is_cmd=True)
                return

            # ========== 重载场景 ==========
            if cmd == "/reload_scenes":
                pipeline.scene.reload()
                await send_msg(event, f"已重新加载场景配置，共 {len(pipeline.scene.scenes)} 个场景，{len(pipeline.scene.tones)} 个语气", is_cmd=True)
                return

            # ========== 人格状态观测 ==========
            if cmd == "/persona":
                session = pipeline.get_session(user_id)
                persona_ctrl = session.persona_controller
                pad_bridge = session.pad_bridge

                lines = ["🎭 人格状态面板：\n"]

                # PAD 情感状态提示
                if pad_bridge:
                    pad_ctx = pad_bridge.get_prompt_context()
                    if pad_ctx:
                        lines.append(f"📊 PAD 情感状态：")
                        lines.append(f"  {pad_ctx[:200]}")
                    else:
                        lines.append("📊 PAD 情感状态：平静（无显著偏移）")
                    lines.append("")

                # 残差分析与可采纳性
                if persona_ctrl:
                    lines.append(persona_ctrl.get_status_text())
                else:
                    lines.append("人格控制：未初始化")

                await send_msg(event, "\n".join(lines), is_cmd=True)
                return

            # ========== 漂移检测统计 ==========
            if cmd == "/drift":
                drift = pipeline.drift_detector
                stats_text = drift.get_stats(user_id)
                await send_msg(event, stats_text, is_cmd=True)
                return

            # ========== 手动触发叙事 ==========
            if cmd == "/narrative":
                session = pipeline.get_session(user_id)
                try:
                    narrative = pipeline.narrative_engine
                    # 随机选择叙事类型
                    ntype = narrative.pick_narrative_type("manual")
                    persona = pipeline._get_persona(session)
                    result = await narrative.generate_narrative(
                        user_id=user_id,
                        narrative_type=ntype,
                        persona_name=persona.name,
                        current_emotion=pipeline.emotion.get_mood_hint(user_id) or "平静",
                    )
                    if result:
                        await send_msg(event, result)
                    else:
                        await send_msg(event, "现在没有什么想说的", is_cmd=True)
                except Exception as e:
                    dlog(f"[narrative err] {e}")
                    await send_msg(event, "叙事引擎出了点问题", is_cmd=True)
                return

            # ========== 切换人设 ==========
            if cmd == "/switch_persona" or cmd == "/切换人设":
                target = args.strip()
                if target in pipeline.personas:
                    pipeline.default_persona = target
                    # 清除旧人设的关系上下文，让新人设重新加载
                    for p in pipeline.personas.values():
                        p.relationship_context = ""
                    # 更新所有现有session
                    for sid, session in pipeline.sessions.items():
                        session.current_persona_key = target
                    # 切换数据库
                    pipeline.db.set_persona(target)
                    # 关系桥接：切换人设后异步加载关系上下文
                    await pipeline._ensure_relationship_loaded(
                        pipeline.get_session(event.user_id)
                    )
                    await send_msg(event, f"人设已切换为: {target}", is_cmd=True)
                else:
                    available = ", ".join(pipeline.personas.keys())
                    await send_msg(event, f"可用人设: {available}", is_cmd=True)
                return
            # ========== 关系管理 ==========
            if cmd == "/relationship":
                args = text.split(" ", 1)
                if len(args) > 1 and args[1].strip():
                    # 切换关系类型
                    target_type = args[1].strip().lower()
                    success, msg = pipeline.relationship.set_active_type(user_id, target_type)
                    await send_msg(event, msg, is_cmd=True)
                else:
                    # 查看当前关系状态
                    status = pipeline.relationship.get_status_text(user_id)
                    await send_msg(event, status, is_cmd=True)
                return


        # ========== 情况1：表情包 ==========
        if stickers:
            dlog(f"[p] 表情包，{len(stickers)}张")

            for sticker_url in stickers:
                local_path = sticker_mgr.save_sticker(sticker_url, user_id)
                if local_path:
                    dlog(f"[sticker] saved: {local_path}")

                try:
                    # 先尝试 VLM 分析表情包
                    sticker_analysis = await sticker_mgr.analyze_with_vlm(
                        local_path or sticker_url,
                        qq_tag=text if text else "",
                    )
                    dlog(f"[sticker] VLM 分析: {sticker_analysis.description[:80]}")
                    dlog(f"[sticker] emotion={sticker_analysis.emotion} ({sticker_analysis.intensity})")

                    # 用 VLM 分析结果辅助回复
                    extra_ctx = sticker_analysis.context_hint
                    reply, merged_emotion = await pipeline.process_sticker(
                        user_id, sticker_url, text=extra_ctx,
                    )
                    dlog(f"[sticker] reply: {reply[:100]}")

                    _pending_emotions[user_id] = merged_emotion.primary

                    if reply:
                        await send_msg(event, reply, merged_emotion.primary)
                except Exception as e:
                    dlog(f"[sticker err] {e}")
                    dlog(traceback.format_exc())

            _pending_events.pop(user_id, None)
            return

        # ========== 情况2：QQ 原生表情 ==========
        if faces and not text and not images:
            face_replies = {
                "14": "就一个微笑，什么意思嘛",
                "12": "嘿嘿，笑什么呢",
                "5": "怎么了，哭什么呀",
                "146": "别哭别哭，发生什么了",
                "121": "谁惹你了，这么生气",
                "11": "怎么了，这么惊讶",
                "109": "害羞什么呀，说嘛",
                "176": "怎么啦，撒娇呢",
                "178": "耶什么呀，有什么好事？",
            }
            reply = face_replies.get(str(faces[0]), "就发表情不说话，什么意思嘛")
            await send_msg(event, reply)
            _pending_events.pop(user_id, None)
            return

        # ========== 情况3：普通图片 ==========
        if images:
            dlog(f"[p] 图片，{len(images)}张")
            emotion_result = pipeline.emotion.analyze(text)
            _pending_emotions[user_id] = emotion_result.primary
            _pending_texts[user_id] = text
            _pending_msg_ids[user_id] = event.message_id

            # 使用 VLM 分析图片
            image_descs = []
            for img_url in images:
                try:
                    desc = await vlm.analyze_image(img_url, "请描述这张图片的内容")
                    image_descs.append(desc)
                    dlog(f"[vlm] 图片分析: {desc[:80]}")
                except Exception as e:
                    dlog(f"[vlm err] {e}")
                    image_descs.append("[图片]")

            # 将图片描述作为额外上下文传入
            image_context = "\n".join(f"[图片{i+1}描述] {d}" for i, d in enumerate(image_descs))
            full_text = text + "\n" + image_context if text else image_context

            reply = await pipeline.process(user_id, full_text)
            dlog(f"[p] image reply: {reply[:100]}")
            if reply:
                await send_msg(event, reply)
            _pending_events.pop(user_id, None)
            return

        # ========== 情况4：文件 ==========
        if files:
            for f in files:
                file_name = f["file_name"]
                dlog(f"[p] 文件: {file_name}")

                text_exts = (
                    ".txt", ".md", ".py", ".json", ".csv",
                    ".xml", ".html", ".css", ".js", ".yaml",
                    ".yml", ".log", ".ini", ".cfg", ".conf",
                )

                if any(file_name.lower().endswith(ext) for ext in text_exts):
                    try:
                        bot = nonebot.get_bot()
                        file_info = await bot.call_api(
                            "get_file", file_id=f["file_id"],
                        )
                        file_path = file_info.get("file", "")
                        if file_path:
                            with open(file_path, "r", encoding="utf-8", errors="ignore") as fp:
                                content = fp.read(3000)

                            reply = await pipeline.process_with_file(
                                user_id, file_name, content,
                            )
                            if reply:
                                await send_msg(event, reply)
                    except Exception as e:
                        dlog(f"[file err] {e}")
                        await send_msg(event, "文件读取出了点问题，稍后再试试吧", is_cmd=True)
                        dlog(f"[file err detail] {e}")
                else:
                    await send_msg(event, f"收到「{file_name}」，目前只能解读文本文件哦。", is_cmd=True)

            _pending_events.pop(user_id, None)
            return

        # ========== 情况5：纯文本 ==========
        if not text:
            dlog("[p] 空消息")
            return

        emotion_result = await pipeline.emotion.analyze_with_llm(text, pipeline.llm)
        _pending_emotions[user_id] = emotion_result.primary

        # ========== 插件处理 ==========
        context = {
            "event": event,
            "emotion": emotion_result,
            "pipeline": pipeline,
            "bot": nonebot.get_bot(),
        }
        plugin_reply = await plugin_mgr.try_handle(text, user_id, context)
        if plugin_reply is not None:
            await send_msg(event, plugin_reply, is_cmd=True)
            return


        _pending_emotions[user_id] = emotion_result.primary

        # 权重自动学习（每30条消息用AI判断一次）
        weight_manager._msg_count = getattr(weight_manager, '_msg_count', 0) + 1
        if weight_manager._msg_count >= 100:
            weight_manager._msg_count = 0
            pipeline._spawn_bg(
                _ai_learn_weights(pipeline, user_id, session.memory.get_context())
            )



        # ===== 1. 处理转发记录 =====
        if parsed.get("forwarded"):
            for forward_id in parsed["forwarded"]:
                try:
                    bot = nonebot.get_bot()
                    fwd_data = await bot.call_api("get_forward_msg", id=forward_id)
                    messages = fwd_data.get("messages", [])
                    lines = []
                    for msg in messages:
                        sender = msg.get("sender", {})
                        nickname = sender.get("nickname", "未知")
                        content = ""
                        for seg in msg.get("message", []):
                            if seg.get("type") == "text":
                                content += seg.get("data", {}).get("text", "")
                        if content:
                            lines.append(f"{nickname}: {content}")
                    if lines:
                        text += "\n[聊天记录]\n" + "\n".join(lines) + "\n[/聊天记录]"
                except Exception as e:
                    dlog(f"[forward err] {e}")

        # ===== 2. 防抖收集（解决一句话回一次的问题） =====
        dlog(f"[p] 收到消息，加入防抖队列等待合并...")
        # 这里只做收集，不做回复。倒计时结束会触发底部的 custom_flush
        await pipeline.process_with_debounce(user_id, text)

    except Exception as e:
        dlog("[p err] " + str(e))
        dlog(traceback.format_exc())
        await send_msg(event, "出了点小问题，稍后再试试吧", "平静", is_cmd=True)



# ========== 防抖与完整输出核心回调 ==========
async def custom_flush(user_id: str, extra_context: str = ""):
    # 1. 提取这段时间（默认8秒内）用户连发的所有消息
    messages = pipeline._pending.pop(user_id, [])
    pipeline._timers.pop(user_id, None)
    if not messages:
        return ""
        
    # 2. 拼接用户发的多条消息
    if len(messages) == 1:
        combined_text = messages[0]
    else:
        combined_text = "\n".join(f"[第{i+1}条] {msg}" for i, msg in enumerate(messages))
        
    event = _pending_events.get(user_id)
    emotion = _pending_emotions.get(user_id, "平静")
    
    if not event:
        # 安全兜底，如果没有 event 截获，直接普通请求
        return await pipeline.process(user_id, combined_text, extra_context)

    dlog(f"[flush] 开始对合并后的消息进行【完整输出（非流式）】")
    
    full_reply = ""
    try:
        # 3. 直接调用非流式 process，一次性拿到大模型的完整回复
        full_reply = await pipeline.process(user_id, combined_text, extra_context)
        
        if full_reply:
            voice_sent = False
            explicit_voice = _is_explicit_voice_request(combined_text)

            # 4. 用户明确要求语音：立即强制尝试 TTS（与随机语音分开）
            if explicit_voice:
                dlog("[voice] 检测到明确语音请求：立即尝试 TTS")
                if not tts_client:
                    await send_msg(event, "我现在不方便发语音，先用文字回复你。", is_cmd=True)
                else:
                    try:
                        silk_path = await tts_client.synthesize(full_reply, user_id)
                        if silk_path:
                            voice_sent = await send_voice(event, silk_path)
                        if not voice_sent:
                            await send_msg(event, "我现在不方便发语音，先用文字回复你。", is_cmd=True)
                    except Exception as ve:
                        dlog(f"[voice] 明确语音请求但合成失败: {ve}")
                        await send_msg(event, "我现在不方便发语音，先用文字回复你。", is_cmd=True)
            # 5. 非明确请求时，按随机语音策略走
            elif tts_client and _should_voice_reply(combined_text, full_reply):
                silk_path = await tts_client.synthesize(full_reply, user_id)
                if silk_path:
                    voice_sent = await send_voice(event, silk_path)
            
            # 6. 如果没发语音，就发送文字
            if not voice_sent:
                await send_msg(event, full_reply, emotion)
            else:
                # 语音自识别：记录到记忆，让机器人知道自己发了语音
                session = pipeline.get_session(user_id)
                if session and session.memory:
                    # 在记忆中标记这条回复是语音
                    voice_hint = f"[语音消息]"
                    session.memory.messages.append(
                        session.memory.Message(role="system", content=voice_hint)
                    )
                    dlog(f"[voice] 已记录语音自识别标记")
                
    except Exception as e:
        dlog(f"[flush send err] {e}")
        import traceback
        dlog(traceback.format_exc())

    # 6. 清理状态
    _pending_events.pop(user_id, None)
    _pending_emotions.pop(user_id, None)
    _pending_texts.pop(user_id, None)
    
    return full_reply

# 替换 pipeline 默认的 flush 逻辑
pipeline._flush_messages = custom_flush
