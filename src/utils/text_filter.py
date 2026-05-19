# by UBAI
"""
text_filter.py
Unicode 不可见字符过滤工具
用于过滤用户消息中的不可见/零宽字符，防止空白消息绕过检测
"""
import re
import unicodedata


# 需要过滤的 Unicode 不可见字符集合
INVISIBLE_CHARS = [
    '\u200E',  # LRM (Left-to-Right Mark)
    '\u200C',  # ZWNJ (Zero Width Non-Joiner)
    '\u200B',  # ZWSP (Zero Width Space)
    '\u200D',  # ZWJ (Zero Width Joiner)
    '\uFEFF',  # ZWNBS / BOM (Zero Width No-Break Space)
    '\u200F',  # RLM (Right-to-Left Mark)
    '\u00AD',  # Soft Hyphen
    '\u034F',  # Combining Grapheme Joiner
    '\u180E',  # Mongolian Vowel Separator
    '\u2028',  # Line Separator
    '\u2029',  # Paragraph Separator
    '\u205F',  # Medium Mathematical Space
    '\u3000',  # Ideographic Space (全角空格)
]

# 范围型不可见字符
INVISIBLE_RANGES = [
    (0x2000, 0x200A),  # 各种空格 (En Quad ~ Hair Space)
    (0x202A, 0x202E),  # 方向覆盖 (LRE ~ RLO)
    (0x2060, 0x2069),  # 不可见格式化 (Word Joiner ~ Inhibit Symmetric Swapping)
]

# 编译正则：匹配所有不可见字符
_invisible_pattern = re.compile(
    '['
    + ''.join(INVISIBLE_CHARS)
    + ''.join(
        chr(start) + '-' + chr(end)
        for start, end in INVISIBLE_RANGES
    )
    + ']'
)


def strip_invisible(text: str) -> str:
    """
    移除文本中所有 Unicode 不可见字符。
    包括零宽字符、方向覆盖、各种空格、BOM 等。
    """
    if not text:
        return ""
    result = _invisible_pattern.sub('', text)
    # 额外去除标准 unicode 分类为 "Cf" (Format) 和 "Cc" (Control) 的字符
    # 但保留常见的换行和制表符
    cleaned = []
    for ch in result:
        cat = unicodedata.category(ch)
        if cat in ('Cf', 'Cc') and ch not in ('\n', '\r', '\t'):
            continue
        cleaned.append(ch)
    return ''.join(cleaned).strip()


def is_effectively_empty(text: str) -> bool:
    """
    判断文本是否"实际上为空"。
    即使原始文本包含不可见字符，strip_invisible 后为空也算空。
    """
    if not text:
        return True
    return len(strip_invisible(text)) == 0
