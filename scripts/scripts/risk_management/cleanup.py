"""
cleanup.py
清理最近12小时内的对话记录和短期记忆
"""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta


DB_PATH = Path("data/chatbot.db")


def main():
    if not DB_PATH.exists():
        print(f"数据库不存在: {DB_PATH}")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    cutoff_time = (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")
    cutoff_time_short = (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%d %H:%M")
    cutoff_date = (datetime.now() - timedelta(hours=12)).strftime("%Y-%m-%d")

    print(f"\n===== 清理最近12小时内的数据 =====\n")
    print(f"  截止时间: {cutoff_time} 之后的数据将被清理")
    print()

    # 1. 对话记录
    cnt = conn.execute(
        "SELECT COUNT(*) as cnt FROM conversation_log WHERE timestamp >= ?",
        (cutoff_time,)
    ).fetchone()["cnt"]
    conn.execute("DELETE FROM conversation_log WHERE timestamp >= ?", (cutoff_time,))
    print(f"  对话记录: {cnt} 条")

    # 2. 生活事件
    cnt = conn.execute(
        "SELECT COUNT(*) as cnt FROM life_events WHERE time >= ?",
        (cutoff_time_short,)
    ).fetchone()["cnt"]
    conn.execute("DELETE FROM life_events WHERE time >= ?", (cutoff_time_short,))
    print(f"  生活事件: {cnt} 条")

    # 3. 心情历史
    cnt = conn.execute(
        "SELECT COUNT(*) as cnt FROM mood_history WHERE date >= ?",
        (cutoff_date,)
    ).fetchone()["cnt"]
    conn.execute("DELETE FROM mood_history WHERE date >= ?", (cutoff_date,))
    print(f"  心情历史: {cnt} 条")

    # 4. 心理分析历史
    cnt = conn.execute(
        "SELECT COUNT(*) as cnt FROM psychology_history WHERE timestamp >= ?",
        (cutoff_time,)
    ).fetchone()["cnt"]
    conn.execute("DELETE FROM psychology_history WHERE timestamp >= ?", (cutoff_time,))
    print(f"  心理历史: {cnt} 条")

    conn.commit()
    conn.execute("VACUUM")
    conn.close()

    print(f"\n  清理完成，数据库已压缩")


if __name__ == "__main__":
    main()
